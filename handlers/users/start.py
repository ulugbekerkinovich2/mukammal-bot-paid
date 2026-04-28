import re
import os
import json
import uuid
import html
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, List, Optional, Set

import aiohttp
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text, Command
from aiogram.dispatcher.filters.builtin import CommandStart
from aiogram.types import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton

from loader import dp
from keyboards.default.userKeyboard import keyboard_user
from states.userStates import Registration
from data.config import SUBJECTS_MAP
from keyboards.inline.user_inline import language_keyboard_button, gender_kb

from utils.send_req import (
    register_user,
    get_dtm_result,
    check_user_exists,
    check_user_exists_by_type,
    REGISTER_RETRY_TIMEOUT_SEC,
    REGISTER_RETRY_CONNECT_SEC,
    REGISTER_RETRY_ATTEMPTS,
)
from data.config import ADMIN_CHAT_ID, CHANNEL_USERNAME, CHANNEL_LINK
from data.config import BASE_URL

import asyncio
from collections import defaultdict
import logging

logger = logging.getLogger("registration_bot")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

CERTIFICATE_DOWNLOAD_URL = "https://mentalaba.uz/auth?sign-in"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CERTIFICATE_GUIDE_VIDEO_PATH = Path(
    os.getenv("CERTIFICATE_GUIDE_VIDEO_PATH", str(PROJECT_ROOT / "media" / "sertifikatni-yuklab-olish.mp4"))
)
CERTIFICATE_GUIDE_CAPTION = (
    "<b>Maxsus Sertifikatni olish uchun video qo‘llanma</b>\n\n"
    "<blockquote>Mentalaba.uz hamkor OTMlariga imtihonsiz kirish imkoniyatidan "
    "foydalanish uchun hoziroq platformadan ro‘yxatdan o‘ting, profilingizni "
    "to‘ldiring va sertifikatingizni yuklab oling.</blockquote>"
)
QUEUE_STATS_INTERVAL_SEC = int(os.getenv("QUEUE_STATS_INTERVAL_SEC", "3600"))
FAILED_RETRY_SWEEP_INTERVAL_SEC = int(os.getenv("FAILED_RETRY_SWEEP_INTERVAL_SEC", "600"))
FAILED_RETRY_MAX_COUNT = int(os.getenv("FAILED_RETRY_MAX_COUNT", "4"))

# =========================
# Queue (BOT-side) + JSON persistence
# =========================
JOBS_PATH = os.getenv("REGISTER_JOBS_PATH", "register_jobs.json")
JOBS_FILE_LOCK = asyncio.Lock()

# Per-user test_type flags persistence
# Schema: {chat_id: {"offline": bool, "online": bool, "last": "offline"|"online"}}
USER_INTENTS_PATH = os.getenv("USER_INTENTS_PATH", "user_intents.json")
USER_INTENTS_LOCK = asyncio.Lock()
USER_INTENTS: Dict[str, Dict[str, Any]] = {}


def _load_user_intents() -> None:
    global USER_INTENTS
    try:
        with open(USER_INTENTS_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f) or {}
    except (FileNotFoundError, json.JSONDecodeError):
        raw = {}
    USER_INTENTS = {}
    for cid, val in raw.items():
        if isinstance(val, str):
            USER_INTENTS[cid] = {
                "offline": val == "offline",
                "online": val == "online",
                "last": val,
            }
        elif isinstance(val, dict):
            USER_INTENTS[cid] = {
                "offline": bool(val.get("offline")),
                "online": bool(val.get("online")),
                "last": val.get("last") or ("online" if val.get("online") else "offline"),
            }


async def _save_user_intents() -> None:
    async with USER_INTENTS_LOCK:
        tmp = USER_INTENTS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(USER_INTENTS, f, ensure_ascii=False, indent=2)
        os.replace(tmp, USER_INTENTS_PATH)


def has_user_flag(chat_id: int, intent: str) -> bool:
    return bool(USER_INTENTS.get(str(chat_id), {}).get(intent))


async def set_user_intent(chat_id: int, intent: str) -> None:
    rec = USER_INTENTS.setdefault(
        str(chat_id), {"offline": False, "online": False, "last": intent}
    )
    rec[intent] = True
    rec["last"] = intent
    await _save_user_intents()


def get_user_intent(chat_id: int) -> Optional[str]:
    """Returns the most recently used flow ('last'), or None if user has no flags."""
    rec = USER_INTENTS.get(str(chat_id))
    return rec.get("last") if rec else None


async def clear_user_intent(chat_id: int) -> None:
    if USER_INTENTS.pop(str(chat_id), None) is not None:
        await _save_user_intents()


_load_user_intents()

@dataclass
class RegisterJob:
    job_id: str
    user_id: int
    chat_id: int
    ui_lang: str
    payload: Dict[str, Any]

REGISTER_QUEUE: "asyncio.Queue[RegisterJob]" = asyncio.Queue(maxsize=5000)
REGISTER_JOBS: Dict[str, Dict[str, Any]] = {}   # job_id -> {status, payload, ...}
USER_LAST_JOB: Dict[int, str] = {}              # user_id -> job_id

REGISTER_WORKERS_STARTED = False
REGISTER_WORKERS: List[asyncio.Task] = []
QUEUE_STATS_TASK: Optional[asyncio.Task] = None
FAILED_RETRY_SWEEP_TASK: Optional[asyncio.Task] = None
CERTIFICATE_GUIDE_FILE_ID: Optional[str] = None

# har bir user uchun request lock
USER_LOCKS = defaultdict(asyncio.Lock)

