# Online test **v2** (reklama) — Telegram bot integratsiya

> v2 = reklama uchun **kechiktirilgan registratsiya**. **Bot** fanlarni so'raydi
> va backendga yuboradi → test **WebApp**'da ishlanadi → test tugagach **bot**
> qolgan formani so'raydi (kanaldan tashqari) → natija + PDF chatga keladi.

**Bog'liq commit:** `<shu commit>`. Endpointlar `/api/v1` prefiksli.
**Frontend (WebApp) doc:** [online-test-v2-promo-frontend.md](online-test-v2-promo-frontend.md).

---

## 1. Mas'uliyat taqsimoti

| Qadam | Kim | Endpoint |
|-------|-----|----------|
| `/start` → userni saqlash (tracking) | **Bot** | `POST /auth/register/start` |
| Fan ro'yxatini olish (tugmalar uchun) | **Bot** | `GET /dtm/online/subjects` |
| Fan tanlash (inline tugmalar) | **Bot** | — |
| Tanlangan fanlarni yuborish → user + daftar yaratish | **Bot** | `POST /dtm/online/v2/start` |
| Test WebApp tugmasini ochish | **Bot** | — |
| WebApp'ga kirish (chat_id) | **WebApp** | `POST /dtm/online/quick-login` |
| Test (savollar, javob, topshirish) | **WebApp** | `/test`, `/answer`, `/submit` |
| Test tugadi → botga signal | **WebApp** | `tg.sendData(...)` |
| Qolgan forma (F.I.Sh, tel, maktab, …) | **Bot** | — |
| Formani yuborish → natija ochiladi | **Bot** | `POST /dtm/online/v2/complete` |
| Natija balli | **Bot** | (v2/complete javobida) |
| PDF chatga yuborish | **avtomatik** | backend worker (bot hech narsa qilmaydi) |

---

## 2. To'liq oqim

```
/start
  ├─ POST /auth/register/start            (tracking, idempotent)
  └─ "Fanlaringizni tanlang"  ← GET /dtm/online/subjects dan inline tugmalar
        ↓ (1-fan tanlandi)
     "Ikkinchi fan"
        ↓ (2-fan tanlandi)
     POST /dtm/online/v2/start {bot_id, first_subject_id, second_subject_id, username}
        → user(test_type=online_v2) + 90-savol daftari yaratiladi
        ↓
     [📝 Testni boshlash]  WebApp tugmasi
─────────────────────────────────────────────  WebApp (test UI)
     quick-login(chat_id) → GET /test → /answer → /submit
        → { registration_required: true, total_ball: 0 }   ⚠️ ball yashirin
     tg.sendData('{"done":true}')   → botga qaytaradi
─────────────────────────────────────────────  Bot (forma)
  web_app_data keldi
     → "Natijangizni ko'rish uchun ma'lumot to'ldiring"
     → F.I.Sh → telefon → maktab kodi → (region, district, …)   [KANAL YO'Q]
     → POST /dtm/online/v2/complete {bot_id, full_name, phone, school_code, ...}
        → { total_ball, mandatory_ball, ... }  → botda ko'rsatiladi
        → PDF render + avtomatik chatga yuboriladi (worker)
```

---

## 3. Endpointlar (bot chaqiradigan)

### 3.1 `/start` tracking
```
POST /api/v1/auth/register/start
{ "bot_id": "6796103305", "username": "ali_valiyev" }
```
Idempotent, `X-Api-Key` shart emas. `username` yo'q bo'lsa yubormang.

### 3.2 Fan ro'yxati (tugmalar uchun)
```
GET /api/v1/dtm/online/subjects
→ [ { "mt_id": 35, "name_uz": "Matematika", "name_ru": "..." },
    { "mt_id": 23, "name_uz": "Ingliz tili", ... }, ... ]
```
`mt_id` — `v2/start`ga yuboriladigan qiymat.

