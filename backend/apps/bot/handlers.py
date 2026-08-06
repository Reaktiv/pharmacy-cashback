"""Customer-facing bot handlers (CLAUDE.md §7a). Thin async layer only:
extract data from the Telegram update, delegate to apps.bot.services (sync,
via sync_to_async), send the reply. No Django ORM or cashback math directly
in here.

tenant/bot_row arrive as injected workflow data from Dispatcher.feed_update
(see apps/bot/views.py) — handlers never read the ambient tenant ContextVar
themselves, matching apps/ledger/services.py's "take it explicitly"
convention.

Handlers are registered programmatically via register_handlers() rather
than router decorators, so a fresh Dispatcher can register them each
request (see apps/bot/dispatcher.py for why it's rebuilt per request) —
aiogram routers can't be re-attached to a second parent once attached once.

Every string a customer sees is looked up via apps.bot.i18n.t(language, key)
— never inlined here — because a customer's UI language (Customer.language,
picked at registration, editable later via the Settings menu) determines it.
Before registration there's no Customer row yet, so the chosen language
rides along in FSM state data instead (see on_registration_language_select).
"""

from aiogram import F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from asgiref.sync import sync_to_async

from apps.bot import services as bot_services
from apps.bot.i18n import CHOOSE_LANGUAGE_PROMPT, DEFAULT_LANGUAGE, LANGUAGE_LABELS, button_labels, t
from apps.bot.states import RedeemStates, SettingsStates

REGISTRATION_LANGUAGE_PREFIX = "reglang"
SETTINGS_LANGUAGE_PREFIX = "setlang"


def _language_keyboard(callback_prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label, callback_data=f"{callback_prefix}:{code}"
                )
            ]
            for code, label in LANGUAGE_LABELS.items()
        ]
    )


def _contact_keyboard(language: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(language, "contact_button"), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _main_menu_keyboard(language: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t(language, "balance_button")),
                KeyboardButton(text=t(language, "redeem_button")),
            ],
            [KeyboardButton(text=t(language, "settings_button"))],
        ],
        resize_keyboard=True,
    )


def _consent_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(language, "consent_button"), callback_data="consent:accept"
                )
            ]
        ]
    )


def _settings_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t(language, "settings_change_name"), callback_data="settings:name"
                )
            ],
            [
                InlineKeyboardButton(
                    text=t(language, "settings_change_language"),
                    callback_data="settings:language",
                )
            ],
        ]
    )


async def cmd_start(message: Message, tenant, bot_row) -> None:
    assert message.from_user is not None  # webhook updates always carry a sender

    language = await sync_to_async(bot_services.get_customer_language, thread_sensitive=True)(
        tenant=tenant, telegram_id=message.from_user.id
    )
    is_registered = await sync_to_async(
        bot_services.customer_is_registered, thread_sensitive=True
    )(tenant=tenant, telegram_id=message.from_user.id)
    if is_registered:
        # Already registered — asking for phone/consent again on every
        # /start (instead of just greeting them) is exactly the loop this
        # branch avoids.
        await message.answer(
            t(language, "welcome_back", tenant=tenant.name),
            reply_markup=_main_menu_keyboard(language),
        )
        return

    await message.answer(CHOOSE_LANGUAGE_PROMPT, reply_markup=_language_keyboard(REGISTRATION_LANGUAGE_PREFIX))


async def on_registration_language_select(callback: CallbackQuery, tenant, bot_row, state: FSMContext) -> None:
    data = callback.data or ""
    language = data.split(":", 1)[1] if ":" in data else DEFAULT_LANGUAGE
    if language not in LANGUAGE_LABELS:
        language = DEFAULT_LANGUAGE

    await state.update_data(language=language)
    await callback.answer()
    assert callback.message is not None and hasattr(callback.message, "answer")
    await callback.message.answer(
        t(language, "welcome_intro", tenant=tenant.name),
        reply_markup=_contact_keyboard(language),
    )


