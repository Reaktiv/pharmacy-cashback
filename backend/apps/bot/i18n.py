"""Bot-facing string translations (uz/en/ru). Plain dict lookup rather than
gettext/.po — the string set is small and entirely confined to this app, so
a translation pipeline would be pure overhead (CLAUDE.md §11: ask before
adding a dependency not in §9; this needs none).

Every user-facing string in apps/bot lives here, keyed by a short name, with
one variant per apps.customers.models.Customer.Language code. Handlers/
services never inline Uzbek (or any language) text directly — they call
`t(language, key, **kwargs)`.
"""

from apps.customers.models import Customer

Language = str  # one of Customer.Language.values

DEFAULT_LANGUAGE: Language = Customer.Language.UZBEK

# Each language's own name, for the language-picker buttons — always shown
# in that language regardless of the current UI language, so a user can
# recognize their own language even if stuck on the wrong one.
LANGUAGE_LABELS: dict[Language, str] = {
    Customer.Language.UZBEK: "O'zbekcha 🇺🇿",
    Customer.Language.ENGLISH: "English 🇬🇧",
    Customer.Language.RUSSIAN: "Русский 🇷🇺",
}

# Shown before we know the user's language at all, so it's not keyed by one.
CHOOSE_LANGUAGE_PROMPT = "Tilni tanlang / Please choose your language / Пожалуйста, выберите язык:"