### 3.3 Fanlarni yuborish → test tayyorlash
```
POST /api/v1/dtm/online/v2/start
{ "bot_id": "6796103305", "first_subject_id": 35,
  "second_subject_id": 23, "username": "ali_valiyev" }
→ { access_token, user_id, user_test_id, resumed }
```
- Idempotent: qayta yuborilsa `resumed: true` (o'sha test).
- `access_token`'ni e'tiborsiz qoldirsa bo'ladi — WebApp o'zi quick-login qiladi.
- 400 `Unknown subject_id` → noto'g'ri `mt_id`.

### 3.4 Forma → natijani ochish
```
POST /api/v1/dtm/online/v2/complete
{ "bot_id": "6796103305", "full_name": "Valiyev Ali",
  "phone": "+998901234567", "school_code": "SHAY186",
  "region": "...", "district": "...", "gender": "male",
  "group_name": "B", "language": "uz" }
→ { user_id, document_code, submitted, pdf_pending,
    total_ball, mandatory_ball, primary_ball, secondary_ball }
```
- Majburiy: `bot_id`, `full_name`, `phone`, `school_code`. **Kanal YO'Q.**
- `submitted: true` → ball ochildi (ko'rsating), PDF render boshlandi → chatga
  avtomatik keladi.
- 404 `v2 test user not found` → `v2/start` chaqirilmagan.
- 400 `School not found` → `school_code` noto'g'ri.

---

## 4. Aiogram 3.x — to'liq namuna

```python
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, WebAppInfo,
)
import httpx, json

API = "https://dtm.your-domain.uz/api/v1"
WEBAPP_URL = "https://dtm.your-domain.uz/online-test/"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


class V2(StatesGroup):
    first_subject = State()
    second_subject = State()
    full_name = State()
    phone = State()
    school_code = State()


async def _api_post(path, payload):
    async with httpx.AsyncClient(timeout=30) as c:
        return await c.post(f"{API}{path}", json=payload)

async def _api_get(path):
    async with httpx.AsyncClient(timeout=15) as c:
        return await c.get(f"{API}{path}")


# --- /start: tracking + fan tanlash ---
@dp.message(CommandStart())
async def on_start(message: Message, state: FSMContext):
    # tracking (best-effort)
    try:
        await _api_post("/auth/register/start", {
            "bot_id": str(message.from_user.id),
            "username": message.from_user.username or None,
        })
    except Exception:
        pass

    subs = (await _api_get("/dtm/online/subjects")).json()
    rows = [[InlineKeyboardButton(text=s["name_uz"], callback_data=f"s1:{s['mt_id']}")]
            for s in subs]
    await state.set_state(V2.first_subject)
    await message.answer(
        "Bepul DTM sinov testi!\n\nBirinchi (majburiy) faningizni tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@dp.callback_query(V2.first_subject, F.data.startswith("s1:"))
async def pick_first(cb: CallbackQuery, state: FSMContext):
    await state.update_data(first_subject_id=int(cb.data.split(":")[1]))
    subs = (await _api_get("/dtm/online/subjects")).json()
    rows = [[InlineKeyboardButton(text=s["name_uz"], callback_data=f"s2:{s['mt_id']}")]
            for s in subs]
    await state.set_state(V2.second_subject)
    await cb.message.edit_text("Ikkinchi (tanlov) faningizni tanlang:",
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()


@dp.callback_query(V2.second_subject, F.data.startswith("s2:"))
async def pick_second(cb: CallbackQuery, state: FSMContext):
    data = await state.update_data(second_subject_id=int(cb.data.split(":")[1]))
    # test + daftar yaratish
    r = await _api_post("/dtm/online/v2/start", {
        "bot_id": str(cb.from_user.id),
        "first_subject_id": data["first_subject_id"],
        "second_subject_id": data["second_subject_id"],
        "username": cb.from_user.username or None,
    })
    if r.status_code != 200:
        await cb.message.answer(f"Xatolik: {r.status_code}\n{r.text[:200]}")
        await cb.answer(); return

    # WebApp tugmasi — sendData ishlashi uchun REPLY keyboard (inline emas)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📝 Testni boshlash",
                                  web_app=WebAppInfo(url=WEBAPP_URL))]],
        resize_keyboard=True,
    )
    await state.set_state(None)  # test davomida FSM bo'sh
    await cb.message.answer("Tayyor! Pastdagi tugma orqali testni boshlang:",
                            reply_markup=kb)
    await cb.answer()


# --- WebApp test tugagach botga sendData orqali qaytaradi ---
@dp.message(F.web_app_data)
async def on_test_done(message: Message, state: FSMContext):
    # WebApp tg.sendData('{"done":true}') yuboradi
    await state.set_state(V2.full_name)
    await message.answer("✅ Test topshirildi!\n\n"
                         "Natijangizni ko'rish uchun: F.I.Sh kiriting:")


@dp.message(V2.full_name)
async def get_name(message: Message, state: FSMContext):
    await state.update_data(full_name=message.text.strip())
    await state.set_state(V2.phone)
    await message.answer("Telefon raqamingiz:")


@dp.message(V2.phone)
async def get_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())
    await state.set_state(V2.school_code)
    await message.answer("Maktab kodingiz:")


@dp.message(V2.school_code)
async def get_school_and_finish(message: Message, state: FSMContext):
    data = await state.update_data(school_code=message.text.strip())
    r = await _api_post("/dtm/online/v2/complete", {
        "bot_id": str(message.from_user.id),
        "full_name": data["full_name"],
        "phone": data["phone"],
        "school_code": data["school_code"],
        # ixtiyoriy: region, district, gender, group_name, language
    })
    await state.clear()
    if r.status_code != 200:
        await message.answer(f"Xatolik: {r.status_code}\n{r.text[:200]}")
        return
    res = r.json()
    await message.answer(
        f"🎉 Natijangiz:\n\n"
        f"Umumiy ball: <b>{res['total_ball']}</b>\n"
        f"Majburiy: {res['mandatory_ball']}\n"
        f"1-fan: {res['primary_ball']}\n"
        f"2-fan: {res['secondary_ball']}\n\n"
        f"To'liq natija (PDF) bir zumda yuboriladi…",
        parse_mode="HTML",
    )
    # PDF backend worker tomonidan avtomatik chatga keladi — qo'shimcha kod kerakmas
```

> **WebApp tomon (frontend):** test `/submit`'dan keyin `registration_required: true`
> bo'lsa, ballni KO'RSATMASIN va `tg.sendData(JSON.stringify({done:true}))`
> chaqirib WebApp'ni yopsin. Shunda bot formani boshlaydi. Batafsil: frontend doc.

---

## 5. PDF yetkazish — avtomatik

`v2/complete`'dan keyin backend natija PDF'ini render qiladi va **telegram queue
worker** orqali user chatiga avtomatik yuboradi (mavjud online flow mexanizmi).
Bot tomonida qo'shimcha kod **kerak emas**. Worker ishlashi uchun Redis +
queue worker startup'da ulangan bo'lishi shart (mavjud setup).

---

## 6. WebApp → bot signali (sendData)

`tg.sendData()` faqat **reply-keyboard** WebApp tugmasida ishlaydi (inline
WebApp tugmasida emas) — shu sabab namunada `ReplyKeyboardMarkup`. WebApp test
tugagach `Telegram.WebApp.sendData('{"done":true}')` chaqiradi → bot
`F.web_app_data` handler'ida qabul qiladi.

**Muqobil** (sendData ishlatmasangiz): WebApp yopilgach botga "✅ Natijani olish"
inline tugmasini yuboring, bosilganda forma FSM'ini boshlang.

---

## 7. Smoke test

| # | Holat | Kutilgan |
|---|-------|----------|
| 1 | `/start` | tracking 200, fan tugmalari chiqadi |
| 2 | 2 fan tanlandi | `v2/start` 200, WebApp tugmasi |
| 3 | Qayta `/start` → 2 fan | `v2/start` `resumed: true` |
| 4 | WebApp test → submit | `registration_required: true`, ball ko'rinmaydi |
| 5 | sendData → forma to'ldirildi | `v2/complete` 200, ball xabarda |
| 6 | — | PDF chatga avtomatik keladi |

---

## 8. Tez-tez xatolar

- **`v2/complete` 404** — `v2/start` chaqirilmagan (fan tanlanmagan). Forma'dan
  oldin `v2/start` bo'lishi shart.
- **`v2/start` 400 `Unknown subject_id`** — `GET /subjects` dagi `mt_id`'larni
  ishlating.
- **Submit'da ball 0** — xato emas, `registration_required: true`. Forma'dan
  keyin ochiladi.
- **PDF kelmadi** — Redis/queue worker ishlamayapti (`pm2 logs`'da
  `[online-bg] enqueued telegram send` bormi tekshiring).
- **sendData kelmadi** — WebApp **inline** tugmada ochilgan; reply-keyboard
  tugmasiga o'tkazing yoki muqobil tugma usulini ishlating.

---

## 9. Eski (v1) online flow

v1 (to'liq registratsiya → quick-login → WebApp) **o'zgarmagan**
([online-test-bot-setup.md](online-test-bot-setup.md) §9). v2 alohida
(`test_type="online_v2"`), v1 cap'ga ta'sir qilmaydi. Bir user ham v1, ham v2
testni topshira oladi.

---

## 10. Checklist

- [ ] `/start` → `POST /auth/register/start`
- [ ] `/start` → `GET /dtm/online/subjects` → fan inline tugmalari (2 bosqich)
- [ ] 2 fan → `POST /dtm/online/v2/start`
- [ ] Reply-keyboard WebApp tugmasi (sendData uchun)
- [ ] `F.web_app_data` handler → forma FSM
- [ ] Forma → `POST /dtm/online/v2/complete` → ballni ko'rsatish
- [ ] (frontend) WebApp `tg.sendData('{"done":true}')` qo'shilgan
- [ ] Redis + queue worker ishlaydi (PDF avtomatik yetkazish)
