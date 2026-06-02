# Online test **v2** (reklama) — Telegram bot integratsiya

> v2 = reklama uchun **kechiktirilgan registratsiya**. Foydalanuvchi `/start`
> bosadi → WebApp ochiladi → **faqat fan tanlaydi va testni boshlaydi**. Test
> tugab, natijani ko'rmoqchi bo'lganda qolgan forma (kanaldan tashqari) WebApp
> ichida so'raladi.

**Bog'liq commit:** `534c1c4` (backend tayyor, remote'da).
**Frontend doc:** [online-test-v2-promo-frontend.md](online-test-v2-promo-frontend.md) — WebApp tomoni.

---

## 1. Mas'uliyat taqsimoti

| Qadam | Kim bajaradi |
|-------|--------------|
| `/start` → userni saqlash (tracking) | **Bot** → `POST /auth/register/start` |
| v2 WebApp tugmasini yuborish | **Bot** → `WebAppInfo(url=...)` |
| Fan tanlash | **WebApp** |
| `POST /dtm/online/v2/start` (user + daftar yaratish, JWT) | **WebApp** |
| Test (`/test`, `/answer`, `/submit`) | **WebApp** |
| Qolgan forma + `POST /dtm/online/v2/complete` | **WebApp** |
| Natija + PDF ko'rsatish | **WebApp** (`/status`) |
| GraphBot chat_id import (reklamadan oldin) | **Adminka** → `POST /admin/import-bot-start-users` |

> **Bot yupqa:** asosiy ish WebApp'da. Bot faqat `/start` saqlaydi va WebApp'ni
> ochadi. Fan tanlash, forma, ball — hammasi WebApp ichida.

---

## 2. Bot nima qiladi

### 2.1 — `/start` bosilganda userni saqlash

Foydalanuvchi botga `/start` bosishi bilan, formani to'ldirmasa ham, uni bazaga
yozib qo'yamiz. Keyin qaytib kelib davom etsa — yo'qolmaydi.

```
POST /api/v1/auth/register/start
Content-Type: application/json
{ "bot_id": "6796103305", "username": "ali_valiyev" }
```
- `bot_id` = Telegram `chat_id` (string).
- `username` = Telegram `@username` (`@` siz; yo'q bo'lsa yuborma).
- **Idempotent** — qayta `/start` bosilsa xato yo'q, mavjud yozuv qaytadi.
  Bo'sh `username` eski saqlanganini o'chirmaydi.

**Response 200:** `{ bot_id, username, created_at, converted }`

> `X-Api-Key` shart emas — bu ochiq endpoint (faqat stub saqlaydi).

### 2.2 — v2 WebApp tugmasini ochish

`/start` (yoki reklama tugmasi) → v2 WebApp'ni Mini App sifatida ochadi. WebApp
ichida fan tanlash + test boshlanadi.

**v2 WebApp URL** (frontend bilan kelishilgan, alohida sahifa yoki `?v2=1`):
```
https://dtm.your-domain.uz/online-test/?v2=1
```

---

## 3. Aiogram 3.x — to'liq namuna

```python
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)
import httpx

API_BASE = "https://dtm.your-domain.uz"
V2_WEBAPP_URL = f"{API_BASE}/online-test/?v2=1"   # frontend bilan kelishilgan

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def _track_start(tg_user) -> None:
    """/start bosgan userni bazaga yozish (idempotent, best-effort)."""
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            await cli.post(
                f"{API_BASE}/api/v1/auth/register/start",
                json={
                    "bot_id": str(tg_user.id),
                    "username": tg_user.username or None,
                },
            )
    except Exception:
        pass  # tracking test oqimini bloklamasin


@dp.message(CommandStart())
async def on_start(message: Message):
    # 1) start bosgan userni saqlaymiz (forma to'lmasa ham)
    await _track_start(message.from_user)

    # 2) v2 WebApp tugmasini ochamiz — fan tanlash + test WebApp ichida
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="📝 Testni boshlash",
            web_app=WebAppInfo(url=V2_WEBAPP_URL),
        )
    ]])
    await message.answer(
        "Bepul DTM sinov testi!\n\n"
        "Fan tanlab, 90 savollik testni topshiring. "
        "Natijangizni testdan keyin ko'rasiz.\n\n"
        "Boshlash uchun tugmani bosing:",
        reply_markup=kb,
    )
```

### pyTelegramBotAPI (telebot)

```python
import telebot, requests
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

API_BASE = "https://dtm.your-domain.uz"
V2_WEBAPP_URL = f"{API_BASE}/online-test/?v2=1"
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=["start"])
def on_start(msg):
    # tracking (best-effort)
    try:
        requests.post(
            f"{API_BASE}/api/v1/auth/register/start",
            json={"bot_id": str(msg.chat.id),
                  "username": msg.from_user.username or None},
            timeout=10,
        )
    except Exception:
        pass

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(
        "📝 Testni boshlash",
        web_app=WebAppInfo(url=V2_WEBAPP_URL),
    ))
    bot.send_message(msg.chat.id, "Bepul DTM sinov testi! Boshlash:", reply_markup=kb)
```