PHONE_RE = re.compile(r"^\+?\d{9,15}$")
FULL_NAME_RE = re.compile(
    r"^[A-Za-zА-Яа-яЎўҚқҒғҲҳЁёʻʼ'`\-\s]{5,}$",
    re.UNICODE
)
NAME_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЎўҚқҒғҲҳЁёʻʼ`\'‘’‘]+", re.UNICODE)

# Familiya ko'pincha shunday tugaydi (RU/UZ amaliyot)
SURNAME_SUFFIXES = (
    "ov", "ev", "yov", "yev", "ova", "eva",
    "skiy", "sky", "skaya", "ska", "ko", "enko",
    "yan", "ian", "vich", "vna"
)

DROP_WORDS = {
    "ogli", "o‘gli", "o'g'li", "oʻgʻli", "угли",
    "qizi", "kizi", "қызы", "қизи", "кизи",
    "оглы", "кызы"
}

def _smart_title_word(w: str) -> str:
    w = (w or "").strip()
    if not w:
        return ""
    return w[:1].upper() + w[1:].lower()

def _looks_like_surname(token: str) -> bool:
    t = (token or "").strip().lower()
    if not t:
        return False
    if t.endswith(SURNAME_SUFFIXES):
        return True
    return False

def normalize_fio_to_surname_name(raw: str) -> Optional[str]:
    """
    User qanday yozmasin:
      - 'Ism Familiya'
      - 'Familiya Ism'
      - 'Familiya Ism Otchestva'
      - 'Ism Familiya ... qizi/ogli'
    => 'Familiya Ism' qilib qaytaradi.
    """
    if not raw:
        return None

    s = re.sub(r"\s+", " ", str(raw).strip())
    if not s:
        return None

    tokens = [t for t in NAME_TOKEN_RE.findall(s) if t]
    if len(tokens) < 2:
        return None

    cleaned = []
    for t in tokens:
        tl = t.lower()
        if tl in DROP_WORDS:
            break
        cleaned.append(t)

    if len(cleaned) < 2:
        cleaned = tokens[:2]

    a, b = cleaned[0], cleaned[1]

    if _looks_like_surname(b) and not _looks_like_surname(a):
        surname, name = b, a
    else:
        surname, name = a, b

    surname = _smart_title_word(surname)
    name = _smart_title_word(name)

    if len(surname) < 2 or len(name) < 2:
        return None

    return f"{surname} {name}"

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

    "fio_ask": {"uz": "Familiya Ism kiriting:\nNamuna: Familiya Ism ", "ru": "Введите ФИО:\nПример: Фамилия Имя"},
    "fio_invalid_2words": {
        "uz": "❌ FIO xato.\nIltimos, Ism va Familiyani kiriting.\nMasalan: Erkinov Ulug‘bek",
        "ru": "❌ ФИО неверно.\nВведите Имя и Фамилию.\nПример: Erkinov Ulug‘bek",
    },
    "fio_invalid_letters": {
        "uz": "❌ FIO faqat harflardan iborat bo‘lishi kerak.\nMasalan: Erkinov Ulug‘bek",
        "ru": "❌ ФИО должно содержать только буквы.\nПример: Erkinov Ulug‘bek",
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
    "choose_test_type": {
        "uz": "🎯 Tanlang:",
        "ru": "🎯 Выберите:",
    },
    "btn_offline_test": {"uz": "📄 Offline test", "ru": "📄 Offline тест"},
    "btn_online_test": {"uz": "🌐 Online test", "ru": "🌐 Online тест"},
    "btn_reregister": {"uz": "🔄 Qayta ro'yxatdan o'tish", "ru": "🔄 Зарегистрироваться заново"},
    "offline_menu_text": {
        "uz": "📄 <b>Offline test rejimi</b>\n\nQuyidagi tugmalardan foydalaning. Natijangizni ko'rish yoki sertifikat olish uchun tugmalar pastda.",
        "ru": "📄 <b>Offline тест режим</b>\n\nИспользуйте кнопки ниже. Кнопки для просмотра результата и получения сертификата находятся внизу.",
    },
    "online_ready": {
        "uz": "🌐 <b>Online test</b>\n\nRo'yxatdan muvaffaqiyatli o'tdingiz. Quyidagi tugmani bosing va testni boshlang.\n\n⏱ 90 savol, 3 soat.",
        "ru": "🌐 <b>Online тест</b>\n\nВы успешно зарегистрированы. Нажмите кнопку ниже и начните тест.\n\n⏱ 90 вопросов, 3 часа.",
    },
    "btn_start_online_test": {"uz": "🌐 Testni boshlash", "ru": "🌐 Начать тест"},
    "welcome_back_offline": {
        "uz": "👋 Xush kelibsiz! Pastdagi tugmalardan foydalaning.",
        "ru": "👋 Добро пожаловать! Используйте кнопки ниже.",
    },
    "welcome_back_online": {
        "uz": "👋 Xush kelibsiz! Online testni boshlash uchun quyidagi tugmani bosing.",
        "ru": "👋 Добро пожаловать! Нажмите кнопку ниже, чтобы начать online тест.",
    },
    "edit_exam_lang": {"uz": "Imtihon tilini qayta tanlang:", "ru": "Выберите язык экзамена снова:"},
    "selected_exam_lang": {"uz": "✅ Tanlandi:", "ru": "✅ Выбрано:"},

    "btn_cancel": {"uz": "❌ Bekor qilish", "ru": "❌ Отмена"},
    "btn_back": {"uz": "⬅️ Orqaga", "ru": "⬅️ Назад"},
}

CONF_LABELS = {
    "phone": {"uz": "📞 Telefon", "ru": "📞 Телефон"},
    "fio": {"uz": "👤 FIO", "ru": "👤 ФИО"},
    "gender": {"uz": "👥 Jinsi", "ru": "👥 Пол"},
    "region": {"uz": "🌍 Viloyat", "ru": "🌍 Регион"},
    "district": {"uz": "🏙 Tuman", "ru": "🏙 Район"},
    "school": {"uz": "🏫 Maktab", "ru": "🏫 Школа"},
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

    if isinstance(detail, str) and detail in mapping:
        return mapping[detail]["uz"] if ui_lang == "uz" else mapping[detail]["ru"]

    if isinstance(detail, dict):
        types = detail.get("test_types") or []
        if isinstance(types, list) and set(types) >= {"offline", "online"}:
            return (
                "🚫 Siz offline va online testlarning ikkalasiga ham allaqachon ro‘yxatdan o‘tib bo‘lgansiz.\n"
                "🔁 /start bosib davom eting."
                if ui_lang == "uz"
                else
                "🚫 Вы уже зарегистрированы и на офлайн, и на онлайн тест.\n"
                "🔁 Нажмите /start чтобы продолжить."
            )
        if isinstance(types, list) and types:
            done = ", ".join(types)
            return (
                f"🚫 Siz {done} test(lar)ga allaqachon ro‘yxatdan o‘tgansiz.\n"
                f"🔁 /start bosib boshqa testni tanlang."
                if ui_lang == "uz"
                else
                f"🚫 Вы уже зарегистрированы на {done} тест(ы).\n"
                f"🔁 Нажмите /start и выберите другой тест."
            )
        msg = detail.get("message") or detail.get("error") or detail.get("detail")
        if isinstance(msg, str) and msg:
            return (f"❌ Ошибка: {msg}" if ui_lang == "ru" else f"❌ Xatolik: {msg}")

    detail_str = detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)
    return (f"❌ Ошибка: {detail_str}" if ui_lang == "ru" else f"❌ Xatolik: {detail_str}")


def is_register_duplicate_error(error_text: str) -> bool:
    return _categorize_register_error(error_text) == "User already exists"


def should_treat_register_as_success(user_id: int, error_text: str) -> bool:
    if not user_id or not is_register_duplicate_error(error_text):
        return False

    try:
        return bool(check_user_exists(user_id))
    except Exception as e:
        logger.error(f"REGISTER SUCCESS CHECK ERROR => {repr(e)}")
        return False


async def mark_register_job_success(
    job_id: str,
    *,
    result: Optional[Dict[str, Any]] = None,
    note: str = "",
    original_error: str = "",
) -> Dict[str, Any]:
    REGISTER_JOBS[job_id] = REGISTER_JOBS.get(job_id, {}) or {}
    success_result = dict(result or {})
    success_result.setdefault("ok", True)
    success_result.setdefault("status", 200)

    REGISTER_JOBS[job_id].update({
        "status": "success",
        "result": success_result,
        "updated_at": now_str(),
    })
    REGISTER_JOBS[job_id].pop("error", None)

    if note:
        REGISTER_JOBS[job_id]["note"] = note
    if original_error:
        REGISTER_JOBS[job_id]["original_error"] = str(original_error)

    await persist_job_update(job_id)
    return REGISTER_JOBS[job_id]

# ----------------------------
# Bot message cleanup helpers
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
# API calls (regions/districts/schools)
# ----------------------------
async def _api_get(url: str, params: Dict[str, str]) -> Dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=60)
    logger.info(f"API REQUEST -> {url} params={params}")

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as r:
                logger.info(f"API RESPONSE STATUS -> {r.status}")
                text = await r.text()

                if r.status >= 400:
                    logger.error(f"API ERROR -> {text[:500]}")
                    return {"ok": False, "status": r.status, "text": text}

                try:
                    data = await r.json()
                    logger.info("API JSON parsed successfully")
                    return data
                except Exception:
                    logger.error("API JSON parse error")
                    return {"ok": False, "status": r.status, "text": text}

    except asyncio.TimeoutError:
        logger.error(f"API TIMEOUT -> {url}")
        return {"ok": False, "status": 504, "text": "TimeoutError"}

    except aiohttp.ClientError as e:
        logger.error(f"NETWORK ERROR -> {repr(e)}")
        return {"ok": False, "status": 503, "text": str(e)}

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
# JOBS JSON persistence helpers
# ----------------------------
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default

async def save_jobs_to_json() -> None:
    async with JOBS_FILE_LOCK:
        payload = {
            "saved_at": now_str(),
            "jobs": REGISTER_JOBS,
            "user_last_job": {str(k): v for k, v in USER_LAST_JOB.items()},
        }
        tmp = JOBS_PATH + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, JOBS_PATH)
        except Exception as e:
            logger.error(f"[JOBS] save error: {repr(e)}")
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass

async def load_jobs_from_json() -> None:
    global REGISTER_JOBS, USER_LAST_JOB

    async with JOBS_FILE_LOCK:
        if not os.path.exists(JOBS_PATH):
            REGISTER_JOBS = {}
            USER_LAST_JOB = {}
            return
        try:
            with open(JOBS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception as e:
            logger.error(f"[JOBS] load error: {repr(e)}")
            REGISTER_JOBS = {}
            USER_LAST_JOB = {}
            return

    jobs = data.get("jobs") or {}
    last = data.get("user_last_job") or {}

    REGISTER_JOBS = jobs if isinstance(jobs, dict) else {}
    USER_LAST_JOB = { _safe_int(k): str(v) for k, v in last.items() } if isinstance(last, dict) else {}

    # restart bo'lganda queued/processing -> queued
    for job_id, info in list(REGISTER_JOBS.items()):
        if not isinstance(info, dict):
            continue
        st = info.get("status")
        if st in ("queued", "processing"):
            info["status"] = "queued"
            info["updated_at"] = now_str()
            info["note"] = "requeued_after_restart"

    await save_jobs_to_json()

async def persist_job_update(job_id: str) -> None:
    # hozircha har update'da save (ishonchli)
    await save_jobs_to_json()

async def requeue_pending_jobs() -> int:
    n = 0
    for job_id, info in list(REGISTER_JOBS.items()):
        if not isinstance(info, dict):
            continue
        if info.get("status") != "queued":
            continue
        payload = info.get("payload")
        if not isinstance(payload, dict):
            info["status"] = "failed"
            info["error"] = "payload_missing"
            info["updated_at"] = now_str()
            await persist_job_update(job_id)
            continue

        try:
            REGISTER_QUEUE.put_nowait(RegisterJob(
                job_id=job_id,
                user_id=_safe_int(info.get("user_id")),
                chat_id=_safe_int(info.get("chat_id")),
                ui_lang=info.get("ui_lang") or "uz",
                payload=payload,
            ))
            n += 1
        except asyncio.QueueFull:
            break

    if n:
        logger.info(f"[JOBS] requeued {n} jobs from JSON")
    return n


def should_retry_register_with_status_false(err_text: str) -> bool:
    err = str(err_text or "").lower()
    if not err:
        return False

    retry_markers = (
        "pdf generation failed",
        "after-page images",
        "after page images",
        "topilmadi",
        "timeout",
        "timed out",
        "gateway timeout",
        "read timed out",
        "504",
        "503",
        "service unavailable",
        "clienterror",
    )
    return any(marker in err for marker in retry_markers)


def can_retry_failed_job(info: Dict[str, Any]) -> bool:
    if not isinstance(info, dict):
        return False
    return int(info.get("auto_retry_count") or 0) < FAILED_RETRY_MAX_COUNT


async def retry_register_with_status_false(payload: Dict[str, Any], err_text: str = "") -> Dict[str, Any]:
    retry_payload = dict(payload or {})
    if should_retry_register_with_status_false(err_text):
        retry_payload["status"] = False
    return await register_user(
        **retry_payload,
        retries=REGISTER_RETRY_ATTEMPTS,
        timeout_total=REGISTER_RETRY_TIMEOUT_SEC,
        timeout_connect=REGISTER_RETRY_CONNECT_SEC,
    )


async def requeue_failed_status_false_jobs(limit: int = 25) -> List[Dict[str, Any]]:
    requeued = 0
    retried_items: List[Dict[str, Any]] = []

    for job_id, info in list(REGISTER_JOBS.items()):
        if requeued >= limit:
            break
        if not isinstance(info, dict):
            continue
        if str(info.get("status") or "").lower() != "failed":
            continue

        err_txt = str(info.get("error") or info.get("original_error") or "")
        if not should_retry_register_with_status_false(err_txt):
            continue
        if not can_retry_failed_job(info):
            continue

        payload = info.get("payload")
        if not isinstance(payload, dict):
            continue

        retry_payload = dict(payload)
        if should_retry_register_with_status_false(err_txt):
            retry_payload["status"] = False

        try:
            REGISTER_QUEUE.put_nowait(
                RegisterJob(
                    job_id=job_id,
                    user_id=_safe_int(info.get("user_id")),
                    chat_id=_safe_int(info.get("chat_id")),
                    ui_lang=info.get("ui_lang") or "uz",
                    payload=retry_payload,
                )
            )
        except asyncio.QueueFull:
            logger.warning("[QUEUE] failed-retry sweep stopped: queue full")
            break

        info.update({
            "status": "queued",
            "payload": retry_payload,
            "updated_at": now_str(),
            "note": "requeued_failed_with_long_timeout_and_status_false",
            "auto_retry_count": int(info.get("auto_retry_count") or 0) + 1,
            "retry_with_status_false": True,
        })
        await persist_job_update(job_id)
        retried_items.append({
            "job_id": job_id,
            "updated_at": str(info.get("updated_at") or "-"),
            "user_id": _safe_int(info.get("user_id")) or "-",
            "reason": _categorize_register_error(err_txt),
            "retry_count": int(info.get("auto_retry_count") or 0),
        })
        requeued += 1

    if requeued:
        logger.info(f"[QUEUE] requeued {requeued} failed jobs with extended retry strategy")
    return retried_items


def build_failed_retry_requeue_text(items: List[Dict[str, Any]]) -> str:
    visible_items = items[:10]
    msg = (
        "🔁 <b>Eski texnik failedlar topildi</b>\n"
        "🛠 <b>Qayta generatsiyaga yuboryapman</b>\n"
        f"🕒 <b>Vaqt:</b> {now_str()}\n"
        f"📦 <b>Jami topildi:</b> <code>{len(items)}</code>\n"
        "⚙️ <b>Rejim:</b> <code>long timeout + status=False</code>\n\n"
        "🧾 <b>Qayta yuborilgan joblar:</b>\n"
    )

    for item in visible_items:
        msg += (
            f"• <code>{html.escape(str(item['updated_at']))}</code> | "
            f"<code>{html.escape(str(item['user_id']))}</code> | "
            f"{html.escape(str(item['reason']))} | "
            f"retry <code>#{html.escape(str(item['retry_count']))}</code>\n"
        )

    if len(items) > len(visible_items):
        msg += f"• ... yana <code>{len(items) - len(visible_items)}</code> ta job\n"

    return msg.rstrip()

# ----------------------------
# Queue workers
# ----------------------------
async def _register_worker(worker_idx: int, bot):
    logger.info(f"[QUEUE] worker#{worker_idx} started")
    while True:
        job: RegisterJob = await REGISTER_QUEUE.get()
        try:
            # processing
            REGISTER_JOBS[job.job_id] = REGISTER_JOBS.get(job.job_id, {}) or {}
            REGISTER_JOBS[job.job_id].update({
                "status": "processing",
                "updated_at": now_str(),
                "user_id": job.user_id,
                "chat_id": job.chat_id,
                "ui_lang": job.ui_lang,
                "payload": job.payload,
                "attempts": int(REGISTER_JOBS[job.job_id].get("attempts") or 0) + 1,
            })
            await persist_job_update(job.job_id)

            logger.info(f"[QUEUE] worker#{worker_idx} processing job_id={job.job_id} user_id={job.user_id}")

            res = await register_user(**job.payload)

            if isinstance(res, dict) and res.get("ok") is True:
                await mark_register_job_success(job.job_id, result=res)
                logger.info(f"[QUEUE] job success job_id={job.job_id}")
            else:
                err_txt = res.get("text") if isinstance(res, dict) else str(res)
                if should_treat_register_as_success(job.user_id, err_txt):
                    await mark_register_job_success(
                        job.job_id,
                        result={"ok": True, "status": 200},
                        note="success_after_existing_user_check",
                        original_error=str(err_txt),
                    )
                    logger.info(
                        f"[QUEUE] job normalized to success from existing-user check job_id={job.job_id}"
                    )
                elif should_retry_register_with_status_false(err_txt) and can_retry_failed_job(REGISTER_JOBS.get(job.job_id, {})):
                    logger.warning(
                        f"[QUEUE] retry with extended timeout job_id={job.job_id} err={str(err_txt)[:200]}"
                    )
                    retry_res = await retry_register_with_status_false(job.payload, err_txt)

                    if isinstance(retry_res, dict) and retry_res.get("ok") is True:
                        await mark_register_job_success(
                            job.job_id,
                            result=retry_res,
                            note="success_after_extended_timeout_retry",
                            original_error=str(err_txt),
                        )
                        REGISTER_JOBS[job.job_id]["retry_with_status_false"] = True
                        REGISTER_JOBS[job.job_id]["auto_retry_count"] = int(REGISTER_JOBS[job.job_id].get("auto_retry_count") or 0) + 1
                        await persist_job_update(job.job_id)
                        logger.info(
                            f"[QUEUE] job success after extended timeout retry job_id={job.job_id}"
                        )
                    elif should_treat_register_as_success(job.user_id, retry_res.get("text") if isinstance(retry_res, dict) else str(retry_res)):
                        retry_err_txt = retry_res.get("text") if isinstance(retry_res, dict) else str(retry_res)
                        await mark_register_job_success(
                            job.job_id,
                            result={"ok": True, "status": 200},
                            note="success_after_extended_timeout_existing_user_check",
                            original_error=str(retry_err_txt),
                        )
                        REGISTER_JOBS[job.job_id]["retry_with_status_false"] = True
                        REGISTER_JOBS[job.job_id]["auto_retry_count"] = int(REGISTER_JOBS[job.job_id].get("auto_retry_count") or 0) + 1
                        await persist_job_update(job.job_id)
                        logger.info(
                            f"[QUEUE] job normalized to success after extended timeout retry existing-user check job_id={job.job_id}"
                        )
                    else:
                        retry_err_txt = retry_res.get("text") if isinstance(retry_res, dict) else str(retry_res)
                        REGISTER_JOBS[job.job_id].update({
                            "status": "failed",
                            "error": str(retry_err_txt),
                            "updated_at": now_str(),
                            "note": "extended_timeout_retry_failed",
                            "retry_with_status_false": True,
                            "auto_retry_count": int(REGISTER_JOBS[job.job_id].get("auto_retry_count") or 0) + 1,
                            "original_error": str(err_txt),
                        })
                        await persist_job_update(job.job_id)
                        logger.error(
                            f"[QUEUE] extended timeout retry failed job_id={job.job_id} err={str(retry_err_txt)[:200]}"
                        )
                else:
                    REGISTER_JOBS[job.job_id].update({
                        "status": "failed",
                        "error": str(err_txt),
                        "updated_at": now_str(),
                    })
                    await persist_job_update(job.job_id)
                    logger.error(f"[QUEUE] job failed job_id={job.job_id} err={str(err_txt)[:200]}")

        except Exception as e:
            REGISTER_JOBS[job.job_id] = REGISTER_JOBS.get(job.job_id, {}) or {}
            REGISTER_JOBS[job.job_id].update({
                "status": "failed",
                "error": str(e),
                "updated_at": now_str(),
                "user_id": job.user_id,
                "chat_id": job.chat_id,
                "ui_lang": job.ui_lang,
                "payload": job.payload,
            })
            await persist_job_update(job.job_id)
            logger.exception(f"[QUEUE] worker exception job_id={job.job_id}")
        finally:
            REGISTER_QUEUE.task_done()

async def ensure_register_workers(bot, workers: int = 2):
    global REGISTER_WORKERS_STARTED
    if REGISTER_WORKERS_STARTED:
        return

    REGISTER_WORKERS_STARTED = True

    await load_jobs_from_json()

    for i in range(max(1, workers)):
        REGISTER_WORKERS.append(asyncio.create_task(_register_worker(i + 1, bot)))

    logger.info(f"[QUEUE] started {len(REGISTER_WORKERS)} workers")

    await requeue_pending_jobs()


def get_register_queue_stats() -> Dict[str, int]:
    queued = 0
    processing = 0
    success = 0
    failed = 0
    retried_total = 0
    retried_success = 0
    retried_pending = 0
    retried_failed = 0
    pending_users: Set[int] = set()

    for info in REGISTER_JOBS.values():
        if not isinstance(info, dict):
            continue
        status = str(info.get("status") or "").strip().lower()
        user_id = _safe_int(info.get("user_id"))
        was_retried = bool(info.get("retry_with_status_false")) or int(info.get("auto_retry_count") or 0) > 0

        if status == "queued":
            queued += 1
            if user_id:
                pending_users.add(user_id)
        elif status == "processing":
            processing += 1
            if user_id:
                pending_users.add(user_id)
        elif status == "success":
            success += 1
        elif status == "failed":
            failed += 1

        if was_retried:
            retried_total += 1
            if status in ("queued", "processing"):
                retried_pending += 1
            elif status == "success":
                retried_success += 1
            elif status == "failed":
                retried_failed += 1

    alive_workers = sum(1 for t in REGISTER_WORKERS if not t.done())
    total_workers = len(REGISTER_WORKERS)

    return {
        "queued": queued,
        "processing": processing,
        "success": success,
        "failed": failed,
        "pending_total": queued + processing,
        "pending_users": len(pending_users),
        "queue_size": REGISTER_QUEUE.qsize(),
        "alive_workers": alive_workers,
        "total_workers": total_workers,
        "total_jobs": len(REGISTER_JOBS),
        "retried_total": retried_total,
        "retried_success": retried_success,
        "retried_pending": retried_pending,
        "retried_failed": retried_failed,
    }


def _parse_job_updated_at(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _categorize_register_error(error_text: str) -> str:
    err = str(error_text or "").strip()
    err_l = err.lower()

    if not err:
        return "Noma'lum xatolik"
    if "timeout" in err_l:
        return "Timeout / javob kechikdi"
    if "user already exists" in err_l:
        return "User already exists"
    if "invalid phone" in err_l:
        return "Telefon noto'g'ri"
    if "diskfull" in err_l or "no space left on device" in err_l:
        return "Server disk to'lgan"
    if "queue_full" in err_l:
        return "Queue to'lib qolgan"
    if "payload_missing" in err_l:
        return "Payload topilmadi"
    if "clienterror" in err_l:
        return "Network client error"
    if "503" in err_l:
        return "Service unavailable"
    if "504" in err_l:
        return "Gateway timeout"
    if "500" in err_l:
        return "Server 500 xatolik"
    if "psycopg2" in err_l or "sqlalchemy" in err_l or "database" in err_l:
        return "Database xatoligi"

    first_line = err.splitlines()[0].strip()
    return first_line[:70] + ("..." if len(first_line) > 70 else "")


def _classify_register_error_bucket(reason: str) -> str:
    normalized_reason = str(reason or "").strip().lower()

    if normalized_reason == "user already exists":
        return "duplicate"
    if normalized_reason == "telefon noto'g'ri":
        return "validation"
    return "technical"


def get_register_failed_insights(limit: int = 10) -> Dict[str, Any]:
    today = datetime.now().date()
    technical_reasons: Dict[str, int] = {}
    technical_failed: List[Dict[str, Any]] = []
    technical_failed_total = 0
    today_technical_failed = 0
    duplicate_failed_total = 0
    today_duplicate_failed = 0
    duplicate_users_today: Set[int] = set()
    validation_failed_total = 0
    today_validation_failed = 0

    for job_id, info in REGISTER_JOBS.items():
        if not isinstance(info, dict) or str(info.get("status") or "").lower() != "failed":
            continue

        updated_at = str(info.get("updated_at") or "-")
        dt = _parse_job_updated_at(updated_at)
        is_today = bool(dt and dt.date() == today)
        user_id = _safe_int(info.get("user_id")) or "-"
        reason = _categorize_register_error(info.get("error"))
        bucket = _classify_register_error_bucket(reason)

        if bucket == "duplicate":
            duplicate_failed_total += 1
            if is_today:
                today_duplicate_failed += 1
                if isinstance(user_id, int):
                    duplicate_users_today.add(user_id)
            continue

        if bucket == "validation":
            validation_failed_total += 1
            if is_today:
                today_validation_failed += 1
            continue

        technical_failed_total += 1
        if is_today:
            today_technical_failed += 1

        technical_reasons[reason] = technical_reasons.get(reason, 0) + 1
        technical_failed.append({
            "job_id": job_id,
            "updated_at": updated_at,
            "updated_at_dt": dt,
            "user_id": user_id,
            "reason": reason,
        })

    technical_failed.sort(
        key=lambda item: (
            item["updated_at_dt"] or datetime.min,
            str(item["updated_at"]),
        ),
        reverse=True,
    )

    recent_failed: List[Dict[str, Any]] = []
    recent_seen: Set[Any] = set()
    for item in technical_failed:
        dedupe_key = (item["user_id"], item["reason"])
        if dedupe_key in recent_seen:
            continue
        recent_seen.add(dedupe_key)
        recent_failed.append(item)
        if len(recent_failed) >= max(1, limit):
            break

    top_reasons_sorted = sorted(
        technical_reasons.items(),
        key=lambda item: (-item[1], item[0]),
    )[:3]

    return {
        "technical_failed_total": technical_failed_total,
        "today_technical_failed": today_technical_failed,
        "duplicate_failed_total": duplicate_failed_total,
        "today_duplicate_failed": today_duplicate_failed,
        "duplicate_users_today": len(duplicate_users_today),
        "validation_failed_total": validation_failed_total,
        "today_validation_failed": today_validation_failed,
        "top_technical_reasons": top_reasons_sorted,
        "recent_technical_failed": recent_failed,
    }


def build_register_queue_stats_text() -> str:
    stats = get_register_queue_stats()
    failed_insights = get_register_failed_insights(limit=5)

    msg = (
        "📊 <b>Register Queue Statistikasi</b>\n"
        f"🕒 <b>Vaqt:</b> {now_str()}\n\n"
        f"⏳ <b>Navbatda:</b> <code>{stats['queued']}</code>\n"
        f"⚙️ <b>Ishlanmoqda:</b> <code>{stats['processing']}</code>\n"
        f"👥 <b>Qolgan foydalanuvchi:</b> <code>{stats['pending_users']}</code>\n"
        f"📦 <b>Queue size:</b> <code>{stats['queue_size']}</code>\n"
        f"🧵 <b>Workerlar:</b> <code>{stats['alive_workers']}/{stats['total_workers']}</code>\n\n"
        f"✅ <b>Success:</b> <code>{stats['success']}</code>\n"
        f"❌ <b>Failed (jami):</b> <code>{stats['failed']}</code>\n"
        f"🗂 <b>Jami joblar:</b> <code>{stats['total_jobs']}</code>"
    )

    if stats["retried_total"] > 0:
        msg += (
            "\n\n🔁 <b>Qayta generatsiya statistikasi:</b>\n"
            f"• <b>Jami retry:</b> <code>{stats['retried_total']}</code>\n"
            f"• <b>Retry success:</b> <code>{stats['retried_success']}</code>\n"
            f"• <b>Retry navbatda:</b> <code>{stats['retried_pending']}</code>\n"
            f"• <b>Retry failed:</b> <code>{stats['retried_failed']}</code>"
        )

    if stats["failed"] > 0:
        msg += (
            "\n\n🧠 <b>Failed tahlili:</b>\n"
            f"• <b>Texnik failed:</b> <code>{failed_insights['technical_failed_total']}</code>\n"
            f"• <b>Bugun texnik failed:</b> <code>{failed_insights['today_technical_failed']}</code>"
        )

        if failed_insights["duplicate_failed_total"] > 0:
            msg += (
                "\n"
                f"• <b>Duplicate urinishlar:</b> <code>{failed_insights['duplicate_failed_total']}</code>\n"
                f"• <b>Bugun duplicate:</b> <code>{failed_insights['today_duplicate_failed']}</code>"
            )
            if failed_insights["duplicate_users_today"] > 0:
                msg += (
                    f" | <b>Unique user:</b> "
                    f"<code>{failed_insights['duplicate_users_today']}</code>"
                )

        if failed_insights["validation_failed_total"] > 0:
            msg += (
                "\n"
                f"• <b>Validatsiya rad etildi:</b> <code>{failed_insights['validation_failed_total']}</code>\n"
                f"• <b>Bugun validatsiya failed:</b> <code>{failed_insights['today_validation_failed']}</code>"
            )

        if failed_insights["top_technical_reasons"]:
            msg += "\n\n🔝 <b>Top texnik sabablar:</b>\n"
            for reason, count in failed_insights["top_technical_reasons"]:
                msg += f"• {html.escape(str(reason))}: <code>{count}</code>\n"
            msg = msg.rstrip()
        elif failed_insights["technical_failed_total"] == 0:
            msg += "\n\nℹ️ <b>Hozircha texnik failed yo‘q.</b> Failedlar asosan duplicate yoki validatsiya sababli."

        if failed_insights["recent_technical_failed"]:
            msg += "\n\n🧾 <b>So‘nggi texnik failedlar:</b>\n"
            for item in failed_insights["recent_technical_failed"]:
                msg += (
                    f"• <code>{html.escape(str(item['updated_at']))}</code> | "
                    f"<code>{html.escape(str(item['user_id']))}</code> | "
                    f"{html.escape(str(item['reason']))}\n"
                )
            msg = msg.rstrip()

    return msg


async def _register_queue_stats_notifier(bot):
    logger.info(f"[QUEUE] stats notifier started interval={QUEUE_STATS_INTERVAL_SEC}s")

    while True:
        try:
            await asyncio.sleep(max(60, QUEUE_STATS_INTERVAL_SEC))
            await notify_admins(bot, build_register_queue_stats_text())
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[QUEUE] stats notifier error: {repr(e)}")


async def ensure_register_queue_stats_notifier(bot):
    global QUEUE_STATS_TASK

    if QUEUE_STATS_TASK and not QUEUE_STATS_TASK.done():
        return

    QUEUE_STATS_TASK = asyncio.create_task(_register_queue_stats_notifier(bot))


async def _failed_register_retry_sweeper(bot):
    logger.info(f"[QUEUE] failed retry sweeper started interval={FAILED_RETRY_SWEEP_INTERVAL_SEC}s")

    while True:
        try:
            retried_items = await requeue_failed_status_false_jobs()
            if retried_items:
                await notify_admins(bot, build_failed_retry_requeue_text(retried_items))
            await asyncio.sleep(max(60, FAILED_RETRY_SWEEP_INTERVAL_SEC))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"[QUEUE] failed retry sweeper error: {repr(e)}")


async def ensure_failed_register_retry_sweeper(bot):
    global FAILED_RETRY_SWEEP_TASK

    if FAILED_RETRY_SWEEP_TASK and not FAILED_RETRY_SWEEP_TASK.done():
        return

    FAILED_RETRY_SWEEP_TASK = asyncio.create_task(_failed_register_retry_sweeper(bot))


async def startup_register_services(bot, workers: int = 2):
    await ensure_register_workers(bot, workers=workers)
    await ensure_register_queue_stats_notifier(bot)
    await ensure_failed_register_retry_sweeper(bot)

# ----------------------------
# Keyboards
# ----------------------------
def ui_lang_kb(show_result_btn=False):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.row(
        InlineKeyboardButton("🇺🇿 O‘zbekcha", callback_data="ui:uz"),
        InlineKeyboardButton("🇷🇺 Русский", callback_data="ui:ru"),
    )
    kb.add(InlineKeyboardButton("❌ Cancel", callback_data="reg_cancel"))
    return kb


def certificate_download_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🎓 Sertifikatni yuklab olish", url=CERTIFICATE_DOWNLOAD_URL))
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

def register_status_kb(ui_lang: str, job_id: str):
    kb = InlineKeyboardMarkup(row_width=2)
    check_txt = "🔄 Tekshirish" if ui_lang == "uz" else "🔄 Проверить"
    cancel_txt = tr(ui_lang, "btn_cancel")
    kb.row(
        InlineKeyboardButton(check_txt, callback_data=f"reg_job_check:{job_id}"),
        InlineKeyboardButton(cancel_txt, callback_data="reg_cancel"),
    )
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
# Helpers (phone/subjects/etc.)
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
        f"🏷 <b>Class letter:</b> <code>{data.get('class_letter') or data.get('group_name') or '-'}</code>\n"
        f"🗣 <b>Exam lang:</b> <code>{data.get('exam_lang') or data.get('language') or '-'}</code>\n"
        f"🚻 <b>Gender:</b> <code>{data.get('gender','-')}</code>\n"
        f"📚 <b>Subjects:</b> <code>{data.get('first_subject_id','-')}</code> + <code>{data.get('second_subject_id','-')}</code>"
    )


def _register_identity_snapshot(data: dict) -> dict:
    return {
        "full_name": str(data.get("full_name") or data.get("fio") or "").strip(),
        "phone": str(data.get("phone") or "").strip(),
        "region": str(data.get("region") or "").strip(),
        "district": str(data.get("district") or "").strip(),
        "school_code": str(data.get("school_code") or "").strip(),
        "group_name": str(data.get("group_name") or data.get("class_letter") or "").strip(),
        "language": str(data.get("language") or data.get("exam_lang") or "").strip(),
        "gender": str(data.get("gender") or "").strip(),
        "first_subject_id": str(data.get("first_subject_id") or "").strip(),
        "second_subject_id": str(data.get("second_subject_id") or "").strip(),
    }


def _identity_diff_lines(old_data: dict, new_data: dict) -> List[str]:
    labels = {
        "full_name": "F.I.SH",
        "phone": "Telefon",
        "region": "Viloyat",
        "district": "Tuman",
        "school_code": "Maktab kodi",
        "group_name": "Sinf",
    }
    diffs: List[str] = []
    old_snapshot = _register_identity_snapshot(old_data)
    new_snapshot = _register_identity_snapshot(new_data)

    for key, label in labels.items():
        old_val = old_snapshot.get(key) or "-"
        new_val = new_snapshot.get(key) or "-"
        if old_val != new_val:
            diffs.append(f"• <b>{label}:</b> <code>{old_val}</code> → <code>{new_val}</code>")
    return diffs


def _find_previous_success_for_user(user_id: int, current_job_id: str) -> Optional[dict]:
    matches = []
    for job_id, info in REGISTER_JOBS.items():
        if job_id == current_job_id or not isinstance(info, dict):
            continue
        if info.get("status") != "success":
            continue
        if _safe_int(info.get("user_id")) != int(user_id):
            continue
        payload = info.get("payload")
        if not isinstance(payload, dict):
            continue
        matches.append((info.get("updated_at") or "", job_id, info))

    if not matches:
        return None

    matches.sort(key=lambda x: x[0], reverse=True)
    return matches[0][2]


async def notify_account_reuse_if_needed(bot, user: types.User, current_job_id: str, current_payload: dict):
    previous = _find_previous_success_for_user(user.id, current_job_id)
    if not previous:
        return

    previous_payload = previous.get("payload") or {}
    diff_lines = _identity_diff_lines(previous_payload, current_payload)
    if not diff_lines:
        return

    prev_time = previous.get("updated_at", "-")
    prev_job_id = next(
        (
            job_id for job_id, info in REGISTER_JOBS.items()
            if info is previous
        ),
        "-",
    )

    alert_text = (
        f"🚨 <b>ACCOUNT REUSE ALERT</b>\n"
        f"🕒 <b>Time:</b> {now_str()}\n"
        f"👤 <b>Telegram user:</b> {_tg_user_link(user)}\n"
        f"🆔 <b>Chat ID:</b> <code>{user.id}</code>\n\n"
        f"📌 <b>Oldingi muvaffaqiyatli register:</b>\n"
        f"🧩 <b>Job ID:</b> <code>{prev_job_id}</code>\n"
        f"🕒 <b>Vaqt:</b> <code>{prev_time}</code>\n"
        f"{build_register_details(previous_payload)}\n"
        f"📝 <b>Full name:</b> <code>{previous_payload.get('full_name','-')}</code>\n\n"
        f"📌 <b>Hozirgi register:</b>\n"
        f"🧩 <b>Job ID:</b> <code>{current_job_id}</code>\n"
        f"{build_register_details(current_payload)}\n"
        f"📝 <b>Full name:</b> <code>{current_payload.get('full_name','-')}</code>\n\n"
        f"⚠️ <b>Farqlar:</b>\n" + "\n".join(diff_lines)
    )
    await notify_admins(bot, alert_text)

def build_confirm_text(ui_lang: str, data: dict) -> str:
    exam_lang = data.get("exam_lang", "uz")
    gender = data.get("gender", "male")

    exam_lang_label = EXAM_LANG_LABELS.get(exam_lang, {}).get(ui_lang, exam_lang)
    gender_label = GENDER_LABELS.get(gender, {}).get(ui_lang, gender)

    first_label = data.get("first_subject_uz", "-") if ui_lang == "uz" else (data.get("first_subject_ru") or data.get("first_subject_uz") or "-")
    second_label = data.get("second_subject_uz", "-") if ui_lang == "uz" else (data.get("second_subject_ru") or data.get("second_subject_uz") or "-")

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
# Test type chooser
# ----------------------------
def test_type_kb(ui_lang: str = "uz") -> types.InlineKeyboardMarkup:
    from data.config import WEBAPP_URL
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(text=tr(ui_lang, "btn_offline_test"), callback_data="test_type_offline"),
        types.InlineKeyboardButton(text=tr(ui_lang, "btn_online_test"), web_app=types.WebAppInfo(url=WEBAPP_URL)),
    )
    return kb


async def show_test_type_menu(target, ui_lang: str = "uz"):
    """target — Message yoki CallbackQuery.message"""
    await target.answer(
        tr(ui_lang, "choose_test_type"),
        parse_mode="HTML",
        reply_markup=test_type_kb(ui_lang),
    )


def pre_register_test_type_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            text=f"{TEXTS['btn_offline_test']['uz']} / {TEXTS['btn_offline_test']['ru']}",
            callback_data="pre_choose_offline",
        ),
        types.InlineKeyboardButton(
            text=f"{TEXTS['btn_online_test']['uz']} / {TEXTS['btn_online_test']['ru']}",
            callback_data="pre_choose_online",
        ),
    )
    return kb


async def show_pre_register_test_type(message: types.Message, state: Optional[FSMContext] = None):
    text = f"{TEXTS['choose_test_type']['uz']} / {TEXTS['choose_test_type']['ru']}"
    if state is not None:
        await send_clean(
            message, state, text,
            parse_mode="HTML",
            reply_markup=pre_register_test_type_kb(),
        )
    else:
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=pre_register_test_type_kb(),
        )


def online_ready_kb(ui_lang: str = "uz") -> types.InlineKeyboardMarkup:
    from data.config import WEBAPP_URL
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            text=tr(ui_lang, "btn_start_online_test"),
            web_app=types.WebAppInfo(url=WEBAPP_URL),
        ),
    )
    return kb


async def _show_offline_menu(target_message: types.Message, user_id: int, ui_lang: str = "uz"):
    from data.config import ADMINS
    from keyboards.default.userKeyboard import adminKeyboard_user
    reply_markup = adminKeyboard_user if str(user_id) in ADMINS else keyboard_user
    await target_message.bot.send_message(
        target_message.chat.id,
        tr(ui_lang, "offline_menu_text"),
        parse_mode="HTML",
        reply_markup=reply_markup,
    )


async def _show_offline_greeting(target_message: types.Message, user_id: int, ui_lang: str = "uz"):
    from data.config import ADMINS
    from keyboards.default.userKeyboard import adminKeyboard_user
    reply_markup = adminKeyboard_user if str(user_id) in ADMINS else keyboard_user
    await target_message.bot.send_message(
        target_message.chat.id,
        tr(ui_lang, "welcome_back_offline"),
        reply_markup=reply_markup,
    )


async def _show_online_greeting(target_message: types.Message, user_id: int, ui_lang: str = "uz"):
    from data.config import ADMINS
    from keyboards.default.userKeyboard import adminKeyboard_user
    reply_markup = adminKeyboard_user if str(user_id) in ADMINS else keyboard_user
    await target_message.bot.send_message(
        target_message.chat.id,
        tr(ui_lang, "welcome_back_online"),
        reply_markup=reply_markup,
    )
    await target_message.bot.send_message(
        target_message.chat.id,
        tr(ui_lang, "btn_start_online_test"),
        reply_markup=online_ready_kb(ui_lang),
    )


async def _show_online_ready(target_message: types.Message, user_id: int, ui_lang: str = "uz"):
    from data.config import ADMINS
    from keyboards.default.userKeyboard import adminKeyboard_user
    reply_markup = adminKeyboard_user if str(user_id) in ADMINS else keyboard_user
    await target_message.bot.send_message(
        target_message.chat.id,
        tr(ui_lang, "online_ready"),
        parse_mode="HTML",
        reply_markup=reply_markup,
    )
    await target_message.bot.send_message(
        target_message.chat.id,
        tr(ui_lang, "btn_start_online_test"),
        reply_markup=online_ready_kb(ui_lang),
    )


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
    # Avval oldingi flow ning bot xabarlarini o'chiramiz, keyin state ni reset qilamiz
    await cleanup_bot_messages(message.bot, message.chat.id, state)
    await state.finish()

    # Queue workerlarni ishga tushiramiz (1 marta)
    await ensure_register_workers(message.bot, workers=2)

    # 1. Obunani tekshiramiz (vaqtincha o'chirilgan)
    # is_sub = await is_subscribed(message.from_user.id, message.bot)
    # if not is_sub:
    #     await message.answer(
    #         "Botdan foydalanish uchun rasmiy kanalimizga a'zo bo'ling! ✅",
    #         reply_markup=sub_kb()
    #     )
    #     return

    # 2. Har doim chooser ko'rsatamiz — bir userda ikkala flow ham bo'lishi mumkin,
    # callback (pre_choose_*) kerakli ish-harakatni qiladi (greet vs register).
    await show_pre_register_test_type(message, state)

@dp.callback_query_handler(lambda c: c.data == "test_type_offline", state="*")
async def test_type_offline_cb(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    from data.config import ADMINS
    from keyboards.default.userKeyboard import adminKeyboard_user

    reply_markup = adminKeyboard_user if str(call.from_user.id) in ADMINS else keyboard_user
    await call.bot.send_message(
        call.message.chat.id,
        tr(ui_lang, "offline_menu_text"),
        parse_mode="HTML",
        reply_markup=reply_markup,
    )


@dp.callback_query_handler(lambda c: c.data == "reregister", state="*")
async def reregister_cb(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await state.finish()
    await clear_user_intent(call.from_user.id)

    res = await get_dtm_result(call.from_user.id)
    show_btn = bool(extract_dtm_result_data(res))

    await send_clean(
        call.message, state,
        f"{TEXTS['choose_ui_lang']['uz']} / {TEXTS['choose_ui_lang']['ru']}",
        reply_markup=ui_lang_kb(show_result_btn=bool(show_btn)),
    )
    await Registration.ui_lang.set()


async def _start_registration_with_intent(call: types.CallbackQuery, state: FSMContext, intent: str):
    await call.answer()
    # Eski tracked xabarlarni o'chiramiz, so'ng FSM ni reset qilamiz
    await cleanup_bot_messages(call.bot, call.message.chat.id, state)
    await state.finish()

    try:
        await call.message.delete()
    except Exception:
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

    # Faqat DB bo'yicha tekshiruv: (chat_id, test_type) bor bo'lsa — registratsiyasiz
    # greeting; yo'q bo'lsa — to'liq registratsiya FSM.
    if check_user_exists_by_type(call.from_user.id, intent):
        await set_user_intent(call.from_user.id, intent)
        ui_lang = "uz"
        if intent == "online":
            await _show_online_greeting(call.message, call.from_user.id, ui_lang)
        else:
            await _show_offline_greeting(call.message, call.from_user.id, ui_lang)
        return

    # DB da yo'q — to'liq registratsiya FSM
    await state.update_data(test_intent=intent)
    res = await get_dtm_result(call.from_user.id)
    show_btn = bool(extract_dtm_result_data(res))
    await send_clean(
        call.message, state,
        f"{TEXTS['choose_ui_lang']['uz']} / {TEXTS['choose_ui_lang']['ru']}",
        reply_markup=ui_lang_kb(show_result_btn=bool(show_btn)),
    )
    await Registration.ui_lang.set()


@dp.callback_query_handler(lambda c: c.data == "pre_choose_offline", state="*")
async def pre_choose_offline_cb(call: types.CallbackQuery, state: FSMContext):
    await _start_registration_with_intent(call, state, "offline")


@dp.callback_query_handler(lambda c: c.data == "pre_choose_online", state="*")
async def pre_choose_online_cb(call: types.CallbackQuery, state: FSMContext):
    await _start_registration_with_intent(call, state, "online")


@dp.callback_query_handler(lambda c: c.data == "check_sub", state="*")
async def check_sub(call: types.CallbackQuery, state: FSMContext):
    ok = await is_subscribed(call.from_user.id, call.bot)
    if not ok:
        await call.answer("Hali obuna emassiz. Avval obuna bo‘ling ✅", show_alert=True)
        return

    await call.answer("✅ Obuna tasdiqlandi")

    # 1. Ro'yxatdan o'tganmi?
    if check_user_exists(call.from_user.id):
        data = await state.get_data()
        ui_lang = data.get("ui_lang", "uz")
        try:
            await call.message.delete()
        except Exception:
            pass
        intent = get_user_intent(call.from_user.id) or "offline"
        if intent == "online":
            await _show_online_greeting(call.message, call.from_user.id, ui_lang)
        else:
            await _show_offline_greeting(call.message, call.from_user.id, ui_lang)
        await state.finish()
        return

    # 2. Tilni tanlash
    res = await get_dtm_result(call.from_user.id)
    show_btn = bool(extract_dtm_result_data(res))

    await edit_clean(
        call, state,
        f"{TEXTS['choose_ui_lang']['uz']} / {TEXTS['choose_ui_lang']['ru']}",
        reply_markup=ui_lang_kb(show_result_btn=bool(show_btn))
    )
    await Registration.ui_lang.set()


@dp.callback_query_handler(lambda c: c.data == "show_my_result_callback", state="*")
async def show_my_result_callback(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await state.finish()
    # Call the message handler logic
    await show_my_result(call.message, state)

@dp.callback_query_handler(lambda c: c.data == "reg_cancel", state="*")
async def reg_cancel(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    await cleanup_bot_messages(call.bot, call.message.chat.id, state)
    await state.finish()

    txt = TEXTS["cancelled"].get(ui_lang, TEXTS["cancelled"]["uz"])
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

    raw = (message.text or "").strip()
    fio_norm = normalize_fio_to_surname_name(raw)
    if not fio_norm:
        return await send_clean(message, state, tr(ui_lang, "fio_invalid_2words"))

    await state.update_data(fio=fio_norm)

    await send_clean(message, state, tr(ui_lang, "ask_gender"), reply_markup=gender_kb(ui_lang))
    await Registration.gender.set()

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("gender:"), state=Registration.gender)
async def reg_gender_cb(call: types.CallbackQuery, state: FSMContext):
    logger.info(f"GENDER CLICK -> user_id={call.from_user.id} data={call.data}")

    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    gender = call.data.split(":", 1)[1]
    logger.info(f"USER GENDER SELECTED -> {gender}")

    await state.update_data(gender=gender)

    logger.info("FETCHING REGIONS FROM API")
    res = await fetch_regions()
    logger.info(f"FETCH_REGIONS RESULT -> {res}")

    if not (isinstance(res, dict) and res.get("ok")):
        logger.error("REGIONS FETCH FAILED")
        await edit_clean(call, state, pretty_register_error(str(res), ui_lang), reply_markup=None)
        return

    regions = res.get("regions") or []
    logger.info(f"REGIONS COUNT -> {len(regions)}")

    await edit_clean(call, state, tr(ui_lang, "region_ask"), reply_markup=regions_kb(ui_lang, regions))
    await Registration.region.set()

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

# ✅ Confirm callbacks
@dp.callback_query_handler(lambda c: c.data in ["reg_confirm", "reg_edit"], state=Registration.verify)
async def reg_verify(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    try:
        await call.answer()
    except Exception:
        pass

    # ========= EDIT =========
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

    # ========= CONFIRM (QUEUE + JSON) =========
    lock = USER_LOCKS[call.from_user.id]
    if lock.locked():
        try:
            await call.answer(
                "⏳ So‘rov navbatda, kuting..." if ui_lang == "uz" else "⏳ Заявка в очереди, подождите...",
                show_alert=False
            )
        except Exception:
            pass
        return

    async with lock:
        # stop double click
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

        # worker start (1 marta)
        await ensure_register_workers(call.bot, workers=2)

        job_id = uuid.uuid4().hex
        USER_LAST_JOB[call.from_user.id] = job_id

        payload = dict(
            bot_id=str(call.from_user.id),
            full_name=data.get("fio"),
            phone=data.get("phone"),
            school_code=data.get("school_code"),
            first_subject_id=data.get("first_subject_id"),
            second_subject_id=data.get("second_subject_id"),
            password="1111",
            language=data.get("exam_lang", "uz"),
            gender=data.get("gender", "male"),
            district=data.get("district"),
            region=data.get("region"),
            group_name=data.get("class_letter"),
            status=True,
            test_type=data.get("test_intent", "offline"),
        )

        # ---- ONLINE: to’g’ridan API, queue kerak emas ----
        if data.get("test_intent") == "online":
            wait_msg = await call.bot.send_message(
                call.message.chat.id,
                "⏳ Ro’yxatdan o’tilmoqda..." if ui_lang == "uz" else "⏳ Регистрация...",
            )
            res = await register_user(**payload)
            try:
                await wait_msg.delete()
            except Exception:
                pass

            if isinstance(res, dict) and res.get("ok") is True:
                info = {
                    "status": "done",
                    "updated_at": now_str(),
                    "user_id": call.from_user.id,
                    "chat_id": call.message.chat.id,
                    "ui_lang": ui_lang,
                    "payload": payload,
                }
                REGISTER_JOBS[job_id] = info
                await persist_job_update(job_id)
                await complete_register_success(call, state, ui_lang, job_id, info)
            else:
                err_txt = res.get("text") if isinstance(res, dict) else str(res)
                if should_treat_register_as_success(call.from_user.id, err_txt):
                    info = {
                        "status": "done",
                        "updated_at": now_str(),
                        "user_id": call.from_user.id,
                        "chat_id": call.message.chat.id,
                        "ui_lang": ui_lang,
                        "payload": payload,
                    }
                    REGISTER_JOBS[job_id] = info
                    await persist_job_update(job_id)
                    await complete_register_success(call, state, ui_lang, job_id, info)
                else:
                    err_msg = pretty_register_error(err_txt, ui_lang)
                    await call.bot.send_message(call.message.chat.id, err_msg)
            return

        # ---- OFFLINE: queue ----
        REGISTER_JOBS[job_id] = {
            "status": "queued",
            "updated_at": now_str(),
            "user_id": call.from_user.id,
            "chat_id": call.message.chat.id,
            "ui_lang": ui_lang,
            "payload": payload,
        }
        await persist_job_update(job_id)

        try:
            REGISTER_QUEUE.put_nowait(RegisterJob(
                job_id=job_id,
                user_id=call.from_user.id,
                chat_id=call.message.chat.id,
                ui_lang=ui_lang,
                payload=payload,
            ))
        except asyncio.QueueFull:
            REGISTER_JOBS[job_id]["status"] = "failed"
            REGISTER_JOBS[job_id]["error"] = "queue_full"
            REGISTER_JOBS[job_id]["updated_at"] = now_str()
            await persist_job_update(job_id)

            txt = "❌ Navbat to’lib ketdi. Keyinroq urinib ko’ring." if ui_lang == "uz" else "❌ Очередь переполнена. Попробуйте позже."
            await call.bot.send_message(call.message.chat.id, txt)
            return

        txt = (
            "✅ So’rov navbatga qo’yildi.\n"
            "⏳ Tizim band bo’lsa ham, navbat bilan ishlaydi.\n\n"
            f"🧩 Job ID: <code>{job_id}</code>\n"
            "🔄 Natijani tekshirish uchun ‘Tekshirish’ ni bosing."
            if ui_lang == "uz" else
            "✅ Заявка поставлена в очередь.\n"
            "⏳ Даже если сервер занят, обработаем по очереди.\n\n"
            f"🧩 Job ID: <code>{job_id}</code>\n"
            "🔄 Нажмите ‘Проверить’ чтобы узнать результат."
        )

        await call.bot.send_message(
            call.message.chat.id,
            txt,
            parse_mode="HTML",
            reply_markup=register_status_kb(ui_lang, job_id),
            disable_web_page_preview=True
        )

        await notify_admins(call.bot, (
            f"🧾 <b>REGISTER QUEUED (BOT)</b>\n"
            f"🕒 <b>Time:</b> {now_str()}\n"
            f"👤 <b>User:</b> {_tg_user_link(call.from_user)}\n"
            f"🆔 <b>Chat ID:</b> <code>{call.from_user.id}</code>\n"
            f"🧩 <b>Job ID:</b> <code>{job_id}</code>\n"
            f"📝 <b>Full name:</b> {data.get('fio','-')}\n\n"
            f"{build_register_details(data)}"
        ))

        # state.finish() qilmaymiz: user "Tekshirish" bilan natijani ko'radi
        return

async def complete_register_success(
    call: types.CallbackQuery,
    state: FSMContext,
    ui_lang: str,
    job_id: str,
    info: dict,
):
    data = await state.get_data()
    intent = data.get("test_intent")

    success_text = tr(ui_lang, "success")
    try:
        await call.message.edit_text(success_text, reply_markup=None)
    except Exception:
        await call.bot.send_message(call.message.chat.id, success_text)

    if intent == "online":
        await _show_online_ready(call.message, call.from_user.id, ui_lang)
        await set_user_intent(call.from_user.id, "online")
    else:
        await _show_offline_menu(call.message, call.from_user.id, ui_lang)
        await set_user_intent(call.from_user.id, "offline")

    await notify_admins(call.bot, (
        f"🧾 <b>REGISTER SUCCESS (BOT QUEUE)</b>\n"
        f"🕒 <b>Time:</b> {now_str()}\n"
        f"👤 <b>User:</b> {_tg_user_link(call.from_user)}\n"
        f"🆔 <b>Chat ID:</b> <code>{call.from_user.id}</code>\n"
        f"🧩 <b>Job ID:</b> <code>{job_id}</code>\n"
        f"📝 <b>Full name:</b> <code>{(info.get('payload') or {}).get('full_name','-')}</code>\n\n"
        f"{build_register_details(info.get('payload') or {})}"
    ))

    await notify_account_reuse_if_needed(
        call.bot,
        call.from_user,
        job_id,
        info.get("payload") or {},
    )

    await state.finish()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("reg_job_check:"), state="*")
async def reg_job_check(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    job_id = call.data.split(":", 1)[1].strip()
    info = REGISTER_JOBS.get(job_id)

    if not info:
        txt = "❌ Job topilmadi (bot qayta ishga tushgan bo‘lishi mumkin)." if ui_lang == "uz" else "❌ Job не найден (возможно бот перезапущен)."
        try:
            await call.message.edit_text(txt, reply_markup=None)
        except Exception:
            await call.bot.send_message(call.message.chat.id, txt)
        return

    st = info.get("status")
    if st in ("queued", "processing"):
        txt = (
            f"⏳ Holat: <b>{'Navbatda' if st=='queued' else 'Ishlanyapti'}</b>\n"
            f"🕒 Yangilangan: <code>{info.get('updated_at','-')}</code>\n\n"
            "🔄 Keyinroq yana tekshiring."
            if ui_lang == "uz" else
            f"⏳ Статус: <b>{'В очереди' if st=='queued' else 'Обрабатывается'}</b>\n"
            f"🕒 Обновлено: <code>{info.get('updated_at','-')}</code>\n\n"
            "🔄 Проверьте позже."
        )
        try:
            await call.message.edit_text(txt, parse_mode="HTML", reply_markup=register_status_kb(ui_lang, job_id))
        except Exception:
            await call.bot.send_message(call.message.chat.id, txt, parse_mode="HTML", reply_markup=register_status_kb(ui_lang, job_id))
        return

    if st == "success":
        await complete_register_success(call, state, ui_lang, job_id, info)
        return

    if st == "failed":
        err = info.get("error") or "Unknown error"
        if should_treat_register_as_success(call.from_user.id, err):
            info = await mark_register_job_success(
                job_id,
                result={"ok": True, "status": 200},
                note="success_on_manual_check_after_existing_user_check",
                original_error=str(err),
            )
            await complete_register_success(call, state, ui_lang, job_id, info)
            return

        user_err = pretty_register_error(str(err), ui_lang=ui_lang)
        try:
            await call.message.edit_text(user_err, reply_markup=None)
        except Exception:
            await call.bot.send_message(call.message.chat.id, user_err)

        await notify_admins(call.bot, (
            f"🧾 <b>REGISTER FAIL (BOT QUEUE)</b>\n"
            f"🕒 <b>Time:</b> {now_str()}\n"
            f"👤 <b>User:</b> {_tg_user_link(call.from_user)}\n"
            f"🆔 <b>Chat ID:</b> <code>{call.from_user.id}</code>\n"
            f"🧩 <b>Job ID:</b> <code>{job_id}</code>\n"
            f"❗ <b>Error:</b>\n<code>{str(err)[:1200]}</code>"
        ))
        return

    txt = "⏳ Holat tekshirilyapti, keyinroq urinib ko‘ring." if ui_lang == "uz" else "⏳ Статус проверяется, попробуйте позже."
    try:
        await call.message.edit_text(txt, reply_markup=register_status_kb(ui_lang, job_id))
    except Exception:
        await call.bot.send_message(call.message.chat.id, txt, reply_markup=register_status_kb(ui_lang, job_id))
# =========================
# Result Lookup by chat_id
# =========================
def dtm_result_has_score(data):
    try:
        if float(data.get("total_ball", 0) or 0) > 0:
            return True
    except (TypeError, ValueError):
        pass

    for subject in data.get("subjects") or []:
        try:
            if int(subject.get("correct", 0) or 0) > 0:
                return True
        except (TypeError, ValueError):
            pass

        try:
            if float(subject.get("score", 0) or 0) > 0:
                return True
        except (TypeError, ValueError):
            pass

    return False


def extract_dtm_result_data(res):
    if not isinstance(res, dict) or not res.get("ok"):
        return None

    data = res.get("data") if isinstance(res.get("data"), dict) else res
    if not isinstance(data, dict):
        return None

    if (data.get("document_code") or data.get("full_name") or data.get("subjects")) and dtm_result_has_score(data):
        return data
    return None


def format_dtm_result(data):
    full_name = data.get('full_name', 'Noma\'lum')
    document_code = data.get('document_code')
    total_ball = data.get('total_ball', 0)
    subjects = data.get('subjects', [])

    msg = f"👤 <b>F.I.SH:</b> {full_name}\n"
    if document_code:
        msg += f"🆔 <b>Document code:</b> {document_code}\n"
    msg += f"📊 <b>Umumiy ball:</b> {total_ball}\n\n"
    
    if subjects:
        msg += "📖 <b>Fanlar bo'yicha natijalar:</b>\n"
        for s in subjects:
            msg += f"🔹 <b>{s.get('name')}:</b>\n"
            msg += f"   ✅ To'g'ri: {s.get('correct')}/{s.get('allocated')}\n"
            msg += f"   📈 Ball: {s.get('score')} ({s.get('percent')}%)\n"
    
    return msg

@dp.message_handler(Command("natija"), state="*")
@dp.message_handler(Text(equals="📊 Mening natijam"), state="*")
async def show_my_result(message: types.Message, state: FSMContext):
    await state.finish()
    user_id = message.from_user.id
    
    msg = await message.answer("⏳ Natijangizni qidiryapman, biroz kuting...")
    
    try:
        # Get result from API
        res = await get_dtm_result(user_id)
        status = res.get("status") if isinstance(res, dict) else 0

        data = extract_dtm_result_data(res)
        if not data:
            if status == 401:
                err_text = (
                    "⚠️ Server konfiguratsiyasida xatolik (API key noto'g'ri).\n"
                    "Iltimos, administrator bilan bog'laning."
                )
            elif status == 404 or (status == 200 and isinstance(res, dict) and res.get("ok")):
                # 200 + ok=True, lekin score yo'q → backend yozuvni qabul qilgan, lekin
                # test hali baholanmagan
                err_text = "❌ Sizning natijangiz hali tayyor emas yoki kiritilmagan."
            else:
                err_text = (
                    "❌ Natijani olishda muammo yuz berdi.\n"
                    f"Status: <code>{status}</code>\n"
                    "Iltimos, biroz vaqtdan so'ng qayta urinib ko'ring."
                )
            await message.answer(err_text, parse_mode="HTML")
            try: await msg.delete()
            except: pass
            return

        formatted_text = format_dtm_result(data)

        if not formatted_text:
            await message.answer("❌ Sizning natijangiz hali tayyor emas yoki kiritilmagan.")
            try: await msg.delete()
            except: pass
            return

        file_url = data.get("file_url")
        if file_url and "127.0.0.1:8000" in file_url:
            file_url = file_url.replace("http://127.0.0.1:8000", "https://dtmpaperreaderapi.mentalaba.uz")

        kb = certificate_download_kb()

        # 1) Natija matnini darhol yuboramiz — PDF kutmaymiz
        await message.answer(
            f"<b>Test natijangiz tayyor.</b>\n\n{formatted_text}",
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=kb,
        )
        try: await msg.delete()
        except: pass

        # 2) PDFni alohida fonda yuboramiz (Telegram file_url'dan yuklab oladi)
        if file_url:
            pdf_progress = await message.answer("📄 PDF tayyorlanmoqda...")
            try:
                await message.answer_document(
                    document=file_url,
                    caption="📄 Sizning natijangiz PDF formatida",
                    parse_mode="HTML",
                )
                try: await pdf_progress.delete()
                except: pass
            except Exception as document_err:
                logger.error(f"Result document send error: {document_err}")
                fallback_kb = InlineKeyboardMarkup().add(
                    InlineKeyboardButton("📄 PDF Natijani yuklash", url=file_url)
                )
                try: await pdf_progress.delete()
                except: pass
                await message.answer(
                    "PDFni quyidagi tugma orqali yuklab olishingiz mumkin:",
                    reply_markup=fallback_kb,
                )
        
    except Exception as e:
        logger.error(f"Error in show_my_result: {e}")
        await message.answer("❌ Natijani yuklashda texnik xatolik yuz berdi.")
        try: await msg.delete()
        except: pass


@dp.message_handler(Command("sertifikat_qollanma"), state="*")
@dp.message_handler(Text(equals="🎥 Sertifikatni olish uchun video qo‘llanma"), state="*")
async def send_certificate_guide(message: types.Message, state: FSMContext):
    global CERTIFICATE_GUIDE_FILE_ID

    await state.finish()
    kb = certificate_download_kb()
    progress = await message.answer("⏳ Video qo‘llanma yuborilmoqda, biroz kuting...")

    try:
        if CERTIFICATE_GUIDE_FILE_ID:
            sent = await message.answer_video(
                CERTIFICATE_GUIDE_FILE_ID,
                caption=CERTIFICATE_GUIDE_CAPTION,
                parse_mode="HTML",
                reply_markup=kb,
                supports_streaming=True,
            )
        elif CERTIFICATE_GUIDE_VIDEO_PATH.exists():
            sent = await message.answer_video(
                types.InputFile(str(CERTIFICATE_GUIDE_VIDEO_PATH)),
                caption=CERTIFICATE_GUIDE_CAPTION,
                parse_mode="HTML",
                reply_markup=kb,
                supports_streaming=True,
            )
            if getattr(sent, "video", None) and sent.video.file_id:
                CERTIFICATE_GUIDE_FILE_ID = sent.video.file_id
        else:
            await message.answer(
                "❌ Video qo‘llanma fayli topilmadi. Administratorga murojaat qiling."
            )
            await message.answer(
                CERTIFICATE_GUIDE_CAPTION,
                parse_mode="HTML",
                reply_markup=kb,
                disable_web_page_preview=True,
            )
        try:
            await progress.delete()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Error in send_certificate_guide: {e}")
        await message.answer(
            "❌ Video qo‘llanmani yuborishda texnik xatolik yuz berdi.",
            reply_markup=kb,
        )
        try:
            await progress.delete()
        except Exception:
            pass
