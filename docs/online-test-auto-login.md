# Online test — chat_id avtomatik login (bot + frontend)

> WebApp endi har qanday holatda **chat_id'ni avtomatik** oladi:
> - Telegram WebApp ichida → `tg.initData`'dan
> - Brauzerda → URL'dagi `?chat_id=...` parametridan
>
> Foydalanuvchi hech qachon Telegram ID'sini qo'lda kiritmaydi (manual input — faqat fallback).

**Bog'liq commit**: `<ushbu commit>` — frontend o'zgartirishi.

---

## Hozirgi flow

```
Foydalanuvchi havolani ochadi
        ↓
WebApp boot()
        ↓
   ┌────────────────────────┐
   │ Telegram WebApp'mi?    │
   │ tg.initData mavjudmi?  │
   └────────────┬───────────┘
                │
        ┌───────┴───────┐
       YES             NO
        │               │
        │               ↓
        │     ┌──────────────────────────┐
        │     │ JWT localStorage'da bor? │
        │     └──────────┬───────────────┘
        │                │
        │       ┌────────┴────────┐
        │      YES               NO
        │       │                 │
        │       │                 ↓
        │       │       ┌─────────────────────┐
        │       │       │ URL'da ?chat_id=    │
        │       │       │ yoki ?bot_id= bor?  │
        │       │       └────────┬────────────┘
        │       │                │
        │       │       ┌────────┴──────────┐
        │       │      HA                  YO'Q
        │       │       │                   │
        │       │       │                   ↓
        │       │       │        Manual login form
        │       │       │        ko'rsatiladi
        │       │       │
        │       │       ↓
        │       │     /quick-login (avtomatik)
        │       │       ↓
        │       │     OK → JWT saqlash
        ↓       ↓       ↓
    ──────────────────────────
        loadAndShowTest()
```

---

## Bot tomon (alohida repo)

Botingiz user'ga test linkini yuborayotganda **chat_id'ni URL'ga qo'shish kerak**.

### Aiogram misol

```python
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

WEBAPP_URL = "https://your-domain.com/online-test/index.html"

# Variant A: WebApp button (Telegram'da WebApp sifatida ochiladi — initData
#            avtomatik yuboriladi, URL param shart EMAS)
@router.message(Command("test"))
async def cmd_test(message: Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(
                text="📝 Online test",
                web_app=WebAppInfo(url=WEBAPP_URL),
            )
        ]],
        resize_keyboard=True,
    )
    await message.answer("Testni boshlash uchun pastdagi tugmani bosing", reply_markup=kb)


# Variant B: oddiy URL button (brauzerda ochiladi — URL'ga chat_id qo'shing!)
@router.message(Command("test_browser"))
async def cmd_test_browser(message: Message):
    user_id = message.from_user.id
    # ⚠️ ?chat_id=... — frontend shu orqali avtomatik login qiladi
    url_with_chat = f"{WEBAPP_URL}?chat_id={user_id}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📝 Online test (brauzerda)", url=url_with_chat),
    ]])
    await message.answer("Brauzerda ochish uchun:", reply_markup=kb)
```

### Eslatma

- **WebApp button** (`web_app=WebAppInfo(...)`) — Telegram ichida ochiladi, `initData` avtomatik kelganligi uchun URL'ga chat_id qo'shish **shart emas**. Lekin qo'shsangiz ham xato emas (frontend initData'ga ustunlik beradi).
- **URL button** (`url=...`) — brauzerda ochiladi, **bu yerda chat_id majburiy**.
- Agar bot ikki variantni ham yuboradigan bo'lsa, hamma joyga `?chat_id=<user.id>` qo'shish — eng xavfsiz default.

### Aiogram boshqa kontekstlar

```python
# /start orqali deeplink
@router.message(CommandStart(deep_link=True))
async def deep_start(message: Message, command: CommandStart):
    if command.args == "test":
        url = f"{WEBAPP_URL}?chat_id={message.from_user.id}"
        await message.answer(f"Testni ochish: {url}")

# Inline mode result
@router.inline_query()
async def inline(query: InlineQuery):
    user_id = query.from_user.id
    url = f"{WEBAPP_URL}?chat_id={user_id}"
    # ...
```

---

## Frontend — qanday ishlaydi

WebApp `boot()` funksiyasi:

1. **Telegram WebApp** ekanligini tekshiradi → `tg.initData` orqali avtomatik login (avvalgidek)
2. **JWT** `localStorage`'da bormi (oldingi sessiya) → ishlatadi
3. **URL'da `?chat_id=...` yoki `?bot_id=...`** bormi → avtomatik `/quick-login` chaqiradi
4. Hech qaysi yo'q → manual fallback (`<details>` ichida yashirin form)

URL parametri ikki nom qabul qiladi:
- `?chat_id=...` — yangi (tavsiya)
- `?bot_id=...` — bir xil semantika (botingiz boshqa nom ishlatsa)

