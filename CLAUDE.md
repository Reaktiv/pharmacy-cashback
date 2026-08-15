# Pharmacy Cashback — Dizayn tizimi

## Nega hozirgi dizayn ishlamaydi
Hozirgi ekranlar (screenshotlardan ko'rinib turibdi) ikkita bir-biriga mos kelmaydigan uslubdan iborat: login sahifasi — umumiy binafsha gradient SaaS shabloni, admin panellar — umumiy qora sidebar'li "generic B2B dashboard" shabloni. Ikkalasi ham "istalgan SaaS" ko'rinishida — farmatsevtika, ishonch, va O'zbekiston kontekstiga bog'liq hech narsa yo'q.

## Konsepsiya
**Signatura element: "Blister lenta" (pill-strip perforatsiya).** Dorixona blister-upakovkasidagi teshikchalar — bo'limlar orasidagi ajratgich, progress-barlar (masalan 50% keshbek chegarasi) va tugma shakllarida qo'llaniladi. Bu farmatsevtika mavzusini so'zsiz, ammo aniq ifodalaydi — logotip sifatida tibbiy xoch yoki tabletka ishlatishdan ko'ra nozikroq yechim.

Ikki rejim bor, chunki ikkita foydalanuvchi butunlay boshqa narsaga muhtoj:
- **Kassa (POS) rejimi** — och fon, ulkan input, bitta tugma. Hech qanday navigatsiya yo'q. Maqsad: 5 soniya.
- **Admin rejimi** — chuqur yashil sidebar + oq kontent, ma'lumot zich, jadvallar mono shriftda.

## Ranglar
| Token | Hex | Vazifa |
|---|---|---|
| `--bg` | `#F6F8F5` | Sahifa foni (yashil tusli oq qog'oz) |
| `--surface` | `#FFFFFF` | Kartalar |
| `--surface-2` | `#EEF3EE` | Ikkinchi darajali fon, inputlar |
| `--ink` | `#14231C` | Asosiy matn (yashil tusli qora) |
| `--ink-muted` | `#5B6B62` | Ikkinchi darajali matn |
| `--primary` | `#0F3D2E` | Chuqur farmatsevtika yashili — sidebar, sarlavhalar, asosiy tugmalar |
| `--primary-2` | `#1B5E44` | Hover holati |
| `--accent` | `#2FBF8F` | Mint-yashil — muvaffaqiyat, faol holat, keshbek |
| `--accent-warm` | `#E3A73B` | Kahrabo — pul/ball raqamlari, ogohlantirish emas urg'u |
| `--danger` | `#C24A3D` | Terrakota-qizil — storno, firibgarlik ogohlantirishi (neon qizil emas) |
| `--line` | `#DDE5DE` | Nozik chiziqlar, perforatsiya rangi |

Binafsha/indigo gradientlar butunlay olib tashlanadi — bu O'zbekistondagi o'nlab boshqa SaaS ilovalar bilan bir xil ko'rinadi.

## Tipografika
- **Display — Fraunces** (variable serif, "opsz" katta o'lchamda): faqat brend nomi, sahifa sarlavhalari va Kassa ekranidagi katta summa ko'rsatkichi uchun. Kam ishlatiladi, lekin ishonch va "qog'ozdagi retsept" hissini beradi.
- **UI/matn — Public Sans**: barcha interfeys matni, tugmalar, formalar.
- **Raqamlar/ma'lumot — IBM Plex Mono**: summalar, telefon raqamlari, OTP kodlari, tranzaksiya ID'lari, jadval raqamlari. Tabular-nums — ustunlar tekis turadi, firibgarlikni tekshirishda raqamlarni solishtirish osonlashadi.

Shrift o'lchamlari: 12 / 14 / 16 / 20 / 28 / 40 / 56px, qadam ~1.25x.

## Shakl va bo'shliq
- Radius: kartalar 20px, kichik elementlar 12px, tugmalar **to'liq kapsula** (999px) — pill-strip metaforasini davom ettiradi.
- Bo'lim ajratgichi: to'g'ri chiziq o'rniga **perforatsiya qatori** — 6px oraliqda kichik doiralar, `--line` rangida.
- Soyalar juda yumshoq: `0 1px 2px rgba(15,61,46,.06), 0 8px 24px rgba(15,61,46,.06)`.
- 8px grid asosida bo'shliqlar.

## Komponentlar
- **Asosiy tugma**: to'liq kapsula, `--primary` fon, oq matn, hover'da `--primary-2`, bosilganda 2px pastga siljish (fizik tugma bosish hissi).
- **50% chegarasi indikatori** (Kassa/Bot): 10 ta segmentli "blister" progress-bar — har bir segment bitta doira, to'lgan qismi `--accent` rangida.
- **Status belgi**: kapsula shaklidagi kichik yorliq — Faol/Onboarding/To'xtatilgan/Storno uchun mos ranglarda, har doim ikonka + matn (faqat rangga tayanmaslik uchun).
- **Jadval raqamlari**: doim IBM Plex Mono, o'ngga tekislangan.

## Uch ekran uchun maxsus qoidalar
1. **Kassa (sotuvchi)** — sidebar yo'q. Markazdagi bitta karta, ulkan summa inputi (Fraunces/mono, 40px+), telefon inputi, bitta katta yashil tugma. Retsept checkbox bosilganda karta kulrang tusga o'tadi va "Keshbek yo'q" yozuvi chiqadi — vizual signal, o'qishga vaqt ketmasin.
2. **Admin panel** — `--primary` fon sidebar, faol bo'lim chap tomonda 3px `--accent` chiziq bilan belgilanadi (to'liq fon emas — kamroq "shovqin"). Kartalar sarlavhasi ostida perforatsiya chizig'i.
3. **Telegram bot** — Telegram'ning o'z UI'siga bo'ysunadi, lekin xabarlarda bir xil ohang: raqamlar mono-uslubda ko'rsatiladi (masalan "Balansingiz: `45 200` ball"), va OTP xabari doim amal qilish muddati bilan birga keladi.

## O'zim-tanqid
Birinchi variantda mint+kahrabo+terrakota birga ishlatilganda "bayramona" bo'lib ketishi mumkin edi — shuning uchun kahrabo va terrakota faqat mono raqamlar va status yorliqlarida, kichik dozada qoldirildi; asosiy sirt 90% holda yashil-oq juftlikda qoladi. Perforatsiya motivi ham haddan tashqari ko'p joyda ishlatilmasin deb faqat bo'lim ajratgichlar va progress-barlarga cheklandi.