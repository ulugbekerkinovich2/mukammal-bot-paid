# Bot — Majburiy Kanal Obunasi

Admin paneldan qaysi kanallar majburiy ekanligi boshqariladi.  
Bot har xabarda shu kanallarni tekshiradi, a'zo bo'lmasa bloklaydi.

---

## 1. Faol kanallarni olish

```
GET https://dtmpaperreaderapi.mentalaba.uz/api/v1/admin/bots/{bot_id}/subscriptions/active
Header: X-Admin-Token: <ADMIN_SECRET_TOKEN>

Response:
[
  { "channel_id": "@mentalaba", "title": "Mentalaba rasmiy" },
  { "channel_id": "-1001234567890", "title": "Ikkinchi kanal" }
]

Bo'sh array [] → hech qanday majburiy kanal yo'q, foydalanishga ruxsat
```

`bot_id` — bu loyihaning DB dagi bot id si (integer), Telegram bot id emas.

---

## 2. Obunani tekshirish (getChatMember)

Har bir faol kanal uchun:

```
GET https://api.telegram.org/bot<BOT_TOKEN>/getChatMember
  ?chat_id=@mentalaba
  &user_id=<user_telegram_id>

Response:
{
  "ok": true,
  "result": {
    "status": "member"   ← bu field tekshiriladi
  }
}
```

**Ruxsat berilgan statuslar:** `member`, `administrator`, `creator`  
**Bloklash:** `left`, `kicked`, `restricted`

---

## 3. Logika

```python
async def check_subscriptions(bot_token, admin_token, bot_id, user_tg_id):
    # 1. Faol kanallarni ol
    resp = await http.get(
        f"https://dtmpaperreaderapi.mentalaba.uz/api/v1/admin/bots/{bot_id}/subscriptions/active",
        headers={"X-Admin-Token": admin_token}
    )
    channels = resp.json()  # []

    if not channels:
        return True  # majburiy kanal yo'q

    # 2. Har birini tekshir
    not_joined = []
    for ch in channels:
        r = await http.get(
            f"https://api.telegram.org/bot{bot_token}/getChatMember",
            params={"chat_id": ch["channel_id"], "user_id": user_tg_id}
        )
        data = r.json()
        status = data.get("result", {}).get("status", "left")
        if status not in ("member", "administrator", "creator"):
            not_joined.append(ch)

    return not_joined  # bo'sh [] → o'tdi, aks holda qo'shilmagan kanallar

# Handler da:
not_joined = await check_subscriptions(...)
if not_joined:
    # Xabar + har kanal uchun inline button
    await send_message(user_id, "Botdan foydalanish uchun kanallarga a'zo bo'ling:",
        buttons=[InlineButton(ch["title"], url=f"https://t.me/{ch['channel_id'].lstrip('@')}") for ch in not_joined]
    )
    return
# → davom et
```

---

## 4. Muhim

- Subscriptions listni **cache** qil (30–60 sek) — har xabarda API chaqirma
- Bot kanal admin bo'lishi **shart emas** — faqat `getChatMember` ishlatiladi
- Admin panel orqali kanal `toggle` qilinganda keyingi cache yangilanishda ta'sir qiladi
- `bot_id` ni env da saqlash: `BOT_DB_ID=1`