### Auth oqibati

Backend `/dtm/online/quick-login` `bot_id` param qabul qiladi:
- User mavjud (status=True, bot_id=`<chat_id>`) → JWT qaytadi → frontend saqlaydi → test ochiladi
- User topilmaydi → 404 → frontend "Avval botda ro'yxatdan o'ting" deydi
- `test_type='offline'` user → 403 (online test'ga kira olmaydi)

---

## Xavfsizlik haqida eslatma

URL'da `?chat_id=...` — **manual input bilan bir xil xavfsizlik darajasi**. Har kim URL'ga istalgan chat_id qo'yib login qila oladi (agar shu chat_id bilan registered user mavjud bo'lsa).

Bu **tegirmonchi** xavfsizlik — `/quick-login` allaqachon shu xulqda. Yangi yo'l xuddi shu xavfsizlik darajasida.

**Production-grade auth**:
- Telegram WebApp ichida — `tg.initData` (Telegram tomonidan signed) ✓ proper auth
- Brauzerda — short-lived signed token (server tomonidan generate qilingan) yoki Telegram OAuth widget

V1 da bu yetarli — bot link'dan kelgan har kim shu user'ning testini topshira olmaydi (registratsiya talabi bor). Spam-resistance kerak bo'lsa keyin signed token'ga o'tamiz.

---

## Test scenariy

### Mahalliy

1. WebApp serverini ishga tushiring (`python3 -m http.server` `report_front/` ichida)
2. Brauzerda oching:
   ```
   http://localhost:8765/online-test/?chat_id=<biror real bot_id>
   ```
3. Avtomatik login bo'lishi kerak (DevTools Network tab'da `/quick-login` chaqirig'i ko'rinadi)
4. URL'siz oching:
   ```
   http://localhost:8765/online-test/
   ```
5. Login screen chiqishi kerak. "Telegram ID'ni qo'lda kiritish" bo'limini ochib, Telegram ID kiritsangiz ham ishlay olishi kerak (fallback).

### Production (real bot bilan)

1. Botda `/test` chaqiring → URL button bilan link kelishi kerak (URL'da `?chat_id=` bor)
2. Linkni desktop brauzerda oching → avtomatik kirish
3. Telegram'da link bossangiz — Telegram in-app brauzerda ochiladi (URL'da chat_id bor) → avtomatik kirish
4. Manual ID input — yashirin (`<details>`), kerak bo'lsa ochsa bo'ladi (testlash/admin uchun)

---

## Frontend o'zgargan fayllar

| Fayl | O'zgarish |
|---|---|
| `report_front/online-test/app.js` | `tryAutoLoginFromUrl()` qo'shildi, `boot()` URL param'ni tekshiradi |
| `report_front/online-test/index.html` | Login screen matn qayta ishlandi, manual input `<details>` ichiga yashirildi |
| `report_front/online-test/styles.css` | `.login-manual` (collapse/expand) style'lari qo'shildi |

Backend o'zgarmadi — `/dtm/online/quick-login` endpoint avvalgidek ishlaydi.

---

## Bot dasturchi uchun checklist

- [ ] WebApp button (`web_app=WebAppInfo(...)`) ishlatiladi → URL'da chat_id shart emas (lekin qo'shish ham xato emas)
- [ ] URL button (`url=...`) ishlatiladi → URL'ga `?chat_id={user.id}` **majburiy**
- [ ] Deeplink (`/start <token>`) → bot user_id ni biladi, URL'ga qo'shing
- [ ] Inline mode result → URL'ga `?chat_id={query.from_user.id}` qo'shing
- [ ] Boshqa variantlar (`InlineQueryResultArticle`, `link_preview` matnida URL) → har qachon URL'ni dynamic format'da yarating

Misol prefix funksiyasi:

```python
def online_test_url(user_id: int) -> str:
    return f"https://your-domain.com/online-test/?chat_id={user_id}"
```

Botning hamma joyida shu funksiya'ni chaqiring — keyinroq URL formatini o'zgartirish bitta joyda bo'ladi.

---

## Frontend dasturchi uchun checklist

- [x] `boot()` URL param'ni tekshiradi
- [x] Manual input `<details>` ichida (default yopiq)
- [x] Login screen matni "Bot orqali keling" deydi
- [x] e2e test (URL param → quick-login chaqirig'i, fallback'da manual form)

---

## Xulosa

| Komponent | Holat |
|---|---|
| Frontend `boot()` URL param ni o'qib avtomatik login | ✅ tayyor |
| Manual input form fallback'ga ko'chirildi | ✅ tayyor |
| Bot'da URL'ga `?chat_id={user.id}` qo'shish | ⏳ bot dasturchi (alohida repo) |
| Server deploy + restart | DevOps |

Bot dasturchi shu doc bo'yicha bot kodida URL formatini yangilasa — foydalanuvchi hech qachon Telegram ID'sini qo'lda kiritmaydi.