_STRINGS: dict[str, dict[Language, str]] = {
    "welcome_intro": {
        "uz": "{tenant} botiga xush kelibsiz! Har bir xariddan keshbek ballari to'plang.\n\n"
        "Boshlash uchun telefon raqamingizni ulashing.",
        "en": "Welcome to {tenant}! Collect cashback points on every purchase.\n\n"
        "Share your phone number to get started.",
        "ru": "Добро пожаловать в {tenant}! Собирайте кешбэк-баллы за каждую покупку.\n\n"
        "Поделитесь номером телефона, чтобы начать.",
    },
    "welcome_back": {
        "uz": "Qaytib kelganingizdan xursandmiz, {tenant}!",
        "en": "Welcome back to {tenant}!",
        "ru": "С возвращением в {tenant}!",
    },
    "contact_button": {
        "uz": "Telefon raqamimni ulashish",
        "en": "Share my phone number",
        "ru": "Поделиться номером телефона",
    },
    "contact_wrong_owner": {
        "uz": "Iltimos, o'zingizning kontaktingizni ulashing, boshqa birovnikini emas.",
        "en": "Please share your own contact, not someone else's.",
        "ru": "Пожалуйста, поделитесь своим контактом, а не чужим.",
    },
    "consent_text": {
        "uz": "Davom etish orqali siz keshbek bildirishnomalarini olishga va telefon "
        "raqamingizni qayta ishlashimizga rozilik bildirasiz.",
        "en": "By continuing, you agree to receive cashback notifications and to our "
        "processing of your phone number.",
        "ru": "Продолжая, вы соглашаетесь получать уведомления о кешбэке и на обработку "
        "вашего номера телефона.",
    },
    "consent_confirm_prompt": {
        "uz": "Tasdiqlang:",
        "en": "Please confirm:",
        "ru": "Подтвердите:",
    },
    "consent_button": {
        "uz": "Roziman",
        "en": "I agree",
        "ru": "Согласен",
    },
    "session_expired": {
        "uz": "Sessiya muddati tugadi, iltimos qaytadan /start bosing.",
        "en": "Your session expired — please send /start again.",
        "ru": "Сессия истекла, пожалуйста, отправьте /start снова.",
    },
    "registered_success": {
        "uz": "Siz ro'yxatdan o'tdingiz! 🎉",
        "en": "You're registered! 🎉",
        "ru": "Вы зарегистрированы! 🎉",
    },
    "claimed_amount": {
        "uz": "Avvalgi xaridlaringizdan {amount} ball hisobingizga qo'shildi.",
        "en": "{amount} points from your earlier purchases were added to your balance.",
        "ru": "{amount} баллов за ваши предыдущие покупки добавлены на баланс.",
    },
    "balance_message": {
        "uz": "Balansingiz: {balance} ball.\n"
        "Har qanday xarid summasining {percent}%igacha ishlatishingiz mumkin.",
        "en": "Your balance: {balance} points.\n"
        "You can redeem up to {percent}% of any purchase amount.",
        "ru": "Ваш баланс: {balance} баллов.\n"
        "Вы можете использовать до {percent}% от суммы любой покупки.",
    },
    "not_registered": {
        "uz": "Siz hali ro'yxatdan o'tmagansiz — boshlash uchun /start yuboring.",
        "en": "You haven't registered yet — send /start to begin.",
        "ru": "Вы ещё не зарегистрированы — отправьте /start, чтобы начать.",
    },
    "balance_button": {
        "uz": "💰 Balans",
        "en": "💰 Balance",
        "ru": "💰 Баланс",
    },
    "redeem_button": {
        "uz": "🎟 Ballarni ishlatish",
        "en": "🎟 Redeem points",
        "ru": "🎟 Использовать баллы",
    },
    "settings_button": {
        "uz": "⚙️ Sozlamalar",
        "en": "⚙️ Settings",
        "ru": "⚙️ Настройки",
    },
    "redeem_ask_amount": {
        "uz": "Nechta ballni ishlatmoqchisiz?",
        "en": "How many points would you like to redeem?",
        "ru": "Сколько баллов вы хотите использовать?",
    },
    "redeem_invalid_number": {
        "uz": "Iltimos, to'g'ri raqam kiriting.",
        "en": "Please enter a valid number.",
        "ru": "Пожалуйста, введите правильное число.",
    },
    "redeem_amount_must_be_positive": {
        "uz": "Miqdor noldan katta bo'lishi kerak.",
        "en": "The amount must be greater than zero.",
        "ru": "Сумма должна быть больше нуля.",
    },
    "redeem_insufficient_balance": {
        "uz": "Sizda bu qadar ball yo'q.",
        "en": "You don't have that many points.",
        "ru": "У вас недостаточно баллов.",
    },
    "redeem_code": {
        "uz": "Sizning kodingiz: {code}\nBuni sotuvchiga ko'rsating. Kod 5 daqiqada eskiradi.",
        "en": "Your code: {code}\nShow this to the cashier. It expires in 5 minutes.",
        "ru": "Ваш код: {code}\nПокажите его кассиру. Код истекает через 5 минут.",
    },
    "report_invalid": {
        "uz": "Kechirasiz, bu shikoyatni qayta ishlab bo'lmadi.",
        "en": "Sorry, this report couldn't be processed.",
        "ru": "Извините, эту жалобу не удалось обработать.",
    },
    "report_thanks": {
        "uz": "Rahmat — bu qayd etildi. Menejer buni ko'rib chiqadi.",
        "en": "Thanks — this has been logged. A manager will review it.",
        "ru": "Спасибо — это зафиксировано. Менеджер рассмотрит это.",
    },
    "report_button": {
        "uz": "Miqdor noto'g'rimi? Shikoyat qilish",
        "en": "Wrong amount? Report it",
        "ru": "Неверная сумма? Пожаловаться",
    },
    "notif_reversal": {
        "uz": "⚠️ Oldingi tranzaksiya tuzatildi.",
        "en": "⚠️ A previous transaction was corrected.",
        "ru": "⚠️ Предыдущая транзакция была исправлена.",
    },
    "notif_earned": {
        "uz": "✅ {check_amount} so'mlik xariddan {earned} ball qo'shildi.",
        "en": "✅ {earned} points added from a {check_amount} UZS purchase.",
        "ru": "✅ Начислено {earned} баллов за покупку на {check_amount} сум.",
    },
    "notif_spent": {
        "uz": "✅ {spent} ball ishlatildi.",
        "en": "✅ {spent} points redeemed.",
        "ru": "✅ Использовано {spent} баллов.",
    },
    "notif_no_cashback": {
        "uz": "ℹ️ Ushbu xarid uchun ball berilmadi (faqat retsept bo'yicha savdo).",
        "en": "ℹ️ No points for this purchase (prescription-only sale).",
        "ru": "ℹ️ Баллы за эту покупку не начислены (продажа только по рецепту).",
    },
    "notif_generic": {
        "uz": "Xaridingiz qayd etildi.",
        "en": "Your purchase was recorded.",
        "ru": "Ваша покупка зафиксирована.",
    },
    "notif_balance_suffix": {
        "uz": "Balans: {balance}.",
        "en": "Balance: {balance}.",
        "ru": "Баланс: {balance}.",
    },
    "settings_menu_prompt": {
        "uz": "Nimani o'zgartirmoqchisiz?",
        "en": "What would you like to change?",
        "ru": "Что вы хотите изменить?",
    },
    "settings_change_name": {
        "uz": "✏️ Ismni o'zgartirish",
        "en": "✏️ Change name",
        "ru": "✏️ Изменить имя",
    },
    "settings_change_language": {
        "uz": "🌐 Tilni o'zgartirish",
        "en": "🌐 Change language",
        "ru": "🌐 Изменить язык",
    },
    "settings_ask_new_name": {
        "uz": "Yangi ismingizni yuboring:",
        "en": "Please send your new name:",
        "ru": "Отправьте новое имя:",
    },
    "settings_name_updated": {
        "uz": "Ismingiz yangilandi: {name}",
        "en": "Your name was updated: {name}",
        "ru": "Ваше имя обновлено: {name}",
    },
    "settings_choose_language": {
        "uz": "Yangi tilni tanlang:",
        "en": "Choose a new language:",
        "ru": "Выберите новый язык:",
    },
    "settings_language_updated": {
        "uz": "Til o'zgartirildi.",
        "en": "Language changed.",
        "ru": "Язык изменён.",
    },
    "receipt_button": {
        "uz": "🧾 Chek yuborish",
        "en": "🧾 Send receipt",
        "ru": "🧾 Отправить чек",
    },
    "receipt_ask_photo": {
        "uz": "Chekingizning QR kodi aniq ko'rinadigan suratini yuboring. Agar o'qilmasa — rasmni 📎 fayl sifatida yuboring (Telegram uni siqib, sifatini pasaytirmaydi).",
        "en": "Send a photo of your receipt with the QR code clearly visible. If it doesn't read, send it as a 📎 file instead (Telegram won't compress it).",
        "ru": "Отправьте фото чека, на котором чётко виден QR-код. Если не считается — отправьте фото как 📎 файл (Telegram его не сожмёт).",
    },
    "receipt_processing": {
        "uz": "⏳ Chek tekshirilmoqda...",
        "en": "⏳ Checking your receipt...",
        "ru": "⏳ Проверяем ваш чек...",
    },
    "receipt_qr_not_found": {
        "uz": "Rasmda QR kod topilmadi. Qayta suratga oling yoki rasmni 📎 fayl sifatida yuborib ko'ring — Telegram fotosuratlarni siqib, QR kodning mayda detallarini yo'qotib qo'yishi mumkin.",
        "en": "No QR code found in the photo. Retake it, or try sending it as a 📎 file instead — Telegram compresses photos, which can destroy a QR code's fine detail.",
        "ru": "На фото не найден QR-код. Переснимите или попробуйте отправить как 📎 файл — Telegram сжимает фото, из-за чего мелкие детали QR-кода могут теряться.",
    },
    "receipt_untrusted_url": {
        "uz": "Bu QR kod chek havolasi emas.",
        "en": "This QR code isn't a receipt link.",
        "ru": "Этот QR-код не является ссылкой на чек.",
    },
    "receipt_not_configured": {
        "uz": "Kechirasiz, bu dorixonada QR-chek orqali cashback hali sozlanmagan.",
        "en": "Sorry, QR-receipt cashback isn't set up for this pharmacy yet.",
        "ru": "Извините, кешбэк по QR-чеку для этой аптеки пока не настроен.",
    },
    "receipt_wrong_tenant": {
        "uz": "Bu chek ushbu dorixonaga tegishli emas.",
        "en": "This receipt doesn't belong to this pharmacy.",
        "ru": "Этот чек не относится к этой аптеке.",
    },
    "receipt_already_used": {
        "uz": "Bu chek allaqachon ishlatilgan.",
        "en": "This receipt has already been used.",
        "ru": "Этот чек уже был использован.",
    },
    "receipt_fetch_failed": {
        "uz": "Chekni tekshirib bo'lmadi. Birozdan keyin qayta urinib ko'ring.",
        "en": "Couldn't verify the receipt. Please try again shortly.",
        "ru": "Не удалось проверить чек. Попробуйте ещё раз позже.",
    },
    "cancel_button": {
        "uz": "❌ Bekor qilish",
        "en": "❌ Cancel",
        "ru": "❌ Отмена",
    },
    "cancelled_message": {
        "uz": "Bekor qilindi.",
        "en": "Cancelled.",
        "ru": "Отменено.",
    },
}


def t(language: Language | None, key: str, **kwargs) -> str:
    lang = language if language in LANGUAGE_LABELS else DEFAULT_LANGUAGE
    template = _STRINGS[key][lang]
    return template.format(**kwargs) if kwargs else template


def button_labels(key: str) -> list[str]:
    """All per-language variants of a reply-keyboard button's text, for
    filter matching (F.text.in_(...)) — a customer's keyboard is rendered in
    their own language, so a handler must recognize any of the three."""
    return list(_STRINGS[key].values())
