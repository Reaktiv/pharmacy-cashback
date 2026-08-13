"""Server-rendered string translations (uz/en/ru) for the seller-web pages
(the register/earn/redeem "till" page and its login/forbidden screens).
Same lightweight dict approach as apps.bot.i18n — no gettext/.po pipeline,
since the string set is small and confined to this app.

Unlike the bot (where language is a Customer field the customer picks at
registration) or the React admin panel (where it's a browser localStorage
choice), a seller has no profile field for this and the page is plain
server-rendered HTML — so the preference lives in a cookie, set by
`set_language` below.
"""

from django.http import HttpRequest

LANGUAGE_COOKIE = "seller_lang"
LANGUAGES = ["uz", "en", "ru"]
DEFAULT_LANGUAGE = "uz"

# Each language's own name, for the switcher — always shown in that
# language regardless of the current UI language.
LANGUAGE_LABELS = {
    "uz": "UZ",
    "en": "EN",
    "ru": "RU",
}

_STRINGS = {
    "page_title": {"uz": "Sotuvchi kassasi", "en": "Seller till", "ru": "Касса продавца"},
    "brand_subtitle": {"uz": "Sotuvchi kirishi", "en": "Seller sign-in", "ru": "Вход продавца"},
    "login_page_title": {"uz": "Kirish", "en": "Sign in", "ru": "Вход"},
    "login_heading": {
        "uz": "Sotuvchi tizimga kirishi",
        "en": "Seller sign-in",
        "ru": "Вход продавца",
    },
    "login_subheading": {
        "uz": "Kassa sahifasiga o'tish uchun hisobingizga kiring.",
        "en": "Sign in to your account to open the till page.",
        "ru": "Войдите в свою учётную запись, чтобы открыть страницу кассы.",
    },
    "login_username": {"uz": "Foydalanuvchi nomi", "en": "Username", "ru": "Имя пользователя"},
    "login_password": {"uz": "Parol", "en": "Password", "ru": "Пароль"},
    "login_submit": {"uz": "Kirish", "en": "Sign in", "ru": "Войти"},

    "logout": {"uz": "Chiqish", "en": "Log out", "ru": "Выйти"},
    "logout_confirm_title": {
        "uz": "Tizimdan chiqasizmi?",
        "en": "Log out?",
        "ru": "Выйти из системы?",
    },
    "logout_confirm_description": {
        "uz": (
            "Joriy sessiyangiz yakunlanadi va qayta kirish uchun login/parolni "
            "kiritishingiz kerak bo'ladi."
        ),
        "en": (
            "Your current session will end and you will need to enter your "
            "login/password to sign in again."
        ),
        "ru": (
            "Текущая сессия завершится, и для повторного входа потребуется "
            "ввести логин и пароль."
        ),
    },
    "cancel": {"uz": "Bekor qilish", "en": "Cancel", "ru": "Отмена"},

    "seller_label": {"uz": "Sotuvchi", "en": "Seller", "ru": "Продавец"},

    "sale_legend": {"uz": "Sotuv", "en": "Sale", "ru": "Продажа"},
    "check_amount_label": {"uz": "Chek summasi", "en": "Check amount", "ru": "Сумма чека"},
    "customer_phone_label": {
        "uz": "Mijoz telefon raqami",
        "en": "Customer's phone number",
        "ru": "Номер телефона клиента",
    },
    "no_cashback_label": {
        "uz": "Keshbek yo'q (faqat retsept bo'yicha)",
        "en": "No cashback (prescription only)",
        "ru": "Без кешбэка (только по рецепту)",
    },
    "record_sale_button": {
        "uz": "Sotuvni qayd etish",
        "en": "Record the sale",
        "ru": "Записать продажу",
    },

    "redeem_legend": {
        "uz": "Ballarni ishlatish",
        "en": "Redeem points",
        "ru": "Использовать баллы",
    },
    "otp_code_label": {"uz": "OTP kod", "en": "OTP code", "ru": "OTP-код"},
    "redeem_button": {"uz": "Ishlatish", "en": "Redeem", "ru": "Использовать"},

    "forbidden_title": {"uz": "Mavjud emas", "en": "Not available", "ru": "Недоступно"},
    "forbidden_subtitle": {
        "uz": "Bu sahifa faqat sotuvchi hisoblari uchun.",
        "en": "This page is only for seller accounts.",
        "ru": "Эта страница доступна только для аккаунтов продавцов.",
    },

    "earn_form_invalid": {
        "uz": "Iltimos, summa va telefon raqamini tekshiring.",
        "en": "Please check the amount and phone number.",
        "ru": "Пожалуйста, проверьте сумму и номер телефона.",
    },
    "earn_success_earned": {
        "uz": "{earned} ball qo'shildi. Yangi balans: {balance}.",
        "en": "{earned} points added. New balance: {balance}.",
        "ru": "Начислено {earned} баллов. Новый баланс: {balance}.",
    },
    "earn_success_pending": {
        "uz": (
            "Mijoz hali ro'yxatdan o'tmagan — botga qo'shilgach {amount} ball "
            "hisobiga qo'shiladi."
        ),
        "en": (
            "The customer isn't registered yet — {amount} points will be "
            "credited once they join the bot."
        ),
        "ru": (
            "Клиент ещё не зарегистрирован — {amount} баллов будут начислены "
            "после подключения к боту."
        ),
    },
    "earn_success_no_cashback": {
        "uz": "Sotuv qayd etildi. Keshbek berilmadi.",
        "en": "Sale recorded. No cashback given.",
        "ru": "Продажа зафиксирована. Кешбэк не начислен.",
    },
    "redeem_form_invalid": {
        "uz": "Iltimos, summa va OTP kodni tekshiring.",
        "en": "Please check the amount and OTP code.",
        "ru": "Пожалуйста, проверьте сумму и OTP-код.",
    },
    "redeem_success": {
        "uz": "{spent} ball ishlatildi, yana {earned} ball qo'shildi. Yangi balans: {balance}.",
        "en": "{spent} points redeemed, {earned} more points added. New balance: {balance}.",
        "ru": "Использовано {spent} баллов, начислено ещё {earned}. Новый баланс: {balance}.",
    },

    "profile_link": {"uz": "Profil", "en": "Profile", "ru": "Профиль"},
    "profile_page_title": {"uz": "Mening profilim", "en": "My profile", "ru": "Мой профиль"},
    "profile_heading": {"uz": "Mening profilim", "en": "My profile", "ru": "Мой профиль"},
    "profile_login_label": {"uz": "Login", "en": "Login", "ru": "Логин"},
    "profile_full_name_label": {"uz": "To'liq ismi", "en": "Full name", "ru": "Полное имя"},
    "profile_phone_label": {"uz": "Telefon raqami", "en": "Phone number", "ru": "Номер телефона"},
    "profile_change_photo": {"uz": "Rasm tanlash", "en": "Change photo", "ru": "Изменить фото"},
    "profile_remove_photo": {
        "uz": "Rasmni olib tashlash",
        "en": "Remove photo",
        "ru": "Удалить фото",
    },
    "profile_save_button": {"uz": "Saqlash", "en": "Save", "ru": "Сохранить"},
    "profile_back_link": {"uz": "Kassaga qaytish", "en": "Back to the till", "ru": "Назад к кассе"},
    "profile_saved": {"uz": "Profil saqlandi.", "en": "Profile saved.", "ru": "Профиль сохранён."},
    "profile_form_invalid": {
        "uz": "Iltimos, ismi va telefon raqamini tekshiring.",
        "en": "Please check the name and phone number.",
        "ru": "Пожалуйста, проверьте имя и номер телефона.",
    },
    "profile_avatar_invalid_type": {
        "uz": "Faqat rasm fayli yuklash mumkin.",
        "en": "Only an image file can be uploaded.",
        "ru": "Можно загружать только файл изображения.",
    },
    "profile_avatar_too_large": {
        "uz": "Rasm hajmi {size}MB dan oshmasligi kerak.",
        "en": "The image must not exceed {size}MB.",
        "ru": "Размер изображения не должен превышать {size} МБ.",
    },
    "profile_language_label": {"uz": "Til", "en": "Language", "ru": "Язык"},

    "password_section_heading": {
        "uz": "Parolni almashtirish",
        "en": "Change password",
        "ru": "Смена пароля",
    },
    "current_password_label": {
        "uz": "Joriy parol",
        "en": "Current password",
        "ru": "Текущий пароль",
    },
    "new_password_label": {"uz": "Yangi parol", "en": "New password", "ru": "Новый пароль"},
    "confirm_new_password_label": {
        "uz": "Yangi parolni takrorlang",
        "en": "Confirm new password",
        "ru": "Повторите новый пароль",
    },
    "change_password_button": {
        "uz": "Parolni almashtirish",
        "en": "Change password",
        "ru": "Сменить пароль",
    },
    "password_changed": {
        "uz": "Parol muvaffaqiyatli almashtirildi.",
        "en": "Password changed successfully.",
        "ru": "Пароль успешно изменён.",
    },
    "password_change_error": {
        "uz": "Parolni almashtirib bo'lmadi. Quyidagi xatolarni tekshiring.",
        "en": "Couldn't change the password. Check the errors below.",
        "ru": "Не удалось изменить пароль. Проверьте ошибки ниже.",
    },
}


def t(language: str, key: str, **kwargs) -> str:
    lang = language if language in LANGUAGES else DEFAULT_LANGUAGE
    template = _STRINGS[key][lang]
    return template.format(**kwargs) if kwargs else template


def strings_for(language: str) -> dict[str, str]:
    """A flat {key: text} dict for the given language — passed into template
    context as `s` so templates read `{{ s.some_key }}` directly, no custom
    template tags needed."""
    lang = language if language in LANGUAGES else DEFAULT_LANGUAGE
    return {key: variants[lang] for key, variants in _STRINGS.items()}


def get_language(request: HttpRequest) -> str:
    raw = request.COOKIES.get(LANGUAGE_COOKIE, DEFAULT_LANGUAGE)
    return raw if raw in LANGUAGES else DEFAULT_LANGUAGE
