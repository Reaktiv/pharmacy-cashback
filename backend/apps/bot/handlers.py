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
from apps.bot.states import RedeemStates

BALANCE_BUTTON = "💰 Balance"
REDEEM_BUTTON = "🎟 Redeem"


def _contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Share my phone number", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BALANCE_BUTTON), KeyboardButton(text=REDEEM_BUTTON)]],
        resize_keyboard=True,
    )


def _consent_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="I agree", callback_data="consent:accept")]]
    )


async def cmd_start(message: Message, tenant, bot_row) -> None:
    await message.answer(
        f"Welcome to {tenant.name}! Earn cashback points on every purchase.\n\n"
        "Please share your phone number to get started.",
        reply_markup=_contact_keyboard(),
    )


async def on_contact(message: Message, tenant, bot_row, state: FSMContext) -> None:
    contact = message.contact
    assert contact is not None  # guaranteed by the F.contact filter this is registered under
    assert message.from_user is not None  # webhook updates always carry a sender

    if contact.user_id and contact.user_id != message.from_user.id:
        await message.answer("Please share your own contact, not someone else's.")
        return

    await state.update_data(
        phone=contact.phone_number, full_name=message.from_user.first_name or ""
    )
    await message.answer(
        "By continuing, you agree to receive cashback notifications and consent to "
        "us processing your phone number.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("Please confirm:", reply_markup=_consent_keyboard())


async def on_consent_accept(callback: CallbackQuery, tenant, bot_row, state: FSMContext) -> None:
    data = await state.get_data()
    phone = data.get("phone")
    full_name = data.get("full_name", "")
    if not phone:
        await callback.answer("Session expired, please /start again.", show_alert=True)
        return

    text = await sync_to_async(bot_services.handle_registration, thread_sensitive=True)(
        tenant=tenant, telegram_id=callback.from_user.id, phone=phone, full_name=full_name
    )
    await state.clear()

    assert callback.message is not None and hasattr(callback.message, "answer")
    await callback.message.answer(text, reply_markup=_main_menu_keyboard())
    await callback.answer()


async def on_balance(message: Message, tenant, bot_row) -> None:
    assert message.from_user is not None
    text = await sync_to_async(bot_services.handle_balance_query, thread_sensitive=True)(
        tenant=tenant, telegram_id=message.from_user.id
    )
    await message.answer(text)


async def on_redeem_start(message: Message, tenant, bot_row, state: FSMContext) -> None:
    assert message.from_user is not None
    is_registered = await sync_to_async(
        bot_services.customer_is_registered, thread_sensitive=True
    )(tenant=tenant, telegram_id=message.from_user.id)
    if not is_registered:
        await message.answer("You're not registered yet — send /start to begin.")
        return
    await state.set_state(RedeemStates.awaiting_amount)
    await message.answer("How many points would you like to redeem?")


async def on_redeem_amount(message: Message, tenant, bot_row, state: FSMContext) -> None:
    assert message.from_user is not None
    text = await sync_to_async(bot_services.handle_redeem_request, thread_sensitive=True)(
        tenant=tenant, telegram_id=message.from_user.id, raw_amount=message.text or ""
    )
    await state.clear()
    await message.answer(text, reply_markup=_main_menu_keyboard())


async def on_report(callback: CallbackQuery, tenant, bot_row) -> None:
    data = callback.data or ""
    try:
        transaction_id = int(data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Sorry, that report could not be processed.", show_alert=True)
        return

    text = await sync_to_async(bot_services.handle_report, thread_sensitive=True)(
        tenant=tenant, telegram_id=callback.from_user.id, transaction_id=transaction_id
    )
    await callback.answer(text, show_alert=True)


def register_handlers(router) -> None:
    router.message.register(cmd_start, CommandStart())
    router.message.register(on_contact, F.contact)
    router.callback_query.register(on_consent_accept, F.data == "consent:accept")
    router.message.register(on_balance, F.text == BALANCE_BUTTON)
    router.message.register(on_redeem_start, F.text == REDEEM_BUTTON)
    router.message.register(on_redeem_amount, RedeemStates.awaiting_amount)
    router.callback_query.register(on_report, F.data.startswith("report:"))
