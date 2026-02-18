import re
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Set

import aiohttp
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.builtin import CommandStart
from aiogram.types import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton

from loader import dp
from keyboards.default.userKeyboard import keyboard_user
from states.userStates import Registration
from data.config import SUBJECTS_MAP
from keyboards.inline.user_inline import language_keyboard_button, gender_kb

from utils.send_req import register_user
from data.config import ADMIN_CHAT_ID, CHANNEL_USERNAME, CHANNEL_LINK
from data.config import BASE_URL

PHONE_RE = re.compile(r"^\+?\d{9,15}$")
FULL_NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЎўҚқҒғҲҳЁёO‘o‘G‘g‘ʼ'\-\s]{5,}$")

# ✅ BASE_URL noto'g'ri bo'lsa ham /api/v1 ni qo'shib olamiz (404 muammosi uchun)
API_V1 = (BASE_URL or "").rstrip("/")
if not API_V1.endswith("/api/v1"):
    API_V1 = API_V1 + "/api/v1"

# ✅ Sinf harflari (UI language bo‘yicha)
UZ_CLASS_LETTERS = [
    "A", "B", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
    "N", "O", "P", "Q", "R", "S", "T", "U", "V", "X", "Y", "Z"
]
RU_CLASS_LETTERS = [
    "А", "Б", "В", "Г", "Д", "Е", "Ж", "З", "И", "К", "Л", "М",
    "Н", "О", "П", "Р", "С", "Т", "У", "Ф", "Х", "Ц", "Ч", "Ш",
    "Щ", "Э", "Ю", "Я"
]

TEXTS = {
    "choose_ui_lang": {"uz": "Tilni tanlang:", "ru": "Выберите язык:"},

    "phone_ask": {
        "uz": "Telefon raqamingizni yuboring yoki qo‘lda yozing.\nNamuna: 941234567 (yoki +998941234567)",
        "ru": "Отправьте номер телефона или введите вручную.\nПример: 941234567 (или +998941234567)",
    },
    "phone_invalid": {
        "uz": "❌ Telefon xato.\nNamuna: 941234567 yoki +998941234567",
        "ru": "❌ Неверный номер.\nПример: 941234567 или +998941234567",
    },

    "fio_ask": {"uz": "FIO kiriting:\nNamuna: Ism Familiya", "ru": "Введите ФИО:\nПример: Имя Фамилия"},
    "fio_invalid_2words": {
        "uz": "❌ FIO xato.\nIltimos, Ism va Familiyani kiriting.\nMasalan: Ulug‘bek Erkinov",
        "ru": "❌ ФИО неверно.\nВведите Имя и Фамилию.\nПример: Ulug‘bek Erkinov",
    },
    "fio_invalid_letters": {
        "uz": "❌ FIO faqat harflardan iborat bo‘lishi kerak.\nMasalan: Ulug‘bek Erkinov",
        "ru": "❌ ФИО должно содержать только буквы.\nПример: Ulug‘bek Erkinov",
    },
    "fio_too_short": {
        "uz": "❌ Ism yoki familiya juda qisqa.\nQayta kiriting:",
        "ru": "❌ Имя или фамилия слишком короткие.\nВведите снова:",
    },

    "ask_gender": {"uz": "Jinsini tanlang:", "ru": "Выберите пол:"},
    "gender_invalid": {"uz": "❌ Noto‘g‘ri tanlov.", "ru": "❌ Неверный выбор."},

    "region_ask": {"uz": "Viloyatni tanlang:", "ru": "Выберите регион:"},
    "district_ask": {"uz": "Tumanni tanlang:", "ru": "Выберите район:"},
    "school_pick_ask": {"uz": "Maktabni tanlang:", "ru": "Выберите школу:"},

    "regions_not_found": {"uz": "Viloyatlar topilmadi.", "ru": "Регионы не найдены."},
    "districts_not_found": {"uz": "Tumanlar topilmadi.", "ru": "Районы не найдены."},
    "schools_not_found": {"uz": "Maktablar topilmadi.", "ru": "Школы не найдены."},

    # ✅ class letter
    "class_letter_ask": {
        "uz": "Sinf harfini tanlang (masalan: 11-A, 11-B bo‘lsa faqat harfni tanlang):",
        "ru": "Выберите букву класса (например: если 11-А, 11-Б — выберите только букву):",
    },
    "class_letter_selected": {"uz": "✅ Sinf harfi tanlandi:", "ru": "✅ Выбрана буква класса:"},

    "exam_lang_ask": {"uz": "Imtihon tilini tanlang:", "ru": "Выберите язык экзамена:"},
    "pair_ask": {"uz": "Juftlikni tanlang:", "ru": "Выберите пару:"},
    "pair_not_found": {"uz": "❌ Fan topilmadi. Qayta tanlang.", "ru": "❌ Предмет не найден. Выберите снова."},
    "pair_not_allowed": {"uz": "❌ Bu juftlik ruxsat etilmagan. Qayta tanlang.", "ru": "❌ Эта пара не разрешена. Выберите снова."},

    "confirm_title": {"uz": "🧾 Ma'lumotlaringiz:\n\n", "ru": "🧾 Ваши данные:\n\n"},
    "confirm_question": {"uz": "Tasdiqlaysizmi?", "ru": "Подтверждаете?"},
    "cancelled": {
        "uz": "❌ Ro‘yxatdan o‘tish bekor qilindi.\n/start bosib qayta boshlashingiz mumkin.",
        "ru": "❌ Регистрация отменена.\nНажмите /start чтобы начать заново.",
    },

    "success": {"uz": "✅ Ro‘yxatdan muvaffaqiyatli o‘tdingiz!", "ru": "✅ Регистрация прошла успешно!"},
    "edit_exam_lang": {"uz": "Imtihon tilini qayta tanlang:", "ru": "Выберите язык экзамена снова:"},
    "selected_exam_lang": {"uz": "✅ Tanlandi:", "ru": "✅ Выбрано:"},

    "btn_cancel": {"uz": "❌ Bekor qilish", "ru": "❌ Отмена"},
    "btn_back": {"uz": "⬅️ Orqaga", "ru": "⬅️ Назад"},
}