async def on_contact(message: Message, tenant, bot_row, state: FSMContext) -> None:
    contact = message.contact
    assert contact is not None  # guaranteed by the F.contact filter this is registered under
    assert message.from_user is not None  # webhook updates always carry a sender

    data = await state.get_data()
    language = data.get("language", DEFAULT_LANGUAGE)

    if contact.user_id and contact.user_id != message.from_user.id:
        await message.answer(t(language, "contact_wrong_owner"))
        return

    await state.update_data(
        phone=contact.phone_number, full_name=message.from_user.first_name or ""
    )
    await message.answer(
        t(language, "consent_text"),
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(t(language, "consent_confirm_prompt"), reply_markup=_consent_keyboard(language))


async def on_consent_accept(callback: CallbackQuery, tenant, bot_row, state: FSMContext) -> None:
    data = await state.get_data()
    phone = data.get("phone")
    full_name = data.get("full_name", "")
    language = data.get("language", DEFAULT_LANGUAGE)
    if not phone:
        await callback.answer(t(language, "session_expired"), show_alert=True)
        return

    text = await sync_to_async(bot_services.handle_registration, thread_sensitive=True)(
        tenant=tenant,
        telegram_id=callback.from_user.id,
        phone=phone,
        full_name=full_name,
        language=language,
    )
    await state.clear()

    assert callback.message is not None and hasattr(callback.message, "answer")
    await callback.message.answer(text, reply_markup=_main_menu_keyboard(language))
    await callback.answer()


async def on_balance(message: Message, tenant, bot_row) -> None:
    assert message.from_user is not None
    text = await sync_to_async(bot_services.handle_balance_query, thread_sensitive=True)(
        tenant=tenant, telegram_id=message.from_user.id
    )
    await message.answer(text)


async def on_redeem_start(message: Message, tenant, bot_row, state: FSMContext) -> None:
    assert message.from_user is not None
    language = await sync_to_async(bot_services.get_customer_language, thread_sensitive=True)(
        tenant=tenant, telegram_id=message.from_user.id
    )
    is_registered = await sync_to_async(
        bot_services.customer_is_registered, thread_sensitive=True
    )(tenant=tenant, telegram_id=message.from_user.id)
    if not is_registered:
        await message.answer(t(language, "not_registered"))
        return
    await state.set_state(RedeemStates.awaiting_amount)
    await message.answer(t(language, "redeem_ask_amount"))


async def on_redeem_amount(message: Message, tenant, bot_row, state: FSMContext) -> None:
    assert message.from_user is not None
    text = await sync_to_async(bot_services.handle_redeem_request, thread_sensitive=True)(
        tenant=tenant, telegram_id=message.from_user.id, raw_amount=message.text or ""
    )
    language = await sync_to_async(bot_services.get_customer_language, thread_sensitive=True)(
        tenant=tenant, telegram_id=message.from_user.id
    )
    await state.clear()
    await message.answer(text, reply_markup=_main_menu_keyboard(language))


async def on_settings_start(message: Message, tenant, bot_row) -> None:
    assert message.from_user is not None
    language = await sync_to_async(bot_services.get_customer_language, thread_sensitive=True)(
        tenant=tenant, telegram_id=message.from_user.id
    )
    is_registered = await sync_to_async(
        bot_services.customer_is_registered, thread_sensitive=True
    )(tenant=tenant, telegram_id=message.from_user.id)
    if not is_registered:
        await message.answer(t(language, "not_registered"))
        return
    await message.answer(t(language, "settings_menu_prompt"), reply_markup=_settings_keyboard(language))


async def on_settings_change_name_prompt(callback: CallbackQuery, tenant, bot_row, state: FSMContext) -> None:
    language = await sync_to_async(bot_services.get_customer_language, thread_sensitive=True)(
        tenant=tenant, telegram_id=callback.from_user.id
    )
    await state.set_state(SettingsStates.awaiting_name)
    await callback.answer()
    assert callback.message is not None and hasattr(callback.message, "answer")
    await callback.message.answer(t(language, "settings_ask_new_name"))


async def on_settings_new_name(message: Message, tenant, bot_row, state: FSMContext) -> None:
    assert message.from_user is not None
    new_name = (message.text or "").strip()
    customer = await sync_to_async(bot_services.update_customer_name, thread_sensitive=True)(
        tenant=tenant, telegram_id=message.from_user.id, full_name=new_name
    )
    language = customer.language if customer is not None else DEFAULT_LANGUAGE
    await state.clear()
    await message.answer(
        t(language, "settings_name_updated", name=new_name),
        reply_markup=_main_menu_keyboard(language),
    )


async def on_settings_change_language_prompt(callback: CallbackQuery, tenant, bot_row) -> None:
    language = await sync_to_async(bot_services.get_customer_language, thread_sensitive=True)(
        tenant=tenant, telegram_id=callback.from_user.id
    )
    await callback.answer()
    assert callback.message is not None and hasattr(callback.message, "answer")
    await callback.message.answer(
        t(language, "settings_choose_language"),
        reply_markup=_language_keyboard(SETTINGS_LANGUAGE_PREFIX),
    )


async def on_settings_language_select(callback: CallbackQuery, tenant, bot_row) -> None:
    data = callback.data or ""
    new_language = data.split(":", 1)[1] if ":" in data else DEFAULT_LANGUAGE
    if new_language not in LANGUAGE_LABELS:
        new_language = DEFAULT_LANGUAGE

    await sync_to_async(bot_services.update_customer_language, thread_sensitive=True)(
        tenant=tenant, telegram_id=callback.from_user.id, language=new_language
    )
    await callback.answer()
    assert callback.message is not None and hasattr(callback.message, "answer")
    await callback.message.answer(
        t(new_language, "settings_language_updated"),
        reply_markup=_main_menu_keyboard(new_language),
    )


async def on_report(callback: CallbackQuery, tenant, bot_row) -> None:
    data = callback.data or ""
    try:
        transaction_id = int(data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer(t(DEFAULT_LANGUAGE, "report_invalid"), show_alert=True)
        return

    text = await sync_to_async(bot_services.handle_report, thread_sensitive=True)(
        tenant=tenant, telegram_id=callback.from_user.id, transaction_id=transaction_id
    )
    await callback.answer(text, show_alert=True)


def register_handlers(router) -> None:
    router.message.register(cmd_start, CommandStart())
    router.callback_query.register(
        on_registration_language_select, F.data.startswith(f"{REGISTRATION_LANGUAGE_PREFIX}:")
    )
    router.message.register(on_contact, F.contact)
    router.callback_query.register(on_consent_accept, F.data == "consent:accept")
    router.message.register(on_balance, F.text.in_(button_labels("balance_button")))
    router.message.register(on_redeem_start, F.text.in_(button_labels("redeem_button")))
    router.message.register(on_redeem_amount, RedeemStates.awaiting_amount)
    router.message.register(on_settings_start, F.text.in_(button_labels("settings_button")))
    router.callback_query.register(on_settings_change_name_prompt, F.data == "settings:name")
    router.message.register(on_settings_new_name, SettingsStates.awaiting_name)
    router.callback_query.register(
        on_settings_change_language_prompt, F.data == "settings:language"
    )
    router.callback_query.register(
        on_settings_language_select, F.data.startswith(f"{SETTINGS_LANGUAGE_PREFIX}:")
    )
    router.callback_query.register(on_report, F.data.startswith("report:"))