---

## 4. WebApp v2 oqimi (bot fonida nima bo'ladi)

Bot WebApp'ni ochgach, ichida (frontend bajaradi):

```
WebApp ochiladi (?v2=1)
   ↓
fan tanlash ekrani
   ↓
POST /dtm/online/v2/start { bot_id, first_subject_id, second_subject_id, username }
   → JWT + user + 90-savol daftari yaratiladi
   ↓
GET /dtm/online/test → test
   ↓
POST /dtm/online/submit → { registration_required: true, total_ball: 0 }   ⚠️ ball yashirin
   ↓
qolgan forma (F.I.Sh, telefon, maktab, ... — KANAL YO'Q)
   ↓
POST /dtm/online/v2/complete → ball ochiladi + PDF render
   ↓
GET /dtm/online/status → PDF
```

WebApp `bot_id`'ni Telegram `initData`'dan (yoki `?chat_id=`) oladi — bot
qo'shimcha uzatish shart emas. Batafsil: frontend doc.

---

## 5. PDF'ni Telegram chatga yuborish (ixtiyoriy)

`v2/complete`'dan keyin PDF render bo'ladi va `user.file_url` ga yoziladi. WebApp
uni `/status` orqali ko'rsatadi. Agar PDF'ni **bot chatiga ham** yubormoqchi
bo'lsangiz — mavjud online flow'dagi worker mexanizmi ishlatiladi (alohida
sozlash kerak bo'lsa, frontend/backend bilan kelishing). v2 uchun majburiy emas.

---

## 6. Adminka — reklamadan oldin chat_id import

GraphBot listni (start bosgan, hali ro'yxatdan o'tmagan userlar) bazaga yuklash.
Bu **bot emas, adminka** ishi:

```
POST /api/v1/admin/import-bot-start-users
X-Api-Key: <SECRET_KEY>
Content-Type: multipart/form-data
file: <.json | .csv | .txt>
```
Javob: `{ received, inserted, skipped_registered, skipped_existing }`. Batafsil:
frontend doc, 5-bo'lim.

---

## 7. Test holatlari (manual smoke test)

| # | Holat | Kutilgan |
|---|-------|----------|
| 1 | `/start` bosildi | `register/start` 200, user `bot_start_users`'da |
| 2 | `/start` qayta bosildi | Xato yo'q (idempotent), eski username saqlanadi |
| 3 | WebApp ochilib fan tanlandi | `v2/start` 200, JWT, test yuklanadi |
| 4 | Qayta `/start` → WebApp | `v2/start` `resumed: true` — o'sha test davom etadi |
| 5 | Test submit | `registration_required: true`, ball ko'rsatilmaydi |
| 6 | Forma to'ldirildi | `v2/complete` 200, ball ochiladi, PDF render |
| 7 | Forma'dan oldin submit yo'q (faqat forma) | `v2/complete` `submitted: false`, ball 0 |

---

## 8. Tez-tez uchraydigan xatolar

**`v2/start` 400 — `Unknown subject_id`**
- Sabab: noto'g'ri fan `mt_id`.
- Yechim: WebApp mavjud register'dagi fan `mt_id` qiymatlarini ishlatsin.

**Submit'dan keyin ball 0 ko'rinyapti**
- Bu **xato emas** — `registration_required: true`. Ball ataylab yashirilgan.
  WebApp formaga o'tkazishi, ballni ko'rsatmasligi kerak.

**`v2/complete` 404 — `v2 test user not found`**
- Sabab: bu `bot_id` uchun v2 test boshlanmagan (`v2/start` chaqirilmagan).
- Yechim: avval WebApp `v2/start` chaqirsin.

**`v2/complete` 400 — `School not found`**
- Sabab: `school_code` bazada yo'q.
- Yechim: to'g'ri maktab kodini yuboring.

**`/start` tracking ishlamayapti**
- `register/start` `X-Api-Key` talab qilmaydi — header yubormang. `bot_id`
  string bo'lsin.

---

## 9. Eski (v1) online flow

v1 online test (to'liq registratsiya → quick-login → WebApp) **o'zgarmagan** —
[online-test-bot-setup.md](online-test-bot-setup.md), 9-bo'lim. v2 butunlay
alohida (`test_type="online_v2"`), v1 cap'ga ta'sir qilmaydi. Bir user ham v1
real testni, ham v2 reklama testini topshira oladi.

---

## 10. Xulosa — bot dasturchisi checklist

- [ ] `/start` handler → `POST /auth/register/start` (bot_id + username)
- [ ] `/start` → v2 WebApp tugmasi (`WebAppInfo(url=V2_WEBAPP_URL)`)
- [ ] v2 WebApp URL frontend bilan kelishilgan (`?v2=1` yoki alohida sahifa)
- [ ] (ixtiyoriy) PDF'ni chatga yuborish kerakmi — backend bilan kelishing
- [ ] Reklamadan oldin adminka GraphBot listni import qildi
- [ ] Smoke test (7-bo'lim) bajarildi

Bot tomoni shu — qolgan hammasi WebApp + backend (tayyor, remote'da).
