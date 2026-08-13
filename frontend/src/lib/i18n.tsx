import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'

export type Language = 'uz' | 'en' | 'ru'

export const LANGUAGES: Language[] = ['uz', 'en', 'ru']

// Each language's own name — shown on the switcher regardless of the
// current UI language, same convention as the Telegram bot's picker
// (apps/bot/i18n.py) so a user can recognize their language either way.
export const LANGUAGE_LABELS: Record<Language, string> = {
  uz: "O'zbekcha",
  en: 'English',
  ru: 'Русский',
}

const STORAGE_KEY = 'pharmacy_cashback_language'
export const DEFAULT_LANGUAGE: Language = 'uz'

type Vars = Record<string, string | number>

/** Every user-facing string in the admin dashboard, keyed by name, one
 * variant per Language. Pages/components never inline Uzbek (or any
 * language) text directly — they call `t('key')` via useLanguage(). */
const STRINGS = {
  // ---- Layout / nav ----
  nav_dashboard: { uz: 'Boshqaruv paneli', en: 'Dashboard', ru: 'Панель управления' },
  nav_tenant: { uz: 'Dorixona', en: 'Pharmacy', ru: 'Аптека' },
  nav_tenant_settings: { uz: 'Sozlamalar', en: 'Settings', ru: 'Настройки' },
  nav_sellers: { uz: 'Sotuvchilar', en: 'Sellers', ru: 'Продавцы' },
  nav_broadcasts: { uz: 'Xabarnomalar', en: 'Broadcasts', ru: 'Рассылки' },
  nav_platform_broadcasts: {
    uz: 'Platforma xabarnomalari',
    en: 'Platform broadcasts',
    ru: 'Платформенные рассылки',
  },
  nav_reports: { uz: 'Hisobotlar', en: 'Reports', ru: 'Отчёты' },
  nav_group_label: { uz: "Bo'limlar", en: 'Sections', ru: 'Разделы' },
  page_title_dashboard: { uz: 'Boshqaruv paneli', en: 'Dashboard', ru: 'Панель управления' },
  page_title_tenant_detail: { uz: 'Dorixona tafsilotlari', en: 'Pharmacy details', ru: 'Данные аптеки' },
  page_title_tenant: { uz: 'Dorixona', en: 'Pharmacy', ru: 'Аптека' },
  page_title_tenant_settings: { uz: 'Sozlamalar', en: 'Settings', ru: 'Настройки' },
  page_title_sellers: { uz: 'Sotuvchilar', en: 'Sellers', ru: 'Продавцы' },
  page_title_broadcasts: { uz: 'Xabarnomalar', en: 'Broadcasts', ru: 'Рассылки' },
  page_title_platform_broadcasts: {
    uz: 'Platforma xabarnomalari',
    en: 'Platform broadcasts',
    ru: 'Платформенные рассылки',
  },
  page_title_reports: { uz: 'Hisobotlar', en: 'Reports', ru: 'Отчёты' },
  page_title_fallback: { uz: 'Pharmacy Cashback', en: 'Pharmacy Cashback', ru: 'Pharmacy Cashback' },
  logout: { uz: 'Chiqish', en: 'Log out', ru: 'Выйти' },
  logout_confirm_title: { uz: 'Tizimdan chiqasizmi?', en: 'Log out?', ru: 'Выйти из системы?' },
  logout_confirm_description: {
    uz: "Joriy sessiyangiz yakunlanadi va qayta kirish uchun login/parolni kiritishingiz kerak bo'ladi.",
    en: 'Your current session will end and you will need to enter your login/password to sign in again.',
    ru: 'Текущая сессия завершится, и для повторного входа потребуется ввести логин и пароль.',
  },
  language_label: { uz: 'Til', en: 'Language', ru: 'Язык' },
  menu_toggle_hint: { uz: 'Menyu', en: 'Menu', ru: 'Меню' },

  // ---- Profile drawer (self-service, every role) ----
  profile_link_label: { uz: 'Profil', en: 'Profile', ru: 'Профиль' },
  profile_heading: { uz: 'Mening profilim', en: 'My profile', ru: 'Мой профиль' },
  profile_change_photo: { uz: 'Rasm tanlash', en: 'Change photo', ru: 'Изменить фото' },
  profile_remove_photo: { uz: "Rasmni olib tashlash", en: 'Remove photo', ru: 'Удалить фото' },
  profile_avatar_invalid_type: {
    uz: 'Faqat rasm fayli yuklash mumkin.',
    en: 'Only an image file can be uploaded.',
    ru: 'Можно загружать только файл изображения.',
  },
  profile_avatar_too_large: {
    uz: 'Rasm hajmi {size}MB dan oshmasligi kerak.',
    en: 'The image must not exceed {size}MB.',
    ru: 'Размер изображения не должен превышать {size} МБ.',
  },
  profile_save_error: {
    uz: "Profilni saqlab bo'lmadi.",
    en: "Couldn't save the profile.",
    ru: 'Не удалось сохранить профиль.',
  },
  profile_load_error: {
    uz: "Profilni yuklab bo'lmadi.",
    en: "Couldn't load the profile.",
    ru: 'Не удалось загрузить профиль.',
  },
  field_role: { uz: 'Rol', en: 'Role', ru: 'Роль' },

  platform_branding_heading: {
    uz: 'Platforma nomi va logotipi',
    en: 'Platform name and logo',
    ru: 'Название и логотип платформы',
  },
  field_platform_name: { uz: 'Platforma nomi', en: 'Platform name', ru: 'Название платформы' },

  password_section_heading: {
    uz: 'Parolni almashtirish',
    en: 'Change password',
    ru: 'Смена пароля',
  },
  field_current_password: { uz: 'Joriy parol', en: 'Current password', ru: 'Текущий пароль' },
  field_new_password: { uz: 'Yangi parol', en: 'New password', ru: 'Новый пароль' },
  field_confirm_new_password: {
    uz: 'Yangi parolni takrorlang',
    en: 'Confirm new password',
    ru: 'Повторите новый пароль',
  },
  change_password_button: {
    uz: 'Parolni almashtirish',
    en: 'Change password',
    ru: 'Сменить пароль',
  },
  password_changed_toast: {
    uz: 'Parol muvaffaqiyatli almashtirildi.',
    en: 'Password changed successfully.',
    ru: 'Пароль успешно изменён.',
  },
  password_change_error: {
    uz: "Parolni almashtirib bo'lmadi.",
    en: "Couldn't change the password.",
    ru: 'Не удалось изменить пароль.',
  },
  password_mismatch_error: {
    uz: "Yangi parollar bir xil emas.",
    en: "The new passwords don't match.",
    ru: 'Новые пароли не совпадают.',
  },

  // ---- Shared confirm dialog defaults ----
  confirm_default: { uz: 'Tasdiqlash', en: 'Confirm', ru: 'Подтвердить' },
  cancel: { uz: 'Bekor qilish', en: 'Cancel', ru: 'Отмена' },
  in_progress: { uz: 'Bajarilmoqda…', en: 'Working…', ru: 'Выполняется…' },
  continue_button: { uz: 'Davom etish', en: 'Continue', ru: 'Продолжить' },
  delete_fully_confirm: {
    uz: "Ha, butunlay o'chirish",
    en: 'Yes, delete completely',
    ru: 'Да, удалить полностью',
  },
  delete_confirm: { uz: "Ha, o'chirish", en: 'Yes, delete', ru: 'Да, удалить' },

  // ---- DetailDrawer ----
  close: { uz: 'Yopish', en: 'Close', ru: 'Закрыть' },

  // ---- RichTextEditor ----
  rte_code_placeholder: { uz: 'kod', en: 'code', ru: 'код' },
  rte_bold: { uz: 'Qalin', en: 'Bold', ru: 'Жирный' },
  rte_italic: { uz: 'Kursiv', en: 'Italic', ru: 'Курсив' },
  rte_underline: { uz: 'Tagi chizilgan', en: 'Underline', ru: 'Подчёркнутый' },
  rte_strikethrough: { uz: 'Ustidan chizilgan', en: 'Strikethrough', ru: 'Зачёркнутый' },
  rte_code: { uz: 'Kod', en: 'Code', ru: 'Код' },
  rte_add_link: { uz: "Havola qo'shish", en: 'Add link', ru: 'Добавить ссылку' },
  rte_link_placeholder: { uz: 'https://...', en: 'https://...', ru: 'https://...' },
  rte_link_add: { uz: "Qo'shish", en: 'Add', ru: 'Добавить' },
  rte_link_cancel: { uz: 'Bekor', en: 'Cancel', ru: 'Отмена' },

  // ---- MediaAttach ----
  media_only_image_or_video: {
    uz: 'Faqat rasm yoki video fayl yuklash mumkin.',
    en: 'Only image or video files can be uploaded.',
    ru: 'Можно загружать только изображения или видео.',
  },
  media_image_too_large: {
    uz: 'Rasm hajmi 10MB dan oshmasligi kerak.',
    en: 'The image must not exceed 10MB.',
    ru: 'Размер изображения не должен превышать 10 МБ.',
  },
  media_video_too_large: {
    uz: 'Video hajmi 50MB dan oshmasligi kerak.',
    en: 'The video must not exceed 50MB.',
    ru: 'Размер видео не должен превышать 50 МБ.',
  },
  media_upload_failed: {
    uz: "Faylni yuklab bo'lmadi.",
    en: "Couldn't upload the file.",
    ru: 'Не удалось загрузить файл.',
  },
  media_uploading: { uz: 'Yuklanmoqda…', en: 'Uploading…', ru: 'Загрузка…' },
  media_size_mb: { uz: '{size} MB', en: '{size} MB', ru: '{size} МБ' },
  media_dropzone_instructions: {
    uz: 'Rasm yoki video yuklash uchun bosing yoki shu yerga tashlang',
    en: 'Click to upload an image or video, or drop it here',
    ru: 'Нажмите, чтобы загрузить изображение или видео, либо перетащите сюда',
  },
  media_hint_image: { uz: 'Rasm ≤10MB', en: 'Image ≤10MB', ru: 'Изображение ≤10 МБ' },
  media_hint_video: { uz: 'Video ≤50MB', en: 'Video ≤50MB', ru: 'Видео ≤50 МБ' },

  // ---- TelegramPreview ----
  telegram_preview_placeholder: {
    uz: 'Xabar shu yerda ko\'rinadi',
    en: 'Your message will appear here',
    ru: 'Сообщение появится здесь',
  },

  // ---- Charts ----
  chart_no_data: {
    uz: "Bu davrda ma'lumot yo'q.",
    en: 'No data for this period.',
    ru: 'Нет данных за этот период.',
  },
  chart_pie_aria_label: { uz: 'Statistika doira diagrammasi', en: 'Statistics pie chart', ru: 'Круговая диаграмма статистики' },
  chart_bar_aria_label: { uz: '{a} / {b} grafigi', en: '{a} / {b} chart', ru: 'график {a} / {b}' },

  // ---- LoginPage ----
  login_error_fallback: {
    uz: 'Tizimga kirishda xatolik yuz berdi.',
    en: 'An error occurred while signing in.',
    ru: 'Произошла ошибка при входе в систему.',
  },
  login_brand_subtitle: { uz: 'Boshqaruv paneli', en: 'Admin panel', ru: 'Панель управления' },
  login_heading: { uz: 'Tizimga kirish', en: 'Sign in', ru: 'Вход в систему' },
  login_subheading: {
    uz: "Davom etish uchun hisobingiz ma'lumotlarini kiriting.",
    en: 'Enter your account details to continue.',
    ru: 'Введите данные вашей учётной записи, чтобы продолжить.',
  },
  login_username: { uz: 'Foydalanuvchi nomi', en: 'Username', ru: 'Имя пользователя' },
  login_password: { uz: 'Parol', en: 'Password', ru: 'Пароль' },
  login_submitting: { uz: 'Kirilmoqda…', en: 'Signing in…', ru: 'Выполняется вход…' },
  login_submit: { uz: 'Kirish', en: 'Sign in', ru: 'Войти' },

  // ---- RoleRedirect ----
  role_redirect_no_panel_title: {
    uz: 'Bu rol uchun panel mavjud emas',
    en: 'No panel exists for this role',
    ru: 'Для этой роли панель недоступна',
  },
  role_redirect_seller_subtitle: {
    uz: 'Sotuvchilar bu boshqaruv panelidan emas, /seller/ sahifasidan foydalanadi.',
    en: 'Sellers use the /seller/ page, not this admin panel.',
    ru: 'Продавцы используют страницу /seller/, а не эту панель управления.',
  },
  role_redirect_no_role_subtitle: {
    uz: "Hisobingizga hali rol biriktirilmagan. Superadmin bilan bog'laning.",
    en: 'No role has been assigned to your account yet. Please contact a superadmin.',
    ru: 'Вашей учётной записи ещё не назначена роль. Обратитесь к суперадмину.',
  },

  // ---- Shared field labels / hints ----
  field_tenant_name: { uz: 'Dorixona nomi', en: 'Pharmacy name', ru: 'Название аптеки' },
  field_slug: {
    uz: 'Slug (URL uchun, masalan dorimed)',
    en: 'Slug (for the URL, e.g. dorimed)',
    ru: 'Slug (для URL, например dorimed)',
  },
  field_cashback_rate: { uz: 'Keshbek foizi (%)', en: 'Cashback rate (%)', ru: 'Ставка кешбэка (%)' },
  hint_rate_format: {
    uz: 'Butun foiz sonini kiriting: 10% uchun {ten} deb yozing, {zeroTen} emas.',
    en: 'Enter the whole percent number: for 10% write {ten}, not {zeroTen}.',
    ru: 'Введите целое число процента: для 10% пишите {ten}, а не {zeroTen}.',
  },
  field_login: { uz: 'Kirish uchun login', en: 'Login username', ru: 'Логин для входа' },
  field_password: { uz: 'Kirish uchun parol', en: 'Login password', ru: 'Пароль для входа' },
  field_branch: { uz: 'Filial', en: 'Branch', ru: 'Филиал' },
  field_branch_select_placeholder: { uz: 'Filialni tanlang', en: 'Choose a branch', ru: 'Выберите филиал' },
  field_address: { uz: 'Manzil', en: 'Address', ru: 'Адрес' },
  field_full_name: { uz: "To'liq ismi", en: 'Full name', ru: 'Полное имя' },
  field_phone: { uz: 'Telefon raqami', en: 'Phone number', ru: 'Номер телефона' },
  status_label: { uz: 'Holati', en: 'Status', ru: 'Статус' },
  fallback_dash: { uz: '—', en: '—', ru: '—' },
  saving: { uz: 'Saqlanmoqda…', en: 'Saving…', ru: 'Сохранение…' },
  save: { uz: 'Saqlash', en: 'Save', ru: 'Сохранить' },
  eyebrow_tenant: { uz: 'Dorixona', en: 'Pharmacy', ru: 'Аптека' },
  label_earned: { uz: "Yig'ilgan", en: 'Earned', ru: 'Начислено' },
  label_spent: { uz: 'Sarflangan', en: 'Spent', ru: 'Потрачено' },
  label_outstanding: { uz: 'Qoldiq', en: 'Outstanding', ru: 'Остаток' },
  sub_som: { uz: "so'm", en: 'UZS', ru: 'сум' },
  empty_no_transactions_yet: {
    uz: "Hozircha tranzaksiyalar yo'q",
    en: 'No transactions yet',
    ru: 'Пока нет транзакций',
  },

  // ---- DashboardPage (superadmin) ----
  dashboard_create_tenant_error: {
    uz: "Dorixonani yaratib bo'lmadi.",
    en: "Couldn't create the pharmacy.",
    ru: 'Не удалось создать аптеку.',
  },
  dashboard_creating: { uz: 'Yaratilmoqda…', en: 'Creating…', ru: 'Создание…' },
  dashboard_add_tenant_button: { uz: "Dorixona qo'shish", en: 'Add pharmacy', ru: 'Добавить аптеку' },
  dashboard_stat_total_tenants: { uz: 'Jami dorixonalar', en: 'Total pharmacies', ru: 'Всего аптек' },
  dashboard_stat_active_count: { uz: '{count} ta faol', en: '{count} active', ru: '{count} активных' },
  dashboard_stat_total_customers: { uz: 'Jami mijozlar', en: 'Total customers', ru: 'Всего клиентов' },
  dashboard_stat_customers_sub: {
    uz: "barcha dorixonalar bo'yicha",
    en: 'across all pharmacies',
    ru: 'по всем аптекам',
  },
  dashboard_stat_today_txns: { uz: 'Bugungi tranzaksiyalar', en: "Today's transactions", ru: 'Транзакции за сегодня' },
  dashboard_stat_today_txns_sub: { uz: 'barcha filiallarda', en: 'across all branches', ru: 'по всем филиалам' },
  dashboard_stat_total_liability: { uz: 'Umumiy majburiyat', en: 'Total liability', ru: 'Общие обязательства' },
  dashboard_stat_liability_sub: {
    uz: "mijozlar balansi, so'm",
    en: 'customer balances, UZS',
    ru: 'баланс клиентов, сум',
  },
  dashboard_all_tenants_heading: { uz: 'Barcha dorixonalar', en: 'All pharmacies', ru: 'Все аптеки' },
  dashboard_all_tenants_hint: {
    uz: "Batafsil ma'lumot uchun qatorni bosing.",
    en: 'Click a row for details.',
    ru: 'Нажмите на строку, чтобы увидеть подробности.',
  },
  dashboard_empty_title: { uz: "Hali birorta dorixona yo'q", en: 'No pharmacies yet', ru: 'Пока нет ни одной аптеки' },
  dashboard_empty_subtitle: {
    uz: "Pastdagi shakl orqali birinchi dorixonangizni qo'shing.",
    en: 'Use the form below to add your first pharmacy.',
    ru: 'Добавьте первую аптеку с помощью формы ниже.',
  },
  th_bot: { uz: 'Bot', en: 'Bot', ru: 'Бот' },
  th_tenant: { uz: 'Dorixona', en: 'Pharmacy', ru: 'Аптека' },
  th_customers: { uz: 'Mijozlar', en: 'Customers', ru: 'Клиенты' },
  th_active_30d: { uz: 'Faol (30 kun)', en: 'Active (30d)', ru: 'Активны (30 дн)' },
  th_today_txns: { uz: 'Bugungi tranzaksiyalar', en: "Today's transactions", ru: 'Транзакции за сегодня' },
  th_total_liability: { uz: 'Umumiy majburiyat', en: 'Total liability', ru: 'Общие обязательства' },
  th_status: { uz: 'Holati', en: 'Status', ru: 'Статус' },
  dashboard_add_new_tenant_heading: { uz: 'Yangi dorixona qo\'shish', en: 'Add a new pharmacy', ru: 'Добавить новую аптеку' },
  dashboard_add_new_tenant_hint: {
    uz: "Yaratilgach, botni ulash va filiallarni sozlash uchun dorixona sahifasiga o'tasiz.",
    en: "After creating it, you'll be taken to the pharmacy page to connect a bot and set up branches.",
    ru: 'После создания вы перейдёте на страницу аптеки, чтобы подключить бота и настроить филиалы.',
  },

  // ---- TenantDetailPage (superadmin) ----
  tenant_detail_bot_create_error: { uz: "Botni qo'shib bo'lmadi.", en: "Couldn't add the bot.", ru: 'Не удалось добавить бота.' },
  tenant_detail_token_rotate_error: {
    uz: "Tokenni almashtirib bo'lmadi.",
    en: "Couldn't rotate the token.",
    ru: 'Не удалось обновить токен.',
  },
  tenant_detail_no_bot: {
    uz: 'Bu dorixona uchun hali bot ulanmagan.',
    en: 'No bot has been connected for this pharmacy yet.',
    ru: 'Для этой аптеки ещё не подключён бот.',
  },
  field_bot_username: {
    uz: 'Bot foydalanuvchi nomi (masalan @dorimed_bot)',
    en: 'Bot username (e.g. @dorimed_bot)',
    ru: 'Имя пользователя бота (например @dorimed_bot)',
  },
  field_bot_token: { uz: 'Telegram bot tokeni', en: 'Telegram bot token', ru: 'Токен Telegram-бота' },
  tenant_detail_add_bot_button: { uz: "Bot qo'shish", en: 'Add bot', ru: 'Добавить бота' },
  tenant_detail_saved_toast: { uz: 'Saqlandi', en: 'Saved', ru: 'Сохранено' },
  tenant_detail_bot_label: { uz: 'Bot:', en: 'Bot:', ru: 'Бот:' },
  tenant_detail_status_label: { uz: 'Holati:', en: 'Status:', ru: 'Статус:' },
  tenant_detail_rotate_token_label: { uz: 'Tokenni almashtirish', en: 'Rotate token', ru: 'Заменить токен' },
  tenant_detail_new_token_placeholder: {
    uz: 'Yangi Telegram bot tokeni',
    en: 'New Telegram bot token',
    ru: 'Новый токен Telegram-бота',
  },
  tenant_detail_rotate_confirm_title: {
    uz: 'Tokenni almashtirasizmi?',
    en: 'Rotate the bot token?',
    ru: 'Заменить токен бота?',
  },
  tenant_detail_rotate_confirm_description: {
    uz: "Eski token darhol ishlamay qoladi va bot shu dorixonaga bog'langan holda qoladi. Agar yangi token boshqa botga tegishli bo'lsa, eski bot endi javob bermaydi — bu amalni ortga qaytarib bo'lmaydi.",
    en: "The old token stops working immediately and the bot stays linked to this pharmacy. If the new token belongs to a different bot, the old bot will stop responding — this action cannot be undone.",
    ru: "Старый токен перестанет работать немедленно, а бот останется привязан к этой аптеке. Если новый токен принадлежит другому боту, старый бот перестанет отвечать — это действие нельзя отменить.",
  },
  tenant_detail_delete_error: { uz: "Dorixonani o'chirib bo'lmadi.", en: "Couldn't delete the pharmacy.", ru: 'Не удалось удалить аптеку.' },
  tenant_detail_back_link: { uz: 'Barcha dorixonalar', en: 'All pharmacies', ru: 'Все аптеки' },
  tenant_detail_meta: {
    uz: '{slug} · {rate}% keshbek · {status}',
    en: '{slug} · {rate}% cashback · {status}',
    ru: '{slug} · кешбэк {rate}% · {status}',
  },
  tenant_detail_delete_button: { uz: "Dorixonani o'chirish", en: 'Delete pharmacy', ru: 'Удалить аптеку' },
  label_outstanding_liability: { uz: 'Qoldiq (majburiyat)', en: 'Outstanding (liability)', ru: 'Остаток (обязательства)' },
  label_branches: { uz: 'Filiallar', en: 'Branches', ru: 'Филиалы' },
  tenant_detail_bot_card_heading: { uz: 'Telegram bot', en: 'Telegram bot', ru: 'Telegram-бот' },
  tenant_detail_quota_card_heading: {
    uz: 'Xabarnoma limiti',
    en: 'Broadcast quota',
    ru: 'Лимит рассылок',
  },
  tenant_detail_quota_usage: {
    uz: 'Bu oy: {used} / {quota} ta xabarnoma yuborildi.',
    en: 'This month: {used} / {quota} broadcasts sent.',
    ru: 'В этом месяце: отправлено {used} / {quota} рассылок.',
  },
  tenant_detail_quota_save_error: {
    uz: "Limitni saqlab bo'lmadi.",
    en: "Couldn't save the quota.",
    ru: 'Не удалось сохранить лимит.',
  },
  field_broadcast_quota: {
    uz: 'Oylik xabarnoma limiti',
    en: 'Monthly broadcast quota',
    ru: 'Месячный лимит рассылок',
  },
  field_broadcast_quota_hint: {
    uz: "Bu dorixonaning barcha dorixona adminlari birgalikda oyiga shuncha xabarnoma yubora oladi. Bo'sh qoldiring — cheklanmagan.",
    en: 'All of this pharmacy’s admin logins share this monthly cap. Leave empty for unlimited.',
    ru: 'Все администраторы этой аптеки вместе могут отправить столько рассылок в месяц. Оставьте пустым — без ограничений.',
  },
  tenant_detail_branch_limit_card_heading: {
    uz: 'Filial limiti',
    en: 'Branch limit',
    ru: 'Лимит филиалов',
  },
  tenant_branch_limit_usage: {
    uz: '{used} / {limit} ta filial qo’shilgan.',
    en: '{used} / {limit} branches added.',
    ru: 'Добавлено {used} / {limit} филиалов.',
  },
  tenant_detail_branch_limit_save_error: {
    uz: "Filial limitini saqlab bo'lmadi.",
    en: "Couldn't save the branch limit.",
    ru: 'Не удалось сохранить лимит филиалов.',
  },
  field_branch_limit: {
    uz: 'Filiallar soni limiti',
    en: 'Branch count limit',
    ru: 'Лимит количества филиалов',
  },
  field_branch_limit_hint: {
    uz: "Bu dorixona jami nechta filial qo'sha olishini belgilaydi. Bo'sh qoldiring — cheklanmagan.",
    en: 'Sets the total number of branches this pharmacy can add. Leave empty for unlimited.',
    ru: 'Определяет общее число филиалов, которые может добавить эта аптека. Оставьте пустым — без ограничений.',
  },
  th_branch: { uz: 'Filial', en: 'Branch', ru: 'Филиал' },
  last_14_days: { uz: "So'nggi 14 kun", en: 'Last 14 days', ru: 'Последние 14 дней' },
  tenant_delete_step1_title: { uz: "Dorixonani o'chirasizmi?", en: 'Delete this pharmacy?', ru: 'Удалить аптеку?' },
  tenant_delete_step1_description: {
    uz: " dorixonasini o'chirsangiz, uning barcha filiallari, sotuvchilari va mijozlari endi tizimga kira olmaydi yoki mavjud bo'lmaydi.",
    en: " — deleting this pharmacy means all its branches, sellers, and customers will no longer be able to sign in or exist.",
    ru: ' — при удалении этой аптеки все её филиалы, продавцы и клиенты перестанут существовать или смогут входить в систему.',
  },
  delete_all_transactions_title: {
    uz: "Barcha tranzaksiyalar to'liq o'chib ketadi",
    en: 'All transactions will be permanently deleted',
    ru: 'Все транзакции будут полностью удалены',
  },
  tenant_detail_admins_card_heading: { uz: 'Dorixona adminlari', en: 'Pharmacy admins', ru: 'Администраторы аптеки' },
  tenant_detail_admins_empty_title: { uz: "Hozircha dorixona admini yo'q", en: 'No pharmacy admins yet', ru: 'Пока нет администраторов аптеки' },
  tenant_detail_admin_create_error: {
    uz: "Dorixona adminini yaratib bo'lmadi.",
    en: "Couldn't create the pharmacy admin.",
    ru: 'Не удалось создать администратора аптеки.',
  },
  tenant_detail_admin_delete_error: {
    uz: "Dorixona adminini o'chirib bo'lmadi.",
    en: "Couldn't delete the pharmacy admin.",
    ru: 'Не удалось удалить администратора аптеки.',
  },
  tenant_detail_add_admin_button: { uz: "Admin qo'shish", en: 'Add admin', ru: 'Добавить администратора' },
  admin_drawer_subtitle: { uz: 'Dorixona admini', en: 'Pharmacy admin', ru: 'Администратор аптеки' },
  admin_delete_button: { uz: "Adminni o'chirish", en: 'Delete admin', ru: 'Удалить администратора' },
  admin_delete_title: { uz: "Dorixona adminini o'chirasizmi?", en: 'Delete this pharmacy admin?', ru: 'Удалить администратора аптеки?' },
  tenant_delete_step2_description: {
    uz: " dorixonaning barcha tranzaksiya tarixi, botiga bog'liq narsalar bilan birga, butunlay o'chib ketadi. Bu amalni ortga qaytarib bo'lmaydi.",
    en: "'s entire transaction history, along with everything tied to its bot, will be permanently deleted. This action cannot be undone.",
    ru: ' — вся история транзакций вместе со всем, что связано с её ботом, будет безвозвратно удалена. Это действие нельзя отменить.',
  },

  // ---- TenantAdminPage (tenant admin) ----
  tenant_admin_rate_update_error: { uz: "Foizni yangilab bo'lmadi.", en: "Couldn't update the rate.", ru: 'Не удалось обновить ставку.' },
  tenant_admin_rate_updated_toast: { uz: 'Foiz yangilandi', en: 'Rate updated', ru: 'Ставка обновлена' },
  tenant_admin_save_rate_button: { uz: 'Foizni saqlash', en: 'Save rate', ru: 'Сохранить ставку' },
  tenant_admin_branch_create_error: { uz: "Filial yaratib bo'lmadi.", en: "Couldn't create the branch.", ru: 'Не удалось создать филиал.' },
  tenant_admin_branch_delete_error: { uz: "Filialni o'chirib bo'lmadi.", en: "Couldn't delete the branch.", ru: 'Не удалось удалить филиал.' },
  tenant_admin_branches_empty_title: { uz: "Hozircha filiallar yo'q", en: 'No branches yet', ru: 'Пока нет филиалов' },
  tenant_admin_branches_empty_subtitle: {
    uz: "Pastdagi shakl orqali birinchi filialni qo'shing.",
    en: 'Use the form below to add your first branch.',
    ru: 'Добавьте первый филиал с помощью формы ниже.',
  },
  th_name: { uz: 'Nomi', en: 'Name', ru: 'Название' },
  field_new_branch_name: { uz: 'Yangi filial nomi', en: 'New branch name', ru: 'Название нового филиала' },
  tenant_admin_add_branch_button: { uz: "Filial qo'shish", en: 'Add branch', ru: 'Добавить филиал' },
  branch_drawer_subtitle: { uz: 'Filial', en: 'Branch', ru: 'Филиал' },
  branch_delete_button: { uz: "Filialni o'chirish", en: 'Delete branch', ru: 'Удалить филиал' },
  branch_delete_step1_title: { uz: "Filialni o'chirasizmi?", en: 'Delete this branch?', ru: 'Удалить филиал?' },
  branch_delete_step1_description: {
    uz: " filialidagi sotuvchilar va filial admini endi tizimga kira olmaydi.",
    en: "'s sellers and branch admin will no longer be able to sign in.",
    ru: ' — продавцы и администратор этого филиала больше не смогут входить в систему.',
  },
  branch_delete_step2_description: {
    uz: " filialidagi barcha tranzaksiya tarixi butunlay o'chib ketadi. Bu amalni ortga qaytarib bo'lmaydi.",
    en: "'s entire transaction history will be permanently deleted. This action cannot be undone.",
    ru: ' — вся история транзакций этого филиала будет безвозвратно удалена. Это действие нельзя отменить.',
  },
  tenant_admin_manager_delete_error: {
    uz: "Filial adminini o'chirib bo'lmadi.",
    en: "Couldn't delete the branch admin.",
    ru: 'Не удалось удалить администратора филиала.',
  },
  tenant_admin_manager_create_error: {
    uz: "Filial adminini yaratib bo'lmadi.",
    en: "Couldn't create the branch admin.",
    ru: 'Не удалось создать администратора филиала.',
  },
  tenant_admin_managers_empty_title: {
    uz: "Hozircha filial adminlari yo'q",
    en: 'No branch admins yet',
    ru: 'Пока нет администраторов филиалов',
  },
  th_login: { uz: 'Login', en: 'Login', ru: 'Логин' },
  tenant_admin_add_manager_button: {
    uz: "Filial adminini qo'shish",
    en: 'Add branch admin',
    ru: 'Добавить администратора филиала',
  },
  manager_drawer_subtitle: { uz: 'Filial admini', en: 'Branch admin', ru: 'Администратор филиала' },
  manager_delete_button: { uz: "Filial adminini o'chirish", en: 'Delete admin', ru: 'Удалить администратора' },
  manager_delete_title: { uz: "Filial adminini o'chirasizmi?", en: 'Delete this branch admin?', ru: 'Удалить администратора филиала?' },
  login_will_lose_access: {
    uz: " endi tizimga kira olmaydi. Bu amalni ortga qaytarib bo'lmaydi.",
    en: ' will no longer be able to sign in. This action cannot be undone.',
    ru: ' больше не сможет входить в систему. Это действие нельзя отменить.',
  },
  tenant_admin_identity_card_heading: {
    uz: 'Dorixona nomi va logotipi',
    en: 'Pharmacy name and logo',
    ru: 'Название и логотип аптеки',
  },
  tenant_admin_identity_save_error: {
    uz: "Dorixona ma'lumotlarini saqlab bo'lmadi.",
    en: "Couldn't save the pharmacy's details.",
    ru: 'Не удалось сохранить данные аптеки.',
  },
  tenant_admin_change_logo: { uz: 'Logotip tanlash', en: 'Change logo', ru: 'Изменить логотип' },
  tenant_admin_remove_logo: {
    uz: 'Logotipni olib tashlash',
    en: 'Remove logo',
    ru: 'Удалить логотип',
  },
  tenant_admin_rate_card_heading: { uz: 'Foizni sozlash', en: 'Set the rate', ru: 'Настройка ставки' },
  tenant_admin_quota_card_heading: {
    uz: 'Xabarnoma limiti',
    en: 'Broadcast quota',
    ru: 'Лимит рассылок',
  },
  section_heading_branch_managers: { uz: 'Filial adminlari', en: 'Branch admins', ru: 'Администраторы филиалов' },
  tenant_admin_add_branch_card_heading: {
    uz: "Filial qo'shish",
    en: 'Add a branch',
    ru: 'Добавить филиал',
  },
  tenant_admin_assign_manager_card_heading: {
    uz: 'Filialga admin biriktirish',
    en: 'Assign an admin to a branch',
    ru: 'Назначить администратора филиалу',
  },

  // ---- SellersPage ----
  sellers_delete_error: { uz: "Sotuvchini o'chirib bo'lmadi.", en: "Couldn't delete the seller.", ru: 'Не удалось удалить продавца.' },
  sellers_create_error: { uz: "Sotuvchi yaratib bo'lmadi.", en: "Couldn't create the seller.", ru: 'Не удалось создать продавца.' },
  sellers_stat_total: { uz: 'Jami sotuvchilar', en: 'Total sellers', ru: 'Всего продавцов' },
  sellers_stat_active: { uz: 'Faol sotuvchilar', en: 'Active sellers', ru: 'Активные продавцы' },
  sellers_stat_inactive_sub: { uz: '{count} nofaol', en: '{count} inactive', ru: '{count} неактивных' },
  sellers_heading: { uz: 'Sotuvchilar', en: 'Sellers', ru: 'Продавцы' },
  sellers_empty_title: { uz: "Hozircha sotuvchilar yo'q", en: 'No sellers yet', ru: 'Пока нет продавцов' },
  th_full_name: { uz: 'Ismi', en: 'Name', ru: 'Имя' },
  th_phone: { uz: 'Telefon', en: 'Phone', ru: 'Телефон' },
  th_daily_limit: { uz: 'Kunlik limit', en: 'Daily limit', ru: 'Дневной лимит' },
  sellers_add_heading: { uz: "Sotuvchi qo'shish", en: 'Add seller', ru: 'Добавить продавца' },
  phone_placeholder: { uz: '+998901234567', en: '+998901234567', ru: '+998901234567' },
  seller_drawer_subtitle: { uz: 'Sotuvchi', en: 'Seller', ru: 'Продавец' },
  seller_delete_button: { uz: "Sotuvchini o'chirish", en: 'Delete seller', ru: 'Удалить продавца' },
  unlimited: { uz: 'Cheklanmagan', en: 'Unlimited', ru: 'Без ограничений' },
  seller_delete_title: { uz: "Sotuvchini o'chirasizmi?", en: 'Delete this seller?', ru: 'Удалить продавца?' },

  // ---- BroadcastsPage ----
  broadcast_media_still_uploading: {
    uz: "Fayl hali yuklanmoqda — birozdan so'ng qayta urining.",
    en: 'The file is still uploading — please try again shortly.',
    ru: 'Файл ещё загружается — попробуйте снова через некоторое время.',
  },
  broadcast_over_char_limit: {
    uz: 'Xabar matni {limit} belgidan oshmasligi kerak (hozir: {length}).',
    en: 'The message text must not exceed {limit} characters (currently: {length}).',
    ru: 'Текст сообщения не должен превышать {limit} символов (сейчас: {length}).',
  },
  broadcast_title_required: { uz: 'Sarlavha kiritilishi shart.', en: 'A title is required.', ru: 'Заголовок обязателен.' },
  broadcast_create_error: { uz: "Xabarnoma yaratib bo'lmadi.", en: "Couldn't create the broadcast.", ru: 'Не удалось создать рассылку.' },
  broadcast_send_error: { uz: "Xabarnomani yuborib bo'lmadi.", en: "Couldn't send the broadcast.", ru: 'Не удалось отправить рассылку.' },
  broadcasts_heading: { uz: 'Xabarnomalar', en: 'Broadcasts', ru: 'Рассылки' },
  broadcasts_empty_title: { uz: "Hozircha xabarnomalar yo'q", en: 'No broadcasts yet', ru: 'Пока нет рассылок' },
  broadcasts_empty_subtitle: {
    uz: "Pastdagi shakl orqali birinchi xabarnomani yarating.",
    en: 'Use the form below to create your first broadcast.',
    ru: 'Создайте первую рассылку с помощью формы ниже.',
  },
  th_title: { uz: 'Sarlavha', en: 'Title', ru: 'Заголовок' },
  th_media: { uz: 'Media', en: 'Media', ru: 'Медиа' },
  th_sent: { uz: 'Yuborildi', en: 'Sent', ru: 'Отправлено' },
  th_failed: { uz: 'Muvaffaqiyatsiz', en: 'Failed', ru: 'Не удалось' },
  th_tenants: { uz: 'Dorixonalar', en: 'Pharmacies', ru: 'Аптеки' },
  media_type_image: { uz: 'Rasm', en: 'Image', ru: 'Изображение' },
  media_type_video: { uz: 'Video', en: 'Video', ru: 'Видео' },

  // ---- SuperadminBroadcastsPage ----
  platform_broadcasts_heading: {
    uz: 'Platforma xabarnomalari',
    en: 'Platform broadcasts',
    ru: 'Платформенные рассылки',
  },
  platform_broadcasts_description: {
    uz: "Bu yerdan yuborilgan xabarnoma barcha faol dorixonalarning mijozlariga, har birining o'z boti orqali yuboriladi.",
    en: 'A broadcast sent from here goes out to every active pharmacy’s customers, through each pharmacy’s own bot.',
    ru: 'Рассылка, отправленная отсюда, уходит клиентам всех активных аптек через бота каждой аптеки.',
  },
  platform_broadcast_new_description: {
    uz: "Barcha dorixonalarga yuboriladi — dorixonalarning oylik xabarnoma limitiga ta'sir qilmaydi.",
    en: 'Sent to every pharmacy — never counts against any pharmacy’s monthly broadcast quota.',
    ru: 'Отправляется всем аптекам — не учитывается в месячном лимите рассылок ни одной аптеки.',
  },
  platform_broadcast_send_now_button: {
    uz: 'Barchaga yuborish',
    en: 'Send to everyone',
    ru: 'Отправить всем',
  },
  broadcast_sending: { uz: 'Yuborilmoqda…', en: 'Sending…', ru: 'Отправка…' },
  broadcast_send_button: { uz: 'Yuborish', en: 'Send', ru: 'Отправить' },
  broadcast_new_heading: { uz: 'Yangi xabarnoma', en: 'New broadcast', ru: 'Новая рассылка' },
  broadcast_new_description: {
    uz: "Xabarnoma ushbu dorixonaning botiga obuna bo'lgan barcha faol mijozlarga yuboriladi. Filial bo'yicha yo'naltirish hozircha mavjud emas — mijozlar aniq bir filialga bog'lanmagan (kelajakdagi imkoniyat).",
    en: "The broadcast will be sent to all active customers subscribed to this pharmacy's bot. Targeting by branch isn't available yet — customers aren't tied to a specific branch (a future feature).",
    ru: 'Рассылка будет отправлена всем активным клиентам, подписанным на бота этой аптеки. Таргетинг по филиалам пока недоступен — клиенты не привязаны к конкретному филиалу (будущая возможность).',
  },
  broadcast_title_placeholder: {
    uz: 'Masalan: Dam olish kunlari aksiyasi',
    en: 'E.g.: Weekend promotion',
    ru: 'Например: Акция выходного дня',
  },
  field_text: { uz: 'Matn', en: 'Text', ru: 'Текст' },
  broadcast_text_placeholder: {
    uz: 'Xabar matnini kiriting…',
    en: 'Enter the message text…',
    ru: 'Введите текст сообщения…',
  },
  broadcast_char_counter: { uz: '{length} / {limit} belgi', en: '{length} / {limit} characters', ru: '{length} / {limit} символов' },
  broadcast_media_attached_suffix: {
    uz: ' (media biriktirilgan)',
    en: ' (media attached)',
    ru: ' (медиа прикреплено)',
  },
  field_media_optional: { uz: 'Rasm yoki video (ixtiyoriy)', en: 'Image or video (optional)', ru: 'Изображение или видео (необязательно)' },
  broadcast_save_draft_button: { uz: 'Qoralama sifatida saqlash', en: 'Save as draft', ru: 'Сохранить как черновик' },
  broadcast_send_now_button: { uz: 'Hoziroq yuborish', en: 'Send now', ru: 'Отправить сейчас' },
  broadcast_preview_label: {
    uz: "Telegram'da qanday ko'rinishi",
    en: 'How it looks in Telegram',
    ru: 'Как это выглядит в Telegram',
  },

  // ---- ReportsPage ----
  txn_type_reversal: { uz: 'Bekor qilish', en: 'Reversal', ru: 'Отмена' },
  txn_type_no_cashback: { uz: 'Retsept (keshbeksiz)', en: 'Prescription (no cashback)', ru: 'Рецепт (без кешбэка)' },
  txn_type_earn_and_spend: { uz: 'Sotuv + ishlatish', en: 'Sale + redemption', ru: 'Продажа + списание' },
  txn_type_spend: { uz: 'Ballarni ishlatish', en: 'Redeem points', ru: 'Использование баллов' },
  txn_type_sale: { uz: 'Sotuv', en: 'Sale', ru: 'Продажа' },
  reports_seller_empty_title: {
    uz: 'Bu sotuvchida hali tranzaksiyalar yo\'q',
    en: 'This seller has no transactions yet',
    ru: 'У этого продавца пока нет транзакций',
  },
  th_datetime: { uz: 'Sana va vaqt', en: 'Date & time', ru: 'Дата и время' },
  th_customer_phone: { uz: 'Mijoz telefoni', en: "Customer's phone", ru: 'Телефон клиента' },
  th_check_amount: { uz: 'Chek summasi', en: 'Check amount', ru: 'Сумма чека' },
  th_cash_paid: { uz: "Naqd to'langan", en: 'Cash paid', ru: 'Оплачено наличными' },
  th_cashback_earned: { uz: 'Keshbek qo\'shildi', en: 'Cashback earned', ru: 'Начислен кешбэк' },
  th_cashback_spent: { uz: 'Keshbek ishlatildi', en: 'Cashback redeemed', ru: 'Списан кешбэк' },
  th_type: { uz: 'Turi', en: 'Type', ru: 'Тип' },
  status_reversed: { uz: 'Bekor qilingan', en: 'Reversed', ru: 'Отменена' },
  status_flagged: { uz: 'Shubhali', en: 'Flagged', ru: 'Подозрительная' },
  reports_overall_stats_heading: { uz: 'Umumiy statistika', en: 'Overall statistics', ru: 'Общая статистика' },
  reports_pie_total_sales: { uz: 'Jami savdo', en: 'Total sales', ru: 'Всего продаж' },
  reports_pie_cashback_given: { uz: 'Berilgan keshbek', en: 'Cashback given', ru: 'Начислено кешбэка' },
  reports_pie_cashback_used: { uz: 'Ishlatilgan keshbek', en: 'Cashback redeemed', ru: 'Использовано кешбэка' },
  sub_som_total: { uz: "so'm, jami", en: 'UZS, total', ru: 'сум, всего' },
  reports_stat_flagged: { uz: 'Shubhali tranzaksiyalar', en: 'Flagged transactions', ru: 'Подозрительные транзакции' },
  reports_load_more: { uz: "Yana yuklash", en: 'Load more', ru: 'Загрузить ещё' },
  reports_loading_more: { uz: 'Yuklanmoqda...', en: 'Loading...', ru: 'Загрузка...' },
  reports_stat_flagged_sub: { uz: 'barcha sotuvchilar bo\'yicha', en: 'across all sellers', ru: 'по всем продавцам' },
  reports_sellers_heading: { uz: 'Sotuvchilar', en: 'Sellers', ru: 'Продавцы' },
  reports_sellers_description: {
    uz: "Tranzaksiyalar soniga nisbatan yuqori shubhali (bayroqlangan) soni firibgarlik belgisi hisoblanadi. To'liq tarixni ko'rish uchun sotuvchi qatorini bosing.",
    en: 'A high number of flagged transactions relative to total transaction count is a sign of possible fraud. Click a seller row to see their full history.',
    ru: 'Высокая доля помеченных транзакций относительно общего числа транзакций может указывать на мошенничество. Нажмите на строку продавца, чтобы увидеть полную историю.',
  },
  th_seller: { uz: 'Sotuvchi', en: 'Seller', ru: 'Продавец' },
  th_transactions: { uz: 'Tranzaksiyalar', en: 'Transactions', ru: 'Транзакции' },
  th_average_check: { uz: "O'rtacha chek", en: 'Average check', ru: 'Средний чек' },
  th_flagged: { uz: 'Shubhali', en: 'Flagged', ru: 'Подозрительные' },
  reports_branches_heading: {
    uz: "Filiallar — yig'ilgan / sarflangan / qoldiq",
    en: 'Branches — earned / spent / outstanding',
    ru: 'Филиалы — начислено / потрачено / остаток',
  },
  last_30_days: { uz: "So'nggi 30 kun", en: 'Last 30 days', ru: 'Последние 30 дней' },

  // ---- api/client.ts (used outside React, via translate()) ----
  api_request_failed: {
    uz: "So'rov bajarilmadi (holat: {status})",
    en: 'The request failed (status: {status})',
    ru: 'Запрос не выполнен (статус: {status})',
  },
  api_not_logged_in: { uz: 'Tizimga kirilmagan', en: 'Not signed in', ru: 'Вход не выполнен' },

  // ---- lib/labels.ts ----
  role_superadmin: { uz: 'Superadmin', en: 'Superadmin', ru: 'Суперадмин' },
  role_tenant_admin: { uz: 'Dorixona admini', en: 'Pharmacy admin', ru: 'Администратор аптеки' },
  role_branch_manager: { uz: 'Filial admini', en: 'Branch admin', ru: 'Администратор филиала' },
  role_seller: { uz: 'Sotuvchi', en: 'Seller', ru: 'Продавец' },
  role_unassigned: {
    uz: 'Rol tayinlanmagan',
    en: 'No role assigned',
    ru: 'Роль не назначена',
  },
  status_active: { uz: 'Faol', en: 'Active', ru: 'Активен' },
  status_inactive: { uz: 'Faol emas', en: 'Inactive', ru: 'Неактивен' },
  broadcast_status_draft: { uz: 'Qoralama', en: 'Draft', ru: 'Черновик' },
  broadcast_status_sending: { uz: 'Yuborilmoqda', en: 'Sending', ru: 'Отправляется' },
  broadcast_status_sent: { uz: 'Yuborildi', en: 'Sent', ru: 'Отправлено' },
  broadcast_status_failed: { uz: 'Xatolik', en: 'Failed', ru: 'Ошибка' },
} satisfies Record<string, Record<Language, string>>

