# Admin Panel API Docs

**Base URL:** `https://dtmpaperreaderapi.mentalaba.uz`  
**Auth:** barcha so'rovlarda header → `X-Admin-Token: <token>`  
**403** javob → logout qil, tokenni tozala

---

## BOTLAR

```
GET /api/v1/admin/bots
Response: [{id, name, token_preview, channel_count, created_at}]

POST /api/v1/admin/bots
Body: { name: string, token: string }
Response: { id, name, username }
Errors: 409 (token dublikat), 400 (Telegram token noto'g'ri)

DELETE /api/v1/admin/bots/{bot_id}
Response: { ok: true }
Note: kanallar va subscriptionlar ham o'chadi (cascade)
```

---

## KANALLAR (broadcast uchun)

```
GET /api/v1/admin/bots/{bot_id}/channels
Response: [{id, channel_id, title, created_at}]

GET /api/v1/admin/channels
Response: [{id, bot_id, bot_name, channel_id, title, created_at}]

POST /api/v1/admin/bots/{bot_id}/channels
Body: { channel_id: string, title?: string }
Note: @ prefiksi avtomatik qo'shiladi
Response: { id, channel_id, title }
Errors: 409 (dublikat), 404 (bot yo'q)

DELETE /api/v1/admin/channels/{id}
Note: {id} — DB integer id, Telegram @username emas!
Response: { ok: true }
```

---

## SUBSCRIPTION KANALLAR (obuna majburiy)

Har bir bot uchun foydalanuvchi obuna bo'lishi shart kanallar.  
`is_active: false` → vaqtincha o'chirilgan (o'chirilmagan, faqat tekshirilmaydi).

```
GET /api/v1/admin/bots/{bot_id}/subscriptions
Response: [{id, channel_id, title, is_active, created_at}]

GET /api/v1/admin/bots/{bot_id}/subscriptions/active
Response: [{channel_id, title}]
Note: faqat is_active=true lar — bot handler shu endpoint dan oladi

POST /api/v1/admin/bots/{bot_id}/subscriptions
Body: { channel_id: string, title?: string }
Note: @ prefiksi avtomatik qo'shiladi
Response: { id, channel_id, title, is_active }
Errors: 409 (dublikat), 404 (bot yo'q)

PATCH /api/v1/admin/subscriptions/{id}/toggle
Response: { id, channel_id, is_active }
Note: true → false yoki false → true qiladi

DELETE /api/v1/admin/subscriptions/{id}
Response: { ok: true }
```

---

## KANAL BROADCAST (post → kanallarga)

```
POST /api/v1/admin/broadcast/post
Body: {
  post_url: string,        // https://t.me/channelname/123
  channel_ids?: number[]   // yo'q bo'lsa barcha kanallar
}
Response: {
  sent: number,
  total: number,
  results: [{ channel_id, title, ok: bool, error?: string }]
}
Note: copyMessage — "Forwarded from" ko'rinmaydi
```

---

## FOYDALANUVCHI BROADCAST (bot userlariga)

```
GET /api/v1/admin/bot-users/stats
Response: { registered: number, leads: number, total: number }
// registered = ro'yxatdan o'tgan, aktiv, bot bloklagan emas
// leads      = /start bosgan lekin form to'ldirmagan

POST /api/v1/admin/broadcast/users
Body: {
  message?: string,           // matn xabar. placeholder: {full_name} {phone}
  channel_post_url?: string,  // post URL — berilsa message ishlatilmaydi
  target: "all" | "registered" | "bot_start",
  preview?: boolean           // true = yubormasdan cohort hajmini ko'rsat
}

preview=true  → { preview: true, cohort_size, registered, leads, samples: [{bot_id, name}] }
preview=false → { ok: true, enqueued: number }

Note: Redis queue — background da yuboriladi, darhol emas
Note: bot bloklagan userlar avtomatik o'tkazib yuboriladi
```

---

## XATO KODLAR

| Kod | Sabab                       | UI                          |
|-----|-----------------------------|-----------------------------|
| 403 | Token noto'g'ri             | Logout → login sahifasi     |
| 400 | Noto'g'ri ma'lumot          | Form inline xato            |
| 409 | Dublikat (bot/kanal/sub)    | Toast: "allaqachon qo'shilgan" |
| 404 | Topilmadi                   | Toast error                 |
| 422 | Noto'g'ri URL format        | Maydonda inline xato        |
| 500 | Server/Redis xatosi         | Toast: "server xatosi"      |

---

## SAHIFALAR

| Yo'l                              | Vazifa                                     |
|-----------------------------------|--------------------------------------------|
| `/admin/bots`                     | Botlar ro'yxati + qo'shish                 |
| `/admin/bots/:id/channels`        | Bot broadcast kanallari                    |
| `/admin/bots/:id/subscriptions`   | Bot subscription kanallari (toggle bilan)  |
| `/admin/broadcast`                | Kanal broadcast (post URL → kanallar)      |
| `/admin/broadcast/users`          | Foydalanuvchi broadcast                    |