# ✅ Confirm label’lar (UI language bo‘yicha) — EN aralashmaydi
CONF_LABELS = {
    "phone": {"uz": "📞 Telefon", "ru": "📞 Телефон"},
    "fio": {"uz": "👤 FIO", "ru": "👤 ФИО"},
    "gender": {"uz": "👥 Jinsi", "ru": "👥 Пол"},
    "region": {"uz": "🌍 Viloyat", "ru": "🌍 Регион"},
    "district": {"uz": "🏙 Tuman", "ru": "🏙 Район"},
    "school": {"uz": "🏫 Maktab", "ru": "🏫 Школа"},  # ✅ NAME/NUMBER show
    "class_letter": {"uz": "🏷 Sinf harfi", "ru": "🏷 Буква класса"},
    "exam_lang": {"uz": "🗣 Imtihon tili", "ru": "🗣 Язык экзамена"},
    "subj1": {"uz": "📘 1-fan", "ru": "📘 Предмет 1"},
    "subj2": {"uz": "📗 2-fan", "ru": "📗 Предмет 2"},
}

GENDER_LABELS = {
    "male": {"uz": "Erkak", "ru": "Мужской"},
    "female": {"uz": "Ayol", "ru": "Женский"},
}

EXAM_LANG_LABELS = {
    "uz": {"uz": "O‘zbekcha", "ru": "Узбекский"},
    "ru": {"uz": "Ruscha", "ru": "Русский"},
}


def tr(ui_lang: str, key: str) -> str:
    return TEXTS.get(key, {}).get(ui_lang, TEXTS.get(key, {}).get("uz", ""))


def lbl(ui_lang: str, key: str) -> str:
    return CONF_LABELS.get(key, {}).get(ui_lang, CONF_LABELS.get(key, {}).get("uz", key))


def pretty_register_error(raw: str, ui_lang: str = "uz") -> str:
    raw = str(raw or "")
    m = re.search(r"(\{.*\})", raw)
    detail = None

    if m:
        try:
            payload = json.loads(m.group(1))
            detail = payload.get("detail")
        except Exception:
            detail = None

    if raw.strip().startswith("{") and raw.strip().endswith("}"):
        try:
            p = json.loads(raw)
            if isinstance(p, dict) and "text" in p and "status" in p:
                raw = p.get("text") or raw
        except Exception:
            pass

    if not detail:
        return raw[:700]

    mapping = {
        "User already exists": {
            "uz": "🚫 Siz allaqachon ro‘yxatdan o‘tib bo‘lgansiz.\n🔁 /start bosib davom eting yoki @Mentalaba_help bilan bog‘laning.",
            "ru": "🚫 Вы уже зарегистрированы.\n🔁 Нажмите /start чтобы продолжить или свяжитесь с @Mentalaba_help.",
        },
        "Invalid phone": {
            "uz": "📞 Telefon raqam noto‘g‘ri formatda.\nNamuna: 941234567 yoki +998941234567",
            "ru": "📞 Неверный формат номера.\nПример: 941234567 или +998941234567",
        },
    }

    if detail in mapping:
        return mapping[detail]["uz"] if ui_lang == "uz" else mapping[detail]["ru"]

    return (f"❌ Ошибка: {detail}" if ui_lang == "ru" else f"❌ Xatolik: {detail}")


