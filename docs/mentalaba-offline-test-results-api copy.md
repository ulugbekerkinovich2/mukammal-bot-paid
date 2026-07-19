# mentalaba.uz — Offline Test Results API

Base URL: `https://api.mentalaba.uz`

## Auth

Har bir so'rovda header qo'shiladi:

```
x-api-key: e2b0d2eb35708bdbef628174e01af3a02853d4261c036e94
User-Agent: Mozilla/5.0 (compatible; DTM-Bot/1.0)
```

> ⚠️ `User-Agent` bo'lmasa nginx `403 Forbidden` qaytaradi.

---

## 1. Natija yaratish + sertifikat olish

**Endpoint:** `POST /v1/offline-test-results`

### Request

```http
POST https://api.mentalaba.uz/v1/offline-test-results
Content-Type: application/json
x-api-key: e2b0d2eb35708bdbef628174e01af3a02853d4261c036e94
User-Agent: Mozilla/5.0 (compatible; DTM-Bot/1.0)
```

```json
{
  "full_name": "Abdullayev Sardor",
  "phone": "998901234567",
  "school": "1-sonli maktab",
  "primary_subject": "Matematika",
  "secondary_subject": "Fizika",
  "primary_subject_score": 80.0,
  "secondary_subject_score": 70.0,
  "mandatory_subject_score": 60.0,
  "total_score": 210.0,
  "admission_year": "2025"
}
```

| Maydon | Tur | Tavsif |
|--------|-----|--------|
| `full_name` | string | To'liq ism-familiya |
| `phone` | string | Telefon (998XXXXXXXXX) |
| `school` | string | Maktab nomi |
| `primary_subject` | string | Asosiy fan nomi |
| `secondary_subject` | string | Ikkinchi fan nomi |
| `primary_subject_score` | float | Asosiy fan bali (max 93) |
| `secondary_subject_score` | float | Ikkinchi fan bali (max 63) |
| `mandatory_subject_score` | float | Majburiy fanlar bali (max 33) |
| `total_score` | float | Jami ball |
| `admission_year` | string | Qabul yili (masalan `"2025"`) |

### Response

**200 OK** — plain text (JSON emas):

```
offline_test/f580eac9-a779-4dee-8f65-a1d9cadf3aa5.pdf
```

To'liq sertifikat URL:

```
https://api.mentalaba.uz/offline_test/f580eac9-a779-4dee-8f65-a1d9cadf3aa5.pdf
```

### curl misoli

```bash
curl -X POST https://api.mentalaba.uz/v1/offline-test-results \
  -H "Content-Type: application/json" \
  -H "x-api-key: e2b0d2eb35708bdbef628174e01af3a02853d4261c036e94" \
  -H "User-Agent: Mozilla/5.0 (compatible; DTM-Bot/1.0)" \
  -d '{
    "full_name": "Abdullayev Sardor",
    "phone": "998901234567",
    "school": "1-sonli maktab",
    "primary_subject": "Matematika",
    "secondary_subject": "Fizika",
    "primary_subject_score": 80.0,
    "secondary_subject_score": 70.0,
    "mandatory_subject_score": 60.0,
    "total_score": 210.0,
    "admission_year": "2025"
  }'
```

---

## Bot integratsiyasi (hozirgi holat)

Bot offline test tugagach avtomatik:
1. `POST /v1/offline-test-results` ga natija yuboradi
2. Response'dan PDF path oladi
3. Foydalanuvchiga `https://api.mentalaba.uz/{pdf_path}` linkini inline button sifatida yuboradi

Kod: `utils/send_req.py` → `create_offline_test_result()`

---

## Admin panel integratsiyasi uchun

Admin panel ham xuddi shu endpoint'ni ishlatadi:

```javascript
const response = await fetch('https://api.mentalaba.uz/v1/offline-test-results', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'x-api-key': 'e2b0d2eb35708bdbef628174e01af3a02853d4261c036e94',
    'User-Agent': 'Mozilla/5.0 (compatible; AdminPanel/1.0)',
  },
  body: JSON.stringify({
    full_name: '...',
    phone: '998...',
    school: '...',
    primary_subject: '...',
    secondary_subject: '...',
    primary_subject_score: 80,
    secondary_subject_score: 70,
    mandatory_subject_score: 60,
    total_score: 210,
    admission_year: '2025',
  }),
})

const pdfPath = await response.text()
const certUrl = `https://api.mentalaba.uz/${pdfPath}`
// certUrl → foydalanuvchiga ko'rsatiladi yoki yuklab olish uchun link
```

> ⚠️ Response `Content-Type: application/json` bo'lsa ham body **plain string** — `JSON.parse()` qilmang, `response.text()` ishlating.