export type StringKey = keyof typeof STRINGS
export type TFunction = (key: StringKey, vars?: Vars) => string

function interpolate(template: string, vars?: Vars): string {
  if (!vars) return template
  return Object.entries(vars).reduce(
    (acc, [key, value]) => acc.replaceAll(`{${key}}`, String(value)),
    template
  )
}

/** Non-hook translation, for use outside React components (e.g. api/client.ts).
 * Falls back to the raw key instead of throwing when `key` isn't a real
 * STRINGS entry — callers sometimes derive it from a lookup table keyed by
 * a value that can legitimately fall outside the cases anyone thought to
 * handle (e.g. a role of "unassigned" with no ROLE_KEYS entry — see
 * lib/labels.ts). A missing translation should read as a rough label, not
 * take the whole page down. */
export function translate(language: Language, key: StringKey, vars?: Vars): string {
  const entry = STRINGS[key]
  if (!entry) {
    if (import.meta.env.DEV) console.warn(`translate(): no STRINGS entry for key "${String(key)}"`)
    return String(key)
  }
  return interpolate(entry[language] ?? entry[DEFAULT_LANGUAGE], vars)
}

export function getStoredLanguage(): Language {
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored === 'uz' || stored === 'en' || stored === 'ru' ? stored : DEFAULT_LANGUAGE
}

interface LanguageContextValue {
  language: Language
  setLanguage: (language: Language) => void
  t: TFunction
}

const LanguageContext = createContext<LanguageContextValue | null>(null)

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(getStoredLanguage)

  const setLanguage = (next: Language) => {
    setLanguageState(next)
    localStorage.setItem(STORAGE_KEY, next)
  }

  const value = useMemo<LanguageContextValue>(
    () => ({
      language,
      setLanguage,
      t: (key, vars) => translate(language, key, vars),
    }),
    [language]
  )

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext)
  if (!ctx) throw new Error('useLanguage must be used within LanguageProvider')
  return ctx
}