# ----------------------------
# Bot message cleanup helpers (delete ketma-ketlikda)
# ----------------------------
async def cleanup_bot_messages(bot, chat_id: int, state: FSMContext, except_ids: Optional[Set[int]] = None):
    data = await state.get_data()
    ids: List[int] = data.get("bot_msg_ids", []) or []
    keep: List[int] = []
    for mid in ids:
        if except_ids and mid in except_ids:
            keep.append(mid)
            continue
        try:
            await bot.delete_message(chat_id, mid)
        except Exception:
            pass
    await state.update_data(bot_msg_ids=keep)


async def send_clean(message_obj: types.Message, state: FSMContext, text: str, reply_markup=None, parse_mode=None):
    bot = message_obj.bot
    chat_id = message_obj.chat.id
    await cleanup_bot_messages(bot, chat_id, state)
    msg = await bot.send_message(
        chat_id,
        text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
        disable_web_page_preview=True,
    )
    await state.update_data(bot_msg_ids=[msg.message_id])
    return msg


async def edit_clean(call: types.CallbackQuery, state: FSMContext, text: str, reply_markup=None, parse_mode=None):
    bot = call.bot
    chat_id = call.message.chat.id
    mid = call.message.message_id
    await cleanup_bot_messages(bot, chat_id, state, except_ids={mid})
    try:
        await call.message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=True,
        )
    except Exception:
        pass
    await state.update_data(bot_msg_ids=[mid])


# ----------------------------
# API calls (single endpoint)
# ----------------------------
async def _api_get(url: str, params: Dict[str, str]) -> Dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=25)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params) as r:
            text = await r.text()
            if r.status >= 400:
                return {"ok": False, "status": r.status, "text": text}
            try:
                return await r.json()
            except Exception:
                return {"ok": False, "status": r.status, "text": text}


async def fetch_regions() -> Dict[str, Any]:
    url = f"{API_V1}/admin/districts-and-schools"
    payload = await _api_get(url, {})
    if isinstance(payload, dict) and payload.get("ok") is False:
        return payload
    if not isinstance(payload, dict) or payload.get("type") != "regions":
        return {"ok": False, "status": 500, "text": f"Unexpected regions payload: {payload}"}
    return {"ok": True, "regions": payload.get("data") or []}


async def fetch_districts(region: str) -> Dict[str, Any]:
    url = f"{API_V1}/admin/districts-and-schools"
    payload = await _api_get(url, {"region": region})
    if isinstance(payload, dict) and payload.get("ok") is False:
        return payload
    if not isinstance(payload, dict) or payload.get("type") != "districts":
        return {"ok": False, "status": 500, "text": f"Unexpected districts payload: {payload}"}
    return {"ok": True, "districts": payload.get("data") or []}


async def fetch_schools(region: str, district: str) -> Dict[str, Any]:
    url = f"{API_V1}/admin/districts-and-schools"
    payload = await _api_get(url, {"region": region, "district": district})
    if isinstance(payload, dict) and payload.get("ok") is False:
        return payload
    if not isinstance(payload, dict) or payload.get("type") != "schools":
        return {"ok": False, "status": 500, "text": f"Unexpected schools payload: {payload}"}
    return {"ok": True, "schools": payload.get("data") or []}


# ----------------------------
# Keyboards
# ----------------------------
def ui_lang_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.row(
        InlineKeyboardButton("🇺🇿 O‘zbekcha", callback_data="ui:uz"),
        InlineKeyboardButton("🇷🇺 Русский", callback_data="ui:ru"),
    )
    kb.add(InlineKeyboardButton("❌ Cancel", callback_data="reg_cancel"))
    return kb


def confirm_kb(ui_lang: str):
    kb = InlineKeyboardMarkup(row_width=2)
    if ui_lang == "ru":
        edit = "✏️ Изменить"
        cancel = "❌ Отмена"
        confirm = "✅ Подтвердить"
    else:
        edit = "✏️ Tahrirlash"
        cancel = "❌ Bekor qilish"
        confirm = "✅ Tasdiqlash"

    kb.row(
        InlineKeyboardButton(edit, callback_data="reg_edit"),
        InlineKeyboardButton(cancel, callback_data="reg_cancel"),
    )
    kb.row(InlineKeyboardButton(confirm, callback_data="reg_confirm"))
    return kb


def sub_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("✅ Kanalga obuna bo‘lish", url=CHANNEL_LINK))
    kb.add(InlineKeyboardButton("🔄 Tekshirish", callback_data="check_sub"))
    return kb


