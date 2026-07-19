# Maktab turi (`school.type`) — bot va frontend integratsiyasi

> Backend `c4d8a2e91f3b` migration + `d9c890b` commit'da `schools.type` ustun qo'shildi. Endi har maktabning **turi** bor: `school` (umumta'lim), `litsey` (akademik litsey), `texnikum` (kasb-hunar texnikumi).

Bu hujjat 2 audience uchun:
- **Bot dasturchi** — Telegram bot orqali foydalanuvchini register qilayotganda nima o'zgaradi
- **Frontend dasturchi** — super-admin panelida filter, badge, import nima qilish kerak

---

## 1. Asoslar

### Maktab turi qiymatlari

| Qiymat | Tavsif | Misol |
|---|---|---|
| `"school"` | Umumta'lim maktabi (default) | "41-maktab" |
| `"litsey"` | Akademik litsey | "Toshkent IT-litseyi" |
| `"texnikum"` | Kasb-hunar texnikumi | "Toshkent qurilish texnikumi" |

**NULL bo'lishi mumkin emas** — DB'da default `"school"`. Migration paytida eski rowlarning hammasi avtomatik `"school"` ga set qilingan.

### Qaysi joyda turadi?

- Faqat `schools` jadvalida — `User` rowida turi yo'q
- User'ning maktab turi `user.school_code` → `schools.code` join orqali aniqlanadi
- Yangi userlar register bo'lganda backend avtomatik `school.type`ni saqlaydi

---

## 2. Bot tomon (Telegram registration)

### Hozirgi flow (o'zgarmaydi)

User Telegram bot orqali register qilganda:
```
1. Tilni tanlash (uz/ru)
2. Test turini tanlash (offline / online)
3. Viloyat tanlash
4. Tuman tanlash
5. Maktab kodini kiritish (yoki ro'yxatdan tanlash)
6. F.I.SH, telefon, fanlar...
```

**Maktab kodi → backend qaysi `school` ekanini biladi → school.type avtomatik biriktiriladi.** Bot kodida hech qanday o'zgarish kerak emas.

### Agar bot maktab ro'yxatini ko'rsatadigan bo'lsa

Hozir bot user'ga school_code'ni qo'lda yozib kiritishni so'raydi (yoki "list" tugmasi bo'lsa, lekin ko'p schools bilan praktik emas). Agar bot UX'ini yangilamoqchi bo'lsangiz — masalan, user "Litsey/Texnikum/Maktab" tanlasa va keyin shu turdagi maktablar ro'yxati chiqsa — quyidagicha qiling:

#### Bot tomonidan backend'ga so'rov

```http
GET https://dtmpaperreaderapi.mentalaba.uz/api/v1/dtm/schools
  ?region=Toshkent+shahar
  &district=Shayxontohur+tumani
  &type=litsey
  &limit=200
Headers: X-API-Key: <SECRET_KEY>
```

Response item'i (har maktab uchun):
```json
{
  "id": 41,
  "code": "SHAY41",
  "name": "41-maktab",
  "type": "school",
  "region": "Toshkent shahar",
  "district": "Shayxontohur tumani",
  ...
}
```

Bot user'ga inline keyboard chiqaradi:
```
┌─────────────────────────────┐
│ Maktab turini tanlang:       │
│ 🏫 Maktab                    │
│ 🎓 Litsey                    │
│ 🔧 Texnikum                  │
└─────────────────────────────┘
```

User tanlasa, bot o'sha turdagi schools ro'yxatini ko'rsatadi.

#### Telegram pysxology (uz tilida)

Bot tugmalari uchun tavsiya etilgan matnlar:
- `🏫 Umumta'lim maktabi`
- `🎓 Akademik litsey`
- `🔧 Kasb-hunar texnikumi`

(yoki rasm/emoji shartmas — qisqa "Maktab", "Litsey", "Texnikum" ham yetadi)

### Bot — register payload

Hozirgi register endpoint (`POST /api/v1/auth/register`) `school_code`ni qabul qiladi va boshqa hech narsani. **O'zgarish kerak emas** — bot oddiygina school_code yuborsa, backend o'zi `school.type`ni biladi.

---

## 3. Frontend tomon (super-admin panel)

### Mavjud dokumentatsiya

To'liq endpoint spec → [`dtm-api-frontend.md`](dtm-api-frontend.md) ichidagi `GET /dtm/schools` bo'limi.

Bu hujjat — **frontend nimani o'zgartirishi kerak**ligini sanab ko'rsatadi.

### Cleanup task'lar

#### A) Maktablar grid'iga **type ustuni** qo'shish

`/dtm/schools` har item'da endi `type` field bor:

```ts
interface SchoolEntity {
  // ...
  type: "school" | "litsey" | "texnikum";
  // ...
}
```

Grid kodida (masalan `DTMSchoolsList.tsx`):
```tsx
<td>
  {school.type === "litsey" && <Badge color="purple">Litsey</Badge>}
  {school.type === "texnikum" && <Badge color="orange">Texnikum</Badge>}
  {school.type === "school" && <Badge color="gray">Maktab</Badge>}
</td>
```

#### B) Filter dropdown'iga **maktab turi** qo'shish

`/dtm/filter-options` endi `school_types` qaytaradi:

```json
{
  "school_types": ["school", "litsey", "texnikum"],
  ...
}
```

Multi-select dropdown:
```tsx
<MultiSelect
  label="Maktab turi"
  options={[
    {value: "school",   label: "Umumta'lim maktab"},
    {value: "litsey",   label: "Akademik litsey"},
    {value: "texnikum", label: "Kasb-hunar texnikum"},
  ]}
  value={selectedTypes}
  onChange={setSelectedTypes}
/>
```

So'rov yuborilganda `type[]=litsey&type[]=texnikum` formatida:
```ts
fetchSchools({
  types: selectedTypes,  // ["litsey", "texnikum"]
  // ... boshqa filter'lar
});
```

#### C) Compare sahifa — type bo'yicha guruhlash (ixtiyoriy)

Maktablarni bir-biri bilan solishtirish chartlarida (compare-mode) `type` bo'yicha alohida guruh ko'rsatish foydali bo'lishi mumkin:
- "Toshkent shahridagi litseylar avg ball: 92.3"
- "Toshkent shahridagi texnikumlar avg ball: 65.1"

```ts
const groupedByType = items.reduce((acc, school) => {
  (acc[school.type] ??= []).push(school);
  return acc;
}, {} as Record<string, SchoolEntity[]>);

const litseyAvg = avg(groupedByType.litsey?.map(s => s.avg_total_ball) ?? []);
```

#### D) Excel import sahifasi — `tip` ustunini ko'rsatish

Operator excel orqali maktablar yuklayotganda, eski format'ga `tip` ustunini qo'shish mumkin. Frontend import sahifasida foydalanuvchiga ko'rsatish kerak:

```
Excel formati:
| viloyat | tuman | maktab_nomi | kod | tip          | admin_fio | login | parol |
|---------|-------|-------------|-----|--------------|-----------|-------|-------|
| Toshk.. | Shay.. | 41-maktab  | SHAY41 | school    | ...       | ...   | ...   |
| Toshk.. | Shay.. | IT-litsey  | LIT01  | litsey    | ...       | ...   | ...   |
| Toshk.. | Shay.. | Qurilish T | TEX02  | texnikum  | ...       | ...   | ...   |
```

`tip` ustuni **ixtiyoriy** — bo'lmasa default `school`.

**Backend qabul qiladigan qiymatlar** (alias normalizatsiyasi):

| Excel'da yozilishi mumkin | Saqlanadi |
|---|---|
| `school`, `maktab`, `umumiy` | `school` |
| `litsey`, `lyceum`, `akadem litsey`, `akademik litsey` | `litsey` |
| `texnikum`, `technicum`, `tekhnikum`, `kasb-hunar` | `texnikum` |

Boshqa qiymatlar → `school` (default).

#### E) Maktab detail sahifasi

`/dtm/schools` natijasida har maktab item'ida `type` bor — detail sahifasi sarlavhasiga qo'shish:

```tsx
<h1>
  {school.name}
  <SchoolTypeBadge type={school.type} />
</h1>
```

---

## 4. Frontend uchun TypeScript yordamchi

```ts
// src/lib/school-types.ts
export type SchoolType = "school" | "litsey" | "texnikum";

export const SCHOOL_TYPE_LABELS: Record<SchoolType, string> = {
  school: "Umumta'lim maktab",
  litsey: "Akademik litsey",
  texnikum: "Kasb-hunar texnikum",
};

export const SCHOOL_TYPE_SHORT: Record<SchoolType, string> = {
  school: "Maktab",
  litsey: "Litsey",
  texnikum: "Texnikum",
};

export const SCHOOL_TYPE_COLORS: Record<SchoolType, string> = {
  school: "gray",
  litsey: "purple",
  texnikum: "orange",
};

export function schoolTypeLabel(t: string | undefined | null): string {
  if (!t) return SCHOOL_TYPE_LABELS.school;
  return SCHOOL_TYPE_LABELS[t as SchoolType] ?? SCHOOL_TYPE_LABELS.school;
}
```

Foydalanish:
```tsx
import { schoolTypeLabel, SCHOOL_TYPE_COLORS } from "@/lib/school-types";

<Badge color={SCHOOL_TYPE_COLORS[school.type] ?? "gray"}>
  {schoolTypeLabel(school.type)}
</Badge>
```

---

## 5. Curl misollar

```bash
SECRET="<your_key>"
B="https://dtmpaperreaderapi.mentalaba.uz/api/v1"

# 1. Faqat litseylar
curl "$B/dtm/schools?type=litsey&limit=20" -H "X-API-Key: $SECRET"

# 2. Litsey + texnikum birga
curl "$B/dtm/schools?type[]=litsey&type[]=texnikum" -H "X-API-Key: $SECRET"

# 3. Toshkent shahridagi texnikumlar, eng ko'p ishtirokchi tartibida
curl "$B/dtm/schools?region=Toshkent+shahar&type=texnikum&order_by=registered_count&order=desc" \
     -H "X-API-Key: $SECRET"

# 4. Filter dropdown ma'lumotlari
curl "$B/dtm/filter-options" -H "X-API-Key: $SECRET" | jq '.school_types'
# → ["school", "litsey", "texnikum"]

# 5. CSV eksport — faqat litseylar
curl "$B/dtm/users.csv?school_code=LIT01" -H "X-API-Key: $SECRET" -o lit01.csv
# (user'lar CSV'sida school_name bor — turi alohida ustun emas, lekin school_code orqali bog'lash mumkin)
```

---

## 6. Tekshirish (deploy'dan keyin)

### Server tomon
```bash
# Migration apply qilinganini tekshirish
psql $DB_URL -c "\d schools" | grep type
# → type | character varying | not null default 'school'

# Mavjud schools type bo'yicha
psql $DB_URL -c "SELECT type, COUNT(*) FROM schools GROUP BY type ORDER BY type;"
# → school | 442
# → (litsey/texnikum hali yo'q — operator excel orqali yuklasa paydo bo'ladi)
```

### Frontend tomon
1. **Schools grid** — yangi `Type` ustuni paydo bo'lishi
2. **Filter panel** — "Maktab turi" multi-select tugmasi
3. **Detail sahifa** — sarlavha yonida badge
4. **Excel import** — namuna template'ga `tip` ustuni qo'shilgan

### Bot tomon
- Hozirgi register flow ishlaydi (school_code orqali type avtomatik biriktiriladi)
- UX yangilanishi (litsey/texnikum tanlash) — ixtiyoriy, alohida task

---

## 7. Migration tartib (server uchun)

```bash
cd /data/schools/mentalaba-dtm-paper-reader
git pull --no-rebase origin feature/online-test-tg-polish

# Migration mavjud bo'lsa skip, yo'q bo'lsa qo'shadi (idempotent)
venv/bin/alembic upgrade head

# Server restart
pm2 restart <name>

# Tekshirish
curl -s "http://localhost:8000/api/v1/dtm/filter-options" \
     -H "X-API-Key: $SECRET" | jq '.school_types'
# Kutilgan: ["school", "litsey", "texnikum"]
```

Migration **xavfsiz** — DEFAULT bilan ustun qo'shadi, eski rowlar avtomatik `school` qiymatini oladi. Hech qanday data lost bo'lmaydi.

---

## 8. Xulosa

| Qadam | Kim | Holat |
|---|---|---|
| Backend migration + endpoint + filter | backend | ✅ tayyor (`d9c890b`) |
| Server deploy + restart | DevOps | bajariladi |
| Frontend grid type column + badge | frontend | ⏳ shu doc bo'yicha |
| Frontend type filter dropdown | frontend | ⏳ shu doc bo'yicha |
| Excel import template'ga `tip` qator | frontend | ⏳ namuna fayl yangilash |
| Bot register UX (litsey/texnikum tanlash) | bot | ⏳ ixtiyoriy, alohida task |

Frontend dasturchi shu fayl bo'yicha cleanup qilsa — admin panelda litsey/texnikum maktablari to'liq ishlay boshlaydi.
