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
  nav_tenant: { uz: 'Tarmoq', en: 'Network', ru: 'Сеть' },
  nav_sellers: { uz: 'Sotuvchilar', en: 'Sellers', ru: 'Продавцы' },
  nav_broadcasts: { uz: 'Xabarnomalar', en: 'Broadcasts', ru: 'Рассылки' },
  nav_reports: { uz: 'Hisobotlar', en: 'Reports', ru: 'Отчёты' },
  nav_group_label: { uz: "Bo'limlar", en: 'Sections', ru: 'Разделы' },
  page_title_dashboard: { uz: 'Boshqaruv paneli', en: 'Dashboard', ru: 'Панель управления' },
  page_title_tenant_detail: { uz: 'Tarmoq tafsilotlari', en: 'Network details', ru: 'Данные сети' },
  page_title_tenant: { uz: 'Tarmoq sozlamalari', en: 'Network settings', ru: 'Настройки сети' },
  page_title_sellers: { uz: 'Sotuvchilar', en: 'Sellers', ru: 'Продавцы' },
  page_title_broadcasts: { uz: 'Xabarnomalar', en: 'Broadcasts', ru: 'Рассылки' },
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
  field_tenant_name: { uz: 'Tarmoq nomi', en: 'Network name', ru: 'Название сети' },
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
  eyebrow_tenant: { uz: 'Tarmoq', en: 'Network', ru: 'Сеть' },
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
    uz: "Tarmoqni yaratib bo'lmadi.",
    en: "Couldn't create the network.",
    ru: 'Не удалось создать сеть.',
  },
  dashboard_creating: { uz: 'Yaratilmoqda…', en: 'Creating…', ru: 'Создание…' },
  dashboard_add_tenant_button: { uz: "Tarmoq qo'shish", en: 'Add network', ru: 'Добавить сеть' },
  dashboard_stat_total_tenants: { uz: 'Jami tarmoqlar', en: 'Total networks', ru: 'Всего сетей' },
  dashboard_stat_active_count: { uz: '{count} ta faol', en: '{count} active', ru: '{count} активных' },
  dashboard_stat_total_customers: { uz: 'Jami mijozlar', en: 'Total customers', ru: 'Всего клиентов' },
  dashboard_stat_customers_sub: {
    uz: "barcha tarmoqlar bo'yicha",
    en: 'across all networks',
    ru: 'по всем сетям',
  },
  dashboard_stat_today_txns: { uz: 'Bugungi tranzaksiyalar', en: "Today's transactions", ru: 'Транзакции за сегодня' },
  dashboard_stat_today_txns_sub: { uz: 'barcha filiallarda', en: 'across all branches', ru: 'по всем филиалам' },
  dashboard_stat_total_liability: { uz: 'Umumiy majburiyat', en: 'Total liability', ru: 'Общие обязательства' },
  dashboard_stat_liability_sub: {
    uz: "mijozlar balansi, so'm",
    en: 'customer balances, UZS',
    ru: 'баланс клиентов, сум',
  },
  dashboard_all_tenants_heading: { uz: 'Barcha tarmoqlar', en: 'All networks', ru: 'Все сети' },
  dashboard_all_tenants_hint: {
    uz: "Batafsil ma'lumot uchun qatorni bosing.",
    en: 'Click a row for details.',
    ru: 'Нажмите на строку, чтобы увидеть подробности.',
  },
  dashboard_empty_title: { uz: "Hali birorta tarmoq yo'q", en: 'No networks yet', ru: 'Пока нет ни одной сети' },
  dashboard_empty_subtitle: {
    uz: "Pastdagi shakl orqali birinchi dorixona tarmog'ini qo'shing.",
    en: 'Use the form below to add your first pharmacy network.',
    ru: 'Добавьте первую сеть аптек с помощью формы ниже.',
  },
  th_bot: { uz: 'Bot', en: 'Bot', ru: 'Бот' },
  th_tenant: { uz: 'Tarmoq', en: 'Network', ru: 'Сеть' },
  th_customers: { uz: 'Mijozlar', en: 'Customers', ru: 'Клиенты' },
  th_active_30d: { uz: 'Faol (30 kun)', en: 'Active (30d)', ru: 'Активны (30 дн)' },
  th_today_txns: { uz: 'Bugungi tranzaksiyalar', en: "Today's transactions", ru: 'Транзакции за сегодня' },
  th_total_liability: { uz: 'Umumiy majburiyat', en: 'Total liability', ru: 'Общие обязательства' },
  th_status: { uz: 'Holati', en: 'Status', ru: 'Статус' },
  dashboard_add_new_tenant_heading: { uz: 'Yangi tarmoq qo\'shish', en: 'Add a new network', ru: 'Добавить новую сеть' },
  dashboard_add_new_tenant_hint: {
    uz: "Yaratilgach, botni ulash va filiallarni sozlash uchun tarmoq sahifasiga o'tasiz.",
    en: "After creating it, you'll be taken to the network page to connect a bot and set up branches.",
    ru: 'После создания вы перейдёте на страницу сети, чтобы подключить бота и настроить филиалы.',
  },

  // ---- TenantDetailPage (superadmin) ----
  tenant_detail_bot_create_error: { uz: "Botni qo'shib bo'lmadi.", en: "Couldn't add the bot.", ru: 'Не удалось добавить бота.' },
  tenant_detail_token_rotate_error: {
    uz: "Tokenni almashtirib bo'lmadi.",
    en: "Couldn't rotate the token.",
    ru: 'Не удалось обновить токен.',
  },
  tenant_detail_no_bot: {
    uz: 'Bu tarmoq uchun hali bot ulanmagan.',
    en: 'No bot has been connected for this network yet.',
    ru: 'Для этой сети ещё не подключён бот.',
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
    uz: "Eski token darhol ishlamay qoladi va bot shu tarmoqqa bog'langan holda qoladi. Agar yangi token boshqa botga tegishli bo'lsa, eski bot endi javob bermaydi — bu amalni ortga qaytarib bo'lmaydi.",
    en: "The old token stops working immediately and the bot stays linked to this network. If the new token belongs to a different bot, the old bot will stop responding — this action cannot be undone.",
    ru: "Старый токен перестанет работать немедленно, а бот останется привязан к этой сети. Если новый токен принадлежит другому боту, старый бот перестанет отвечать — это действие нельзя отменить.",
  },
  tenant_detail_delete_error: { uz: "Tarmoqni o'chirib bo'lmadi.", en: "Couldn't delete the network.", ru: 'Не удалось удалить сеть.' },
  tenant_detail_back_link: { uz: 'Barcha tarmoqlar', en: 'All networks', ru: 'Все сети' },
  tenant_detail_meta: {
    uz: '{slug} · {rate}% keshbek · {status}',
    en: '{slug} · {rate}% cashback · {status}',
    ru: '{slug} · кешбэк {rate}% · {status}',
  },
  tenant_detail_delete_button: { uz: "Tarmoqni o'chirish", en: 'Delete network', ru: 'Удалить сеть' },
  label_outstanding_liability: { uz: 'Qoldiq (majburiyat)', en: 'Outstanding (liability)', ru: 'Остаток (обязательства)' },
  label_branches: { uz: 'Filiallar', en: 'Branches', ru: 'Филиалы' },
  tenant_detail_bot_card_heading: { uz: 'Telegram bot', en: 'Telegram bot', ru: 'Telegram-бот' },
  th_branch: { uz: 'Filial', en: 'Branch', ru: 'Филиал' },
  last_14_days: { uz: "So'nggi 14 kun", en: 'Last 14 days', ru: 'Последние 14 дней' },
  tenant_delete_step1_title: { uz: "Tarmoqni o'chirasizmi?", en: 'Delete this network?', ru: 'Удалить сеть?' },
  tenant_delete_step1_description: {
    uz: " tarmog'ini o'chirsangiz, uning barcha filiallari, sotuvchilari va mijozlari endi tizimga kira olmaydi yoki mavjud bo'lmaydi.",
    en: " — deleting this network means all its branches, sellers, and customers will no longer be able to sign in or exist.",
    ru: ' — при удалении этой сети все её филиалы, продавцы и клиенты перестанут существовать или смогут входить в систему.',
  },
  delete_all_transactions_title: {
    uz: "Barcha tranzaksiyalar to'liq o'chib ketadi",
    en: 'All transactions will be permanently deleted',
    ru: 'Все транзакции будут полностью удалены',
  },
  tenant_delete_step2_description: {
    uz: " tarmog'ining barcha tranzaksiya tarixi, botiga bog'liq narsalar bilan birga, butunlay o'chib ketadi. Bu amalni ortga qaytarib bo'lmaydi.",
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
    uz: " filialidagi sotuvchilar va filial menejeri endi tizimga kira olmaydi.",
    en: "'s sellers and branch manager will no longer be able to sign in.",
    ru: ' — продавцы и менеджер этого филиала больше не смогут входить в систему.',
  },
  branch_delete_step2_description: {
    uz: " filialidagi barcha tranzaksiya tarixi butunlay o'chib ketadi. Bu amalni ortga qaytarib bo'lmaydi.",
    en: "'s entire transaction history will be permanently deleted. This action cannot be undone.",
    ru: ' — вся история транзакций этого филиала будет безвозвратно удалена. Это действие нельзя отменить.',
  },
  tenant_admin_manager_delete_error: {
    uz: "Filial menejerini o'chirib bo'lmadi.",
    en: "Couldn't delete the branch manager.",
    ru: 'Не удалось удалить менеджера филиала.',
  },
  tenant_admin_manager_create_error: {
    uz: "Filial menejerini yaratib bo'lmadi.",
    en: "Couldn't create the branch manager.",
    ru: 'Не удалось создать менеджера филиала.',
  },
  tenant_admin_managers_empty_title: {
    uz: "Hozircha filial menejerlari yo'q",
    en: 'No branch managers yet',
    ru: 'Пока нет менеджеров филиалов',
  },
  th_login: { uz: 'Login', en: 'Login', ru: 'Логин' },
  tenant_admin_add_manager_button: {
    uz: "Filial menejerini qo'shish",
    en: 'Add branch manager',
    ru: 'Добавить менеджера филиала',
  },
  manager_drawer_subtitle: { uz: 'Filial menejeri', en: 'Branch manager', ru: 'Менеджер филиала' },
  manager_delete_button: { uz: "Menejerni o'chirish", en: 'Delete manager', ru: 'Удалить менеджера' },
  manager_delete_title: { uz: "Filial menejerini o'chirasizmi?", en: 'Delete this branch manager?', ru: 'Удалить менеджера филиала?' },
  login_will_lose_access: {
    uz: " endi tizimga kira olmaydi. Bu amalni ortga qaytarib bo'lmaydi.",
    en: ' will no longer be able to sign in. This action cannot be undone.',
    ru: ' больше не сможет входить в систему. Это действие нельзя отменить.',
  },
  tenant_admin_rate_card_heading: { uz: 'Foizni sozlash', en: 'Set the rate', ru: 'Настройка ставки' },
  section_heading_branch_managers: { uz: 'Filial menejerlari', en: 'Branch managers', ru: 'Менеджеры филиалов' },

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
  media_type_image: { uz: 'Rasm', en: 'Image', ru: 'Изображение' },
  media_type_video: { uz: 'Video', en: 'Video', ru: 'Видео' },
  broadcast_sending: { uz: 'Yuborilmoqda…', en: 'Sending…', ru: 'Отправка…' },
  broadcast_send_button: { uz: 'Yuborish', en: 'Send', ru: 'Отправить' },
  broadcast_new_heading: { uz: 'Yangi xabarnoma', en: 'New broadcast', ru: 'Новая рассылка' },
  broadcast_new_description: {
    uz: "Xabarnoma ushbu tarmoqning botiga obuna bo'lgan barcha faol mijozlarga yuboriladi. Filial bo'yicha yo'naltirish hozircha mavjud emas — mijozlar aniq bir filialga bog'lanmagan (kelajakdagi imkoniyat).",
    en: "The broadcast will be sent to all active customers subscribed to this network's bot. Targeting by branch isn't available yet — customers aren't tied to a specific branch (a future feature).",
    ru: 'Рассылка будет отправлена всем активным клиентам, подписанным на бота этой сети. Таргетинг по филиалам пока недоступен — клиенты не привязаны к конкретному филиалу (будущая возможность).',
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
  role_tenant_admin: { uz: 'Tarmoq admini', en: 'Network admin', ru: 'Администратор сети' },
  role_branch_manager: { uz: 'Filial menejeri', en: 'Branch manager', ru: 'Менеджер филиала' },
  role_seller: { uz: 'Sotuvchi', en: 'Seller', ru: 'Продавец' },
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

/** Non-hook translation, for use outside React components (e.g. api/client.ts). */
export function translate(language: Language, key: StringKey, vars?: Vars): string {
  return interpolate(STRINGS[key][language], vars)
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