def regions_kb(ui_lang: str, regions: List[str]):
    kb = InlineKeyboardMarkup(row_width=2)
    for r in regions[:60]:
        rr = str(r)[:50]
        kb.insert(InlineKeyboardButton(rr, callback_data=f"reg_region:{rr}"))
    kb.add(InlineKeyboardButton(tr(ui_lang, "btn_cancel"), callback_data="reg_cancel"))
    return kb


def districts_kb(ui_lang: str, districts: List[str]):
    kb = InlineKeyboardMarkup(row_width=1)
    for d in districts[:80]:
        dd = str(d)[:50]
        kb.add(InlineKeyboardButton(dd, callback_data=f"reg_district:{dd}"))
    kb.row(
        InlineKeyboardButton(tr(ui_lang, "btn_back"), callback_data="reg_back:region"),
        InlineKeyboardButton(tr(ui_lang, "btn_cancel"), callback_data="reg_cancel"),
    )
    return kb


def schools_kb(ui_lang: str, schools: List[Dict[str, Any]]):
    kb = InlineKeyboardMarkup(row_width=2)
    for s in schools[:120]:
        code = str(s.get("code") or "")
        name = str(s.get("name") or code)
        if not code:
            continue
        kb.insert(InlineKeyboardButton(name[:32], callback_data=f"reg_school:{code}"))
    kb.row(
        InlineKeyboardButton(tr(ui_lang, "btn_back"), callback_data="reg_back:district"),
        InlineKeyboardButton(tr(ui_lang, "btn_cancel"), callback_data="reg_cancel"),
    )
    return kb


def class_letter_kb(ui_lang: str):
    letters = UZ_CLASS_LETTERS if ui_lang == "uz" else RU_CLASS_LETTERS
    kb = InlineKeyboardMarkup(row_width=6)
    for ch in letters:
        kb.insert(InlineKeyboardButton(ch, callback_data=f"reg_class_letter:{ch}"))
    kb.row(
        InlineKeyboardButton(tr(ui_lang, "btn_back"), callback_data="reg_back:school"),
        InlineKeyboardButton(tr(ui_lang, "btn_cancel"), callback_data="reg_cancel"),
    )
    return kb


def pairs_kb(ui_lang: str = "uz"):
    kb = InlineKeyboardMarkup(row_width=1)
    for first_uz, info in SUBJECTS_MAP.items():
        first_label = first_uz if ui_lang == "uz" else info.get("ru", first_uz)
        first_id = info["id"]

        rel_uz_list = info.get("relative", {}).get("uz", [])
        rel_ru_list = info.get("relative", {}).get("ru", [])

        for i, second_uz in enumerate(rel_uz_list):
            second_label = second_uz
            if ui_lang == "ru" and i < len(rel_ru_list):
                second_label = rel_ru_list[i]

            second_info = SUBJECTS_MAP.get(second_uz)
            if not second_info:
                continue
            second_id = second_info["id"]

            kb.add(InlineKeyboardButton(f"{first_label} — {second_label}", callback_data=f"pair:{first_id}|{second_id}"))

    kb.add(InlineKeyboardButton(tr(ui_lang, "btn_cancel"), callback_data="reg_cancel"))
    return kb


# ----------------------------
# Helpers
# ----------------------------
def normalize_phone(phone: str) -> str:
    phone = phone.strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    return phone


def normalize_uz_phone(raw: str) -> str:
    s = (raw or "").strip().replace(" ", "").replace("-", "")
    if s.startswith("+"):
        s = s[1:]
    if s.isdigit() and len(s) == 9:
        return "+998" + s
    if s.isdigit() and len(s) == 12 and s.startswith("998"):
        return "+" + s
    if raw.strip().startswith("+"):
        return raw.strip()
    return "+" + s


def is_phone_ok(text: str) -> bool:
    s = (text or "").strip().replace(" ", "").replace("-", "")
    if not s:
        return False
    if s.isdigit() and len(s) == 9:
        return True
    if s.isdigit() and len(s) == 12 and s.startswith("998"):
        return True
    return bool(PHONE_RE.match(s))


def find_subject_by_id(sid: int):
    for uz_name, info in SUBJECTS_MAP.items():
        if info["id"] == sid:
            return uz_name, info.get("ru", uz_name)
    return None, None


def pair_is_allowed(first_uz: str, second_uz: str) -> bool:
    info = SUBJECTS_MAP.get(first_uz)
    if not info:
        return False
    return second_uz in info.get("relative", {}).get("uz", [])


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _tg_user_link(user: types.User) -> str:
    if user.username:
        return f"@{user.username}"
    return f"<a href='tg://user?id={user.id}'>user</a>"


async def notify_admins(bot, text: str):
    try:
        await bot.send_message(
            ADMIN_CHAT_ID,
            text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception as e:
        print("ADMIN SEND ERROR =>", repr(e), "ADMIN_CHAT_ID=", ADMIN_CHAT_ID)


def build_register_details(data: dict) -> str:
    return (
        f"📞 <b>Phone:</b> <code>{data.get('phone','-')}</code>\n"
        f"🌍 <b>Region:</b> <code>{data.get('region','-')}</code>\n"
        f"🏙 <b>District:</b> <code>{data.get('district','-')}</code>\n"
        f"🏫 <b>School code:</b> <code>{data.get('school_code','-')}</code>\n"
        f"🏷 <b>Class letter:</b> <code>{data.get('class_letter','-')}</code>\n"
        f"🗣 <b>Exam lang:</b> <code>{data.get('exam_lang','-')}</code>\n"
        f"🚻 <b>Gender:</b> <code>{data.get('gender','-')}</code>\n"
        f"📚 <b>Subjects:</b> <code>{data.get('first_subject_id','-')}</code> + <code>{data.get('second_subject_id','-')}</code>"
    )


def build_confirm_text(ui_lang: str, data: dict) -> str:
    exam_lang = data.get("exam_lang", "uz")
    gender = data.get("gender", "male")

    exam_lang_label = EXAM_LANG_LABELS.get(exam_lang, {}).get(ui_lang, exam_lang)
    gender_label = GENDER_LABELS.get(gender, {}).get(ui_lang, gender)

    first_label = data.get("first_subject_uz", "-") if ui_lang == "uz" else (data.get("first_subject_ru") or data.get("first_subject_uz") or "-")
    second_label = data.get("second_subject_uz", "-") if ui_lang == "uz" else (data.get("second_subject_ru") or data.get("second_subject_uz") or "-")

    # ✅ show school_name/number, not code
    school_name = data.get("school_name") or "-"

    lines = [
        tr(ui_lang, "confirm_title").rstrip(),
        "",
        f"{lbl(ui_lang,'phone')}: {data.get('phone','-')}",
        f"{lbl(ui_lang,'fio')}: {data.get('fio','-')}",
        f"{lbl(ui_lang,'gender')}: {gender_label}",
        f"{lbl(ui_lang,'region')}: {data.get('region','-')}",
        f"{lbl(ui_lang,'district')}: {data.get('district','-')}",
        f"{lbl(ui_lang,'school')}: {school_name}",
        f"{lbl(ui_lang,'class_letter')}: {data.get('class_letter','-')}",
        f"{lbl(ui_lang,'exam_lang')}: {exam_lang_label}",
        f"{lbl(ui_lang,'subj1')}: {first_label}",
        f"{lbl(ui_lang,'subj2')}: {second_label}",
        "",
        tr(ui_lang, "confirm_question"),
    ]
    return "\n".join(lines)


# ----------------------------
# Subscribe check
# ----------------------------
async def is_subscribed(user_id: int, bot) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ("creator", "administrator", "member")
    except Exception:
        return False


# ----------------------------
# Handlers
# ----------------------------
@dp.message_handler(CommandStart(), state="*")
async def start_cmd(message: types.Message, state: FSMContext):
    await state.finish()

    # ok = await is_subscribed(message.from_user.id, message.bot)
    # if not ok:
    #     await send_clean(
    #         message, state,
    #         "Davom etish uchun kanalga majburiy obuna bo‘ling:\nObuna bo‘lgach, 🔄 Tekshirish tugmasini bosing.",
    #         reply_markup=sub_kb()
    #     )
    #     return

    await send_clean(
        message, state,
        f"{TEXTS['choose_ui_lang']['uz']} / {TEXTS['choose_ui_lang']['ru']}",
        reply_markup=ui_lang_kb()
    )
    await Registration.ui_lang.set()


@dp.callback_query_handler(lambda c: c.data == "check_sub", state="*")
async def check_sub(call: types.CallbackQuery, state: FSMContext):
    ok = await is_subscribed(call.from_user.id, call.bot)
    if not ok:
        await call.answer("Hali obuna emassiz. Avval obuna bo‘ling ✅", show_alert=True)
        return

    await edit_clean(
        call, state,
        f"{TEXTS['choose_ui_lang']['uz']} / {TEXTS['choose_ui_lang']['ru']}",
        reply_markup=ui_lang_kb()
    )
    await Registration.ui_lang.set()
    await call.answer("✅ Obuna tasdiqlandi")


@dp.callback_query_handler(lambda c: c.data == "reg_cancel", state="*")
async def reg_cancel(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    ui_lang = data.get("ui_lang")
    await state.finish()

    if ui_lang in ("uz", "ru"):
        txt = TEXTS["cancelled"][ui_lang]
    else:
        txt = TEXTS["cancelled"]["uz"] + "\n\n" + TEXTS["cancelled"]["ru"]

    await cleanup_bot_messages(call.bot, call.message.chat.id, state)
    try:
        await call.message.edit_text(txt, reply_markup=None)
    except Exception:
        await call.bot.send_message(call.message.chat.id, txt)


@dp.callback_query_handler(lambda c: c.data in ["ui:uz", "ui:ru"], state=Registration.ui_lang)
async def pick_ui_language(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    ui_lang = call.data.split(":", 1)[1]
    await state.update_data(ui_lang=ui_lang)

    await cleanup_bot_messages(call.bot, call.message.chat.id, state, except_ids={call.message.message_id})
    try:
        await call.message.delete()
    except Exception:
        pass

    msg = await call.bot.send_message(
        call.message.chat.id,
        tr(ui_lang, "phone_ask"),
        reply_markup=keyboard_user,
        disable_web_page_preview=True
    )
    await state.update_data(bot_msg_ids=[msg.message_id])
    await Registration.phone.set()


@dp.message_handler(content_types=types.ContentType.CONTACT, state=Registration.phone)
async def reg_phone_contact(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    phone = normalize_phone(message.contact.phone_number)
    await state.update_data(phone=phone)

    await send_clean(message, state, tr(ui_lang, "fio_ask"), reply_markup=ReplyKeyboardRemove())
    await Registration.fio.set()


@dp.message_handler(state=Registration.phone)
async def reg_phone_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    raw_phone = (message.text or "").strip()
    if not is_phone_ok(raw_phone):
        return await send_clean(message, state, tr(ui_lang, "phone_invalid"))

    phone = normalize_uz_phone(raw_phone)
    await state.update_data(phone=phone)

    await send_clean(message, state, tr(ui_lang, "fio_ask"), reply_markup=ReplyKeyboardRemove())
    await Registration.fio.set()


@dp.message_handler(state=Registration.fio)
async def reg_fio(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    fio = (message.text or "").strip()
    parts = fio.split()

    if len(parts) < 2:
        return await send_clean(message, state, tr(ui_lang, "fio_invalid_2words"))
    if not FULL_NAME_RE.match(fio):
        return await send_clean(message, state, tr(ui_lang, "fio_invalid_letters"))
    if any(len(p) < 2 for p in parts):
        return await send_clean(message, state, tr(ui_lang, "fio_too_short"))

    await state.update_data(fio=fio)

    await send_clean(message, state, tr(ui_lang, "ask_gender"), reply_markup=gender_kb(ui_lang))
    await Registration.gender.set()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("gender:"), state=Registration.gender)
async def reg_gender_cb(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    gender = call.data.split(":", 1)[1]
    if gender not in ("male", "female"):
        await call.answer(tr(ui_lang, "gender_invalid"), show_alert=True)
        return

    await state.update_data(gender=gender)

    res = await fetch_regions()
    if not (isinstance(res, dict) and res.get("ok")):
        await edit_clean(call, state, pretty_register_error(str(res), ui_lang), reply_markup=None)
        return

    regions = res.get("regions") or []
    if not regions:
        await edit_clean(call, state, tr(ui_lang, "regions_not_found"), reply_markup=None)
        return

    await edit_clean(call, state, tr(ui_lang, "region_ask"), reply_markup=regions_kb(ui_lang, regions))
    await Registration.region.set()
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("reg_region:"), state=Registration.region)
async def reg_pick_region(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    region = call.data.split(":", 1)[1]
    await state.update_data(region=region)

    res = await fetch_districts(region=region)
    if not (isinstance(res, dict) and res.get("ok")):
        await edit_clean(call, state, pretty_register_error(str(res), ui_lang), reply_markup=None)
        return

    districts = res.get("districts") or []
    if not districts:
        await edit_clean(call, state, tr(ui_lang, "districts_not_found"), reply_markup=None)
        return

    await edit_clean(call, state, tr(ui_lang, "district_ask"), reply_markup=districts_kb(ui_lang, districts))
    await Registration.district.set()


@dp.callback_query_handler(lambda c: c.data.startswith("reg_district:"), state=Registration.district)
async def reg_pick_district(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    district = call.data.split(":", 1)[1]
    await state.update_data(district=district)

    region = data.get("region")
    res = await fetch_schools(region=region, district=district)
    if not (isinstance(res, dict) and res.get("ok")):
        await edit_clean(call, state, pretty_register_error(str(res), ui_lang), reply_markup=None)
        return

    schools = res.get("schools") or []
    if not schools:
        await edit_clean(call, state, tr(ui_lang, "schools_not_found"), reply_markup=None)
        return

    # ✅ code -> name mapping
    school_map = {}
    for s in schools:
        code = str(s.get("code") or "")
        name = str(s.get("name") or code)
        if code:
            school_map[code] = name
    await state.update_data(school_map=school_map)

    await edit_clean(call, state, tr(ui_lang, "school_pick_ask"), reply_markup=schools_kb(ui_lang, schools))
    await Registration.school.set()


@dp.callback_query_handler(lambda c: c.data.startswith("reg_school:"), state=Registration.school)
async def reg_pick_school(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    school_code = call.data.split(":", 1)[1]
    school_map = data.get("school_map", {}) or {}
    school_name = school_map.get(school_code, school_code)

    # ✅ API uchun code, UI uchun name
    await state.update_data(school_code=school_code, school_name=school_name)

    await edit_clean(
        call, state,
        (f"✅ Maktab tanlandi: {school_name}" if ui_lang == "uz" else f"✅ Школа выбрана: {school_name}"),
        reply_markup=None
    )

    msg = await call.bot.send_message(
        call.message.chat.id,
        tr(ui_lang, "class_letter_ask"),
        reply_markup=class_letter_kb(ui_lang),
        disable_web_page_preview=True
    )
    await state.update_data(bot_msg_ids=[msg.message_id])
    await Registration.class_letter.set()


@dp.callback_query_handler(lambda c: c.data.startswith("reg_class_letter:"), state=Registration.class_letter)
async def reg_pick_class_letter(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    letter = call.data.split(":", 1)[1].strip()
    await state.update_data(class_letter=letter)

    await edit_clean(call, state, f"{tr(ui_lang, 'class_letter_selected')} {letter}", reply_markup=None)

    msg = await call.bot.send_message(
        call.message.chat.id,
        tr(ui_lang, "exam_lang_ask"),
        reply_markup=language_keyboard_button,
        disable_web_page_preview=True
    )
    await state.update_data(bot_msg_ids=[msg.message_id])
    await Registration.exam_lang.set()


@dp.callback_query_handler(lambda c: c.data.startswith("reg_back:"), state="*")
async def reg_back(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")
    step = call.data.split(":", 1)[1]

    if step == "region":
        res = await fetch_regions()
        if not (isinstance(res, dict) and res.get("ok")):
            await edit_clean(call, state, pretty_register_error(str(res), ui_lang), reply_markup=None)
            return
        regions = res.get("regions") or []
        await edit_clean(call, state, tr(ui_lang, "region_ask"), reply_markup=regions_kb(ui_lang, regions))
        await Registration.region.set()
        return

    if step == "district":
        region = data.get("region")
        res = await fetch_districts(region=region)
        if not (isinstance(res, dict) and res.get("ok")):
            await edit_clean(call, state, pretty_register_error(str(res), ui_lang), reply_markup=None)
            return
        districts = res.get("districts") or []
        await edit_clean(call, state, tr(ui_lang, "district_ask"), reply_markup=districts_kb(ui_lang, districts))
        await Registration.district.set()
        return

    if step == "school":
        region = data.get("region")
        district = data.get("district")
        res = await fetch_schools(region=region, district=district)
        if not (isinstance(res, dict) and res.get("ok")):
            await edit_clean(call, state, pretty_register_error(str(res), ui_lang), reply_markup=None)
            return
        schools = res.get("schools") or []
        if not schools:
            await edit_clean(call, state, tr(ui_lang, "schools_not_found"), reply_markup=None)
            return

        school_map = {}
        for s in schools:
            code = str(s.get("code") or "")
            name = str(s.get("name") or code)
            if code:
                school_map[code] = name
        await state.update_data(school_map=school_map)

        await edit_clean(call, state, tr(ui_lang, "school_pick_ask"), reply_markup=schools_kb(ui_lang, schools))
        await Registration.school.set()
        return


@dp.callback_query_handler(lambda c: c.data in ["uz", "ru"], state=Registration.exam_lang)
async def pick_exam_language(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    exam_lang = call.data
    await state.update_data(exam_lang=exam_lang)

    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    label = "🇺🇿 O‘zbekcha" if exam_lang == "uz" else "🇷🇺 Русский"
    await edit_clean(call, state, f"{tr(ui_lang, 'selected_exam_lang')} {label}", reply_markup=None)

    msg = await call.bot.send_message(
        call.message.chat.id,
        tr(ui_lang, "pair_ask"),
        reply_markup=pairs_kb(ui_lang=ui_lang),
        disable_web_page_preview=True
    )
    await state.update_data(bot_msg_ids=[msg.message_id])
    await Registration.second_subject.set()


@dp.callback_query_handler(lambda c: c.data.startswith("pair:"), state=Registration.second_subject)
async def pick_pair(call: types.CallbackQuery, state: FSMContext):
    await call.answer()

    payload = call.data.split("pair:", 1)[1]
    first_id_str, second_id_str = payload.split("|", 1)

    first_id = int(first_id_str)
    second_id = int(second_id_str)

    first_uz, first_ru = find_subject_by_id(first_id)
    second_uz, second_ru = find_subject_by_id(second_id)

    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    if not first_uz or not second_uz:
        msg = await call.bot.send_message(call.message.chat.id, tr(ui_lang, "pair_not_found"))
        await state.update_data(bot_msg_ids=[msg.message_id])
        return

    if not pair_is_allowed(first_uz, second_uz):
        msg = await call.bot.send_message(call.message.chat.id, tr(ui_lang, "pair_not_allowed"))
        await state.update_data(bot_msg_ids=[msg.message_id])
        return

    await state.update_data(
        first_subject_id=first_id,
        first_subject_uz=first_uz,
        first_subject_ru=first_ru,
        second_subject_id=second_id,
        second_subject_uz=second_uz,
        second_subject_ru=second_ru,
    )

    data = await state.get_data()
    confirm_text = build_confirm_text(ui_lang, data)

    await edit_clean(call, state, confirm_text, reply_markup=confirm_kb(ui_lang))
    await Registration.verify.set()


@dp.callback_query_handler(lambda c: c.data in ["reg_confirm", "reg_edit"], state=Registration.verify)
async def reg_verify(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    if call.data == "reg_edit":
        msg = await call.bot.send_message(
            call.message.chat.id,
            tr(ui_lang, "edit_exam_lang"),
            reply_markup=language_keyboard_button,
            disable_web_page_preview=True
        )
        await state.update_data(bot_msg_ids=[msg.message_id])
        await Registration.exam_lang.set()
        return

    await cleanup_bot_messages(call.bot, call.message.chat.id, state, except_ids={call.message.message_id})
    user_msg = await call.bot.send_message(call.message.chat.id, tr(ui_lang, "success"))
    await state.update_data(bot_msg_ids=[user_msg.message_id])
    print(data)
    try:
        res = await register_user(
            bot_id=str(call.from_user.id),
            full_name=data["fio"],
            phone=data["phone"],
            school_code=data["school_code"],  # ✅ APIga CODE ketadi
            first_subject_id=data["first_subject_id"],
            second_subject_id=data["second_subject_id"],
            password="1111",
            language=data.get("exam_lang", "uz"),
            gender=data.get("gender", "male"),
            district=data.get("district"),
            region=data.get("region"),
            group_name=data.get("class_letter"),
        )

        if isinstance(res, dict) and res.get("ok"):
            admin_text = (
                f"🧾 <b>REGISTER SUCCESS</b>\n"
                f"🕒 <b>Time:</b> {now_str()}\n"
                f"👤 <b>User:</b> {_tg_user_link(call.from_user)}\n"
                f"🆔 <b>Chat ID:</b> <code>{call.from_user.id}</code>\n"
                f"📝 <b>Full name:</b> {data.get('fio','-')}\n\n"
                f"{build_register_details(data)}"
            )
            await notify_admins(call.bot, admin_text)
            await state.finish()
            return

        err_txt = res.get("text") if isinstance(res, dict) else str(res)
        try:
            await user_msg.edit_text(pretty_register_error(str(err_txt), ui_lang=ui_lang))
        except Exception:
            await call.bot.send_message(call.message.chat.id, pretty_register_error(str(err_txt), ui_lang=ui_lang))

        admin_text = (
            f"🧾 <b>REGISTER FAIL</b>\n"
            f"🕒 <b>Time:</b> {now_str()}\n"
            f"👤 <b>User:</b> {_tg_user_link(call.from_user)}\n"
            f"🆔 <b>Chat ID:</b> <code>{call.from_user.id}</code>\n"
            f"📝 <b>Full name:</b> {data.get('fio','-')}\n\n"
            f"{build_register_details(data)}\n\n"
            f"❗ <b>Error:</b>\n<code>{str(err_txt)[:1200]}</code>"
        )
        await notify_admins(call.bot, admin_text)

    except Exception as e:
        try:
            await user_msg.edit_text(pretty_register_error(str(e), ui_lang=ui_lang))
        except Exception:
            await call.bot.send_message(call.message.chat.id, pretty_register_error(str(e), ui_lang=ui_lang))

        admin_text = (
            f"🧾 <b>REGISTER FAIL</b>\n"
            f"🕒 <b>Time:</b> {now_str()}\n"
            f"👤 <b>User:</b> {_tg_user_link(call.from_user)}\n"
            f"🆔 <b>Chat ID:</b> <code>{call.from_user.id}</code>\n"
            f"📝 <b>Full name:</b> {data.get('fio','-')}\n\n"
            f"{build_register_details(data)}\n\n"
            f"❗ <b>Exception:</b>\n<code>{str(e)[:1200]}</code>"
        )
        await notify_admins(call.bot, admin_text)
