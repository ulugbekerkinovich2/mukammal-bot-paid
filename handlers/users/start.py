import re
import os
import io
import json
import uuid
import html
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, List, Optional, Set, Tuple

import aiohttp
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text, Command
from aiogram.dispatcher.filters.builtin import CommandStart
from aiogram.types import (
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from loader import dp
from keyboards.default.userKeyboard import keyboard_user
from states.userStates import Registration, OnlineV2, MandatResult
from utils.mandat_result import fetch_mandat_result, format_mandat_result, is_valid_entrant_id
from utils.mandat_excel import lookup_cached_result, save_result_to_cache, excel_file_exists, EXCEL_PATH
from data.config import SUBJECTS_MAP
from keyboards.inline.user_inline import language_keyboard_button, gender_kb

from utils.send_req import (
    register_user,
    get_dtm_result,
    check_user_exists,
    check_user_exists_by_type,
    normalize_test_type,
    extract_test_type,
    create_offline_test_result,
    fetch_active_subscriptions,
    DEFAULT_TEST_TYPE,
    REGISTER_RETRY_TIMEOUT_SEC,
    REGISTER_RETRY_CONNECT_SEC,
    REGISTER_RETRY_ATTEMPTS,
)
from data.config import ADMIN_CHAT_ID, CHANNEL_LINK
from data.config import BASE_URL, SECRET_KEY, V2_FOR_ALL, V2_API_BASE

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

# v2 endpoint'lari uchun base. V2_API_BASE berilsa o'sha, aks holda API_V1.
V2_API_V1 = (V2_API_BASE or "").rstrip("/")
if V2_API_V1 and not V2_API_V1.endswith("/api/v1"):
    V2_API_V1 = V2_API_V1 + "/api/v1"
if not V2_API_V1:
    V2_API_V1 = API_V1

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

    "flow_choose": {
        "uz": "Nima qilmoqchisiz?",
        "ru": "Что хотите сделать?",
    },
    "btn_flow_test": {"uz": "🧪 Test ishlash", "ru": "🧪 Пройти тест"},
    "btn_flow_dtm_result": {"uz": "🎓 DTM natijasini bilish", "ru": "🎓 Узнать результат DTM"},

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
    "school_type_ask": {"uz": "Ta'lim muassasasi turini tanlang:", "ru": "Выберите тип учебного заведения:"},
    "school_pick_ask": {
        "uz": "Maktabni tanlang yoki nomini yozib yuboring:",
        "ru": "Выберите школу или введите название:",
    },

    "regions_not_found": {"uz": "Viloyatlar topilmadi.", "ru": "Регионы не найдены."},
    "districts_not_found": {"uz": "Tumanlar topilmadi.", "ru": "Районы не найдены."},
    "schools_not_found": {"uz": "Maktablar topilmadi.", "ru": "Школы не найдены."},
    "school_type_school":   {"uz": "🏫 Umumta'lim maktabi", "ru": "🏫 Общеобразовательная школа"},
    "school_type_litsey":   {"uz": "🎓 Akademik litsey",     "ru": "🎓 Академический лицей"},
    "school_type_texnikum": {"uz": "🔧 Kasb-hunar texnikumi","ru": "🔧 Профессиональный техникум"},
    "btn_school_search":    {"uz": "🔎 Nomi bo'yicha qidirish", "ru": "🔎 Поиск по названию"},
    "btn_school_inline_search": {
        "uz": "⚡️ Tezkor qidiruv (real-time)",
        "ru": "⚡️ Быстрый поиск (real-time)",
    },
    "btn_school_show_all":  {"uz": "📋 Barchasini ko'rsatish", "ru": "📋 Показать все"},
    "school_search_ask": {
        "uz": "🔎 Maktab nomini yoki kodini yozib yuboring (masalan: <code>IT-litsey</code> yoki <code>SHAY320</code>):",
        "ru": "🔎 Введите название или код школы (например: <code>IT-лицей</code> или <code>SHAY320</code>):",
    },
    "school_search_too_short": {
        "uz": "❗ Kamida 2 ta belgi yozing.",
        "ru": "❗ Введите минимум 2 символа.",
    },
    "school_search_no_match": {
        "uz": "🔍 Sizning so'rovingiz bo'yicha hech narsa topilmadi. Boshqacha yozib ko'ring yoki barchasini ochib ko'ring.",
        "ru": "🔍 По вашему запросу ничего не найдено. Попробуйте ещё раз или откройте полный список.",
    },
    "school_search_results": {
        "uz": "🔎 Qidiruv natijalari:",
        "ru": "🔎 Результаты поиска:",
    },
    "school_type_label": {
        "school":   {"uz": "Maktab",   "ru": "Школа"},
        "litsey":   {"uz": "Litsey",   "ru": "Лицей"},
        "texnikum": {"uz": "Texnikum", "ru": "Техникум"},
    },

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
        "uz": "🌐 <b>Online test</b>\n\nRo'yxatdan muvaffaqiyatli o'tdingiz. Quyidagi tugmani bosing va testni boshlang.",
        "ru": "🌐 <b>Online тест</b>\n\nВы успешно зарегистрированы. Нажмите кнопку ниже и начните тест.",
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
    "school_type": {"uz": "🎓 Ta'lim turi", "ru": "🎓 Тип учреждения"},
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

V2_TEXTS = {
    "subjects_choose":        {"uz": "Fan kombinatsiyangizni tanlang:",              "ru": "Выберите комбинацию предметов:"},
    "subjects_choose_first":  {"uz": "Birinchi (majburiy) faningizni tanlang:",       "ru": "Выберите первый предмет:"},
    "subjects_choose_second": {"uz": "Ikkinchi (tanlov) faningizni tanlang:",          "ru": "Выберите второй предмет:"},
    "subject_not_found":      {"uz": "Fan topilmadi",                                  "ru": "Предмет не найден"},
    "pair_not_found":         {"uz": "Kombinatsiya topilmadi",                         "ru": "Комбинация не найдена"},
    "first_subject_selected": {"uz": "✅ 1-fan: <b>{}</b>\n\nIkkinchi (tanlov) faningizni tanlang:", "ru": "✅ 1-й предмет: <b>{}</b>\n\nВыберите второй предмет:"},
    "test_submitted":         {"uz": "✅ Test topshirildi!\n\nNatijangizni ko'rish uchun ma'lumotlaringizni kiriting.", "ru": "✅ Тест сдан!\n\nВведите данные для просмотра результата."},
    "enter_phone_btn":        {"uz": "📞 Raqamni yuborish",                            "ru": "📞 Отправить номер"},
    "enter_fio":              {"uz": "Familiya Ism kiriting:\nNamuna: Erkinov Ulugbek", "ru": "Введите Фамилию Имя:\nПример: Эркинов Улугбек"},
    "enter_school_code":      {"uz": "Maktab kodini kiriting (masalan: SHAY186):",     "ru": "Введите код школы (например: SHAY186):"},
    "school_not_found":       {"uz": "❌ Maktab kodi topilmadi. Qayta kiriting (masalan: SHAY186):", "ru": "❌ Код школы не найден. Введите снова (например: SHAY186):"},
    "choose_gender":          {"uz": "🚻 Jinsingizni tanlang:",                        "ru": "🚻 Выберите пол:"},
    "gender_male":            {"uz": "👦 Erkak",                                       "ru": "👦 Мужской"},
    "gender_female":          {"uz": "👧 Ayol",                                        "ru": "👧 Женский"},
    "choose_region":          {"uz": "🌍 Viloyatingizni tanlang:",                     "ru": "🌍 Выберите область:"},
    "choose_district":        {"uz": "🏙 Tumaningizni tanlang:",                       "ru": "🏙 Выберите район:"},
    "region_label":           {"uz": "🌍 Viloyat: <b>{}</b>\n\n🏙 Tumaningizni tanlang:", "ru": "🌍 Область: <b>{}</b>\n\n🏙 Выберите район:"},
    "district_label":         {"uz": "🏙 Tuman: <b>{}</b>\n\n🏫 Maktabingizni tanlang:", "ru": "🏙 Район: <b>{}</b>\n\n🏫 Выберите школу:"},
    "choose_school":          {"uz": "🏫 Maktabingizni tanlang:",                      "ru": "🏫 Выберите школу:"},
    "no_districts":           {"uz": "🏫 Tumanlar topilmadi. Maktab kodingizni kiriting:", "ru": "🏫 Районы не найдены. Введите код школы:"},
    "no_schools":             {"uz": "🏫 Bu tumanda maktab topilmadi. Maktab kodingizni kiriting:", "ru": "🏫 В этом районе школы не найдены. Введите код школы:"},
    "please_wait":            {"uz": "⏳ Iltimos, kuting…",                            "ru": "⏳ Пожалуйста, подождите…"},
    "back_btn":               {"uz": "⬅️ Orqaga",                                     "ru": "⬅️ Назад"},
    "test_start_btn":         {"uz": "📝 Testni boshlash",                             "ru": "📝 Начать тест"},
    "test_done_btn":          {"uz": "✅ Testni tugatdim",                             "ru": "✅ Завершить тест"},
    "ready_msg":              {"uz": "Tayyor! <b>📝 Testni boshlash</b> tugmasi orqali testni boshlang.\nTest tugagach, <b>✅ Testni tugatdim</b> tugmasini bosing — natijangizni ko'rish uchun ma'lumotlaringizni so'raymiz.", "ru": "Готово! Нажмите <b>📝 Начать тест</b> для начала теста.\nПо завершении нажмите <b>✅ Завершить тест</b> — мы запросим данные для просмотра результата."},
    "selected_subjects":      {"uz": "✅ Tanlangan fanlar: <b>{} — {}</b>",           "ru": "✅ Выбранные предметы: <b>{} — {}</b>"},
    "result_header":          {"uz": "<b>Test natijasi:</b>",                          "ru": "<b>Результат теста:</b>"},
    "result_mandatory":       {"uz": "- Majburiy fanlar: {} / 33",                    "ru": "- Обязательные: {} / 33"},
    "result_total":           {"uz": "Jami: <b>{} ball</b>",                          "ru": "Итого: <b>{} балл</b>"},
    "test_not_found":         {"uz": "❌ Test topilmadi. /start v2 bilan qaytadan boshlang.", "ru": "❌ Тест не найден. Начните заново с /start v2."},
    "result_error":           {"uz": "❌ Natijani olishda xatolik ({}). Keyinroq urinib ko'ring.", "ru": "❌ Ошибка получения результата ({}). Попробуйте позже."},
    "subject_error":          {"uz": "❌ Fan tanlovida xatolik. /start v2 bilan qayta urinib ko'ring.", "ru": "❌ Ошибка выбора предмета. Попробуйте /start v2 снова."},
    "test_error":             {"uz": "❌ Test tayyorlashda xatolik ({}).",             "ru": "❌ Ошибка подготовки теста ({})."},
}

def v2_tr(lang: str, key: str) -> str:
    return V2_TEXTS.get(key, {}).get(lang) or V2_TEXTS.get(key, {}).get("uz", "")

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
    if not ids:
        return

    keep: List[int] = []
    to_delete: List[int] = []
    for mid in ids:
        if except_ids and mid in except_ids:
            keep.append(mid)
        else:
            to_delete.append(mid)

    if to_delete:
        async def _safe_delete(mid: int) -> None:
            try:
                await bot.delete_message(chat_id, mid)
            except Exception:
                pass

        # Parallel delete — har bir delete_message ~150ms, ketma-ket bo'lsa
        # bir necha soniyaga cho'zilib, FSM step'larining sekin ko'rinishiga sabab bo'ladi.
        await asyncio.gather(*[_safe_delete(mid) for mid in to_delete])

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
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as r:
                text = await r.text()

                if r.status >= 400:
                    logger.error("[api_get] failed status=%s", r.status)
                    return {"ok": False, "status": r.status, "text": text}

                try:
                    data = await r.json()
                    return data
                except Exception:
                    logger.error("[api_get] json parse error status=%s", r.status)
                    return {"ok": False, "status": r.status, "text": text}

    except asyncio.TimeoutError:
        logger.error("[api_get] timeout")
        return {"ok": False, "status": 504, "text": "timeout"}

    except aiohttp.ClientError as e:
        logger.error("[api_get] network error: %s", type(e).__name__)
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

def _extract_schools_list(payload: Any) -> Optional[List[Dict[str, Any]]]:
    """Backend response'dan schools ro'yxatini ajratib oladi."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return None
    for key in ("items", "results", "schools", "data"):
        v = payload.get(key)
        if isinstance(v, list):
            return v
    return None


_APOSTROPHES = ("ʻ", "ʼ", "‘", "’", "`", "'")


def _norm_locale(s: Any) -> str:
    """
    Region/district nomlarini taqqoslash uchun normalize qiladi:
      - lower-case
      - apostrof variantlari bittaga (`'`)
      - chiziqcha → bo'shliq
      - ortiqcha bo'shliqlar olib tashlanadi
    """
    text = str(s or "").strip().casefold()
    for ch in _APOSTROPHES:
        text = text.replace(ch, "'")
    text = text.replace("-", " ")
    text = re.sub(r"\s+", " ", text)
    # apostrof o'zi ham noaniq mismatch keltirib chiqarishi mumkin (Mirzo Ulug'bek
    # vs Mirzo Ulugbek), shuning uchun normalize'da ularni ham ochiramiz.
    text = text.replace("'", "")
    return text


def _region_variants(region: str) -> Set[str]:
    """
    Bot va /dtm/schools backend'da region nomi farqli yozilgan bo'lishi mumkin
    (masalan: "Toshkent shahar" vs "Toshkent shahri"). Variantlarni qaytaradi.
    Solishtirish _norm_locale orqali ham bajariladi.
    """
    if not region:
        return set()
    base = region.strip()
    out: Set[str] = {base, _norm_locale(base)}
    if "shahar" in base.casefold():
        alt = re.sub(r"shahar", "shahri", base, flags=re.IGNORECASE)
        out |= {alt, _norm_locale(alt)}
    if "shahri" in base.casefold():
        alt = re.sub(r"shahri", "shahar", base, flags=re.IGNORECASE)
        out |= {alt, _norm_locale(alt)}
    return out


def _district_matches(query_district: str, item_district: str) -> bool:
    """Normalized comparison — apostrof/chiziqcha/case farqlariga toqat qiladi."""
    if not query_district or not item_district:
        return False
    return _norm_locale(query_district) == _norm_locale(item_district)


async def _fetch_schools_dtm(region: str, district: str, school_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Yangi /api/v1/dtm/schools endpoint — har turdagi maktablar (school + litsey
    + texnikum) bilan to'liq ro'yxat qaytaradi. X-API-Key talab qiladi.

    Region va district nomi backend'lar orasida farqli yozilgan bo'lishi
    mumkin (apostrof variantlari, "shahar" vs "shahri", chiziqcha va h.k.).
    Shuning uchun query string'da minimal filter qo'yamiz va javobni klient
    tomonida normalize qilingan variantlar bilan moslaymiz:

      - school yoki filtersiz so'rov → district bilan (kichik payload)
      - litsey / texnikum (kichik to'plam ~ 100 item butun bazada) →
        district'siz so'raymiz, javobni district + region variantlari
        bilan client-side filterlaymiz.
    """
    url = f"{API_V1}/dtm/schools"
    # Backend cheklovi: limit <= 200 (422 qaytaradi). 200 — litsey (74) +
    # texnikum (18) bilan yetadi; school filtri bo'lganda ham district
    # narrow qiladi.
    params: Dict[str, Any] = {"limit": 200}
    normalized_type = normalize_school_type(school_type) if school_type else None
    if normalized_type:
        params["type"] = normalized_type

    # litsey/texnikum — kichik to'plam, district query string'iga qo'shmaymiz,
    # apostrof/chiziqcha mismatch'idan qutulamiz.
    send_district_in_query = normalized_type not in ("litsey", "texnikum")
    if send_district_in_query and district:
        params["district"] = district

    headers = {"accept": "application/json"}
    api_key = (SECRET_KEY or "").strip()
    if api_key:
        headers["x-api-key"] = api_key

    timeout = aiohttp.ClientTimeout(total=60)
    logger.info(f"[fetch_schools_dtm] GET {url} params={params}")
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params, headers=headers) as r:
                text = await r.text()
                if r.status >= 400:
                    logger.warning(f"[fetch_schools_dtm] {r.status}: {text[:300]}")
                    return {"ok": False, "status": r.status, "text": text}
                try:
                    data = await r.json()
                except Exception:
                    return {"ok": False, "status": r.status, "text": text}
                lst = _extract_schools_list(data)
                if lst is None:
                    return {"ok": False, "status": 500, "text": f"unexpected payload: {str(data)[:200]}"}

                before = len(lst)

                # Region — variantlar bilan moslash (shahar↔shahri va h.k.)
                if region:
                    region_norms = {_norm_locale(v) for v in _region_variants(region)}
                    lst = [
                        s for s in lst
                        if isinstance(s, dict) and _norm_locale(s.get("region")) in region_norms
                    ]

                # District — apostrof/chiziqcha variantlariga toqat qiluvchi
                # normalize bilan moslash (faqat district query'da yuborilmagan
                # holda kerak, lekin yuborilgan bo'lsa ham xato emas).
                if district:
                    lst = [
                        s for s in lst
                        if isinstance(s, dict) and _district_matches(district, s.get("district"))
                    ]

                logger.info(
                    f"[fetch_schools_dtm] type={normalized_type} region={region!r} "
                    f"district={district!r} api_returned={before} after_filter={len(lst)}"
                )
                return {"ok": True, "schools": lst}
    except asyncio.TimeoutError:
        logger.error("[fetch_schools_dtm] TIMEOUT")
        return {"ok": False, "status": 504, "text": "TimeoutError"}
    except aiohttp.ClientError as e:
        logger.error(f"[fetch_schools_dtm] ClientError: {repr(e)}")
        return {"ok": False, "status": 503, "text": str(e)}


async def _fetch_schools_legacy(region: str, district: str) -> Dict[str, Any]:
    """Eski /admin/districts-and-schools endpoint — fallback (faqat oddiy maktablar)."""
    url = f"{API_V1}/admin/districts-and-schools"
    payload = await _api_get(url, {"region": region, "district": district})
    if isinstance(payload, dict) and payload.get("ok") is False:
        return payload
    if not isinstance(payload, dict) or payload.get("type") != "schools":
        return {"ok": False, "status": 500, "text": f"Unexpected schools payload: {payload}"}
    return {"ok": True, "schools": payload.get("data") or []}


def _merge_schools_by_code(*lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Bir necha ro'yxatni code bo'yicha dedup qilib birlashtiradi (tartib saqlanadi)."""
    seen = set()
    out: List[Dict[str, Any]] = []
    for lst in lists:
        for s in (lst or []):
            if not isinstance(s, dict):
                continue
            code = str(s.get("code") or "").strip()
            if not code or code in seen:
                continue
            seen.add(code)
            out.append(s)
    return out


async def fetch_schools(region: str, district: str, school_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Maktablarni district bo'yicha oladi. Avval yangi /dtm/schools endpoint'ni
    sinaymiz (litsey + texnikum + oddiy maktab — to'liq ro'yxat). Agar u
    ishlamasa yoki bo'sh javob bersa, eski /admin/districts-and-schools'ga
    qaytamiz. Ikkalasi ham ishlasa, dedup qilib birlashtiramiz — backend
    qaysi yangilangan-yangilanmasligidan qat'iy nazar foydalanuvchi to'liq
    ro'yxatni ko'radi.

    school_type berilgan bo'lsa, response'da type maydoni mavjud bo'lganlar
    o'sha turga muvofiq filterlanadi (type'siz row'lar — legacy default
    'school' deb hisoblanadi).
    """
    new_res = await _fetch_schools_dtm(region, district, school_type)
    legacy_res = await _fetch_schools_legacy(region, district)

    new_schools = new_res.get("schools") if new_res.get("ok") else []
    legacy_schools = legacy_res.get("schools") if legacy_res.get("ok") else []

    if not new_schools and not legacy_schools:
        # Ikkalasi ham xato bo'lsa, asosiy javobni qaytarib xato sababini ko'rsatamiz.
        if not new_res.get("ok") and not legacy_res.get("ok"):
            return new_res if new_res.get("text") else legacy_res

    schools = _merge_schools_by_code(new_schools or [], legacy_schools or [])

    if school_type:
        wanted = normalize_school_type(school_type)
        # type'siz row'larni 'school' deb hisoblash (legacy default).
        schools = [
            s for s in schools
            if normalize_school_type(s.get("type")) == wanted
        ]

    logger.info(
        f"[fetch_schools] district={district!r} type={school_type!r} "
        f"new={len(new_schools or [])} legacy={len(legacy_schools or [])} merged={len(schools)}"
    )
    return {"ok": True, "schools": schools}

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
    skipped_offline = 0
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

        # Offline registratsiya o'chirilgan — eski queue'da qolgan offline
        # job'larni qayta yubormaymiz, "cancelled" deb belgilaymiz.
        if normalize_test_type(payload.get("test_type")) == "offline":
            info["status"] = "cancelled"
            info["error"] = "offline_disabled"
            info["updated_at"] = now_str()
            info["note"] = "offline_path_disabled_at_restart"
            await persist_job_update(job_id)
            skipped_offline += 1
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
    if skipped_offline:
        logger.warning(
            f"[JOBS] skipped {skipped_offline} offline job(s) at restart "
            f"(offline path disabled)"
        )
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

        # Offline registratsiya o'chirilgan — failed offline job'lar
        # qayta urinilmaydi.
        if normalize_test_type(payload.get("test_type")) == "offline":
            info.update({
                "status": "cancelled",
                "error": "offline_disabled",
                "updated_at": now_str(),
                "note": "offline_path_disabled_skipped_retry",
            })
            await persist_job_update(job_id)
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
            # Defensiv tekshiruv: offline job worker'ga yetib kelsa, ishlamaymiz.
            if normalize_test_type((job.payload or {}).get("test_type")) == "offline":
                REGISTER_JOBS[job.job_id] = REGISTER_JOBS.get(job.job_id, {}) or {}
                REGISTER_JOBS[job.job_id].update({
                    "status": "cancelled",
                    "error": "offline_disabled",
                    "updated_at": now_str(),
                    "note": "offline_path_disabled_in_worker",
                    "user_id": job.user_id,
                    "chat_id": job.chat_id,
                    "ui_lang": job.ui_lang,
                    "payload": job.payload,
                })
                await persist_job_update(job.job_id)
                logger.warning(
                    f"[QUEUE] worker#{worker_idx} dropped offline job_id={job.job_id} "
                    f"user_id={job.user_id} (offline disabled)"
                )
                continue

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
    # Queue stats periodic broadcast'i guruhga kerak emas — o'chirilgan.
    # await ensure_register_queue_stats_notifier(bot)
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


def flow_choice_kb(ui_lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(tr(ui_lang, "btn_flow_test"), callback_data="flow:test"))
    kb.add(InlineKeyboardButton(tr(ui_lang, "btn_flow_dtm_result"), callback_data="flow:mandat"))
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

def _channel_join_url(channel: Dict[str, Any]) -> Optional[str]:
    cid = str(channel.get("channel_id") or "").strip()
    if cid.startswith("@"):
        return f"https://t.me/{cid[1:]}"
    if cid and not cid.lstrip("-").isdigit():
        return f"https://t.me/{cid}"
    return None  # numeric chat_id — username yo'q, link qurib bo'lmaydi


def sub_kb(channels: Optional[list] = None, check_callback: str = "check_sub"):
    """Majburiy kanallar uchun obuna klaviaturasi.
    channels berilmasa (eski static fallback) — CHANNEL_LINK ishlatiladi."""
    kb = InlineKeyboardMarkup(row_width=1)
    if channels:
        for ch in channels:
            title = ch.get("title") or ch.get("channel_id") or "Kanal"
            url = _channel_join_url(ch)
            if url:
                kb.add(InlineKeyboardButton(f"✅ {title}", url=url))
    else:
        kb.add(InlineKeyboardButton("✅ Kanalga obuna bo‘lish", url=CHANNEL_LINK))
    kb.add(InlineKeyboardButton("🔄 Tekshirish", callback_data=check_callback))
    return kb

def _dedupe_keep_order(items: List[str]) -> List[str]:
    """Bo'shliqlarni trim qilib, case-insensitive duplicate'larni tashlaydi.
    Original tartib saqlanadi, birinchi uchragan variant qoladi."""
    seen: Set[str] = set()
    out: List[str] = []
    for raw in items or []:
        s = str(raw or "").strip()
        if not s:
            continue
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def regions_kb(ui_lang: str, regions: List[str]):
    kb = InlineKeyboardMarkup(row_width=2)
    for r in _dedupe_keep_order(regions)[:60]:
        rr = r[:50]
        kb.insert(InlineKeyboardButton(rr, callback_data=f"reg_region:{rr}"))
    kb.add(InlineKeyboardButton(tr(ui_lang, "btn_cancel"), callback_data="reg_cancel"))
    return kb

def districts_kb(ui_lang: str, districts: List[str]):
    kb = InlineKeyboardMarkup(row_width=1)
    for d in _dedupe_keep_order(districts)[:80]:
        dd = d[:50]
        kb.add(InlineKeyboardButton(dd, callback_data=f"reg_district:{dd}"))
    kb.row(
        InlineKeyboardButton(tr(ui_lang, "btn_back"), callback_data="reg_back:region"),
        InlineKeyboardButton(tr(ui_lang, "btn_cancel"), callback_data="reg_cancel"),
    )
    return kb

import difflib

SCHOOL_TYPE_VALUES = ("school", "litsey", "texnikum")


def _norm_search(s: str) -> str:
    """Lowercase, strip, oddiy translit (apostroflar) — qidiruv uchun."""
    s = (s or "").strip().lower()
    # Apostrof variantlarini bittaga keltirish
    for ch in ("ʻ", "ʼ", "‘", "’", "`", "'"):
        s = s.replace(ch, "")
    s = re.sub(r"\s+", " ", s)
    return s


def _school_match_score(query: str, school: Dict[str, Any]) -> float:
    q = _norm_search(query)
    if not q:
        return 0.0
    name = _norm_search(str(school.get("name") or ""))
    code = _norm_search(str(school.get("code") or ""))
    if q in name:
        return 1.0
    if q in code:
        return 0.95
    # Har bir so'z bo'yicha tekshirish
    name_tokens = name.split()
    if any(tok.startswith(q) for tok in name_tokens):
        return 0.9
    # Fuzzy fallback
    ratio = difflib.SequenceMatcher(None, q, name).ratio()
    return ratio


def filter_schools_by_query(
    query: str,
    schools: List[Dict[str, Any]],
    *,
    limit: int = 30,
    min_score: float = 0.55,
) -> List[Dict[str, Any]]:
    if not _norm_search(query):
        return schools[:limit]
    scored = [(_school_match_score(query, s), s) for s in (schools or []) if isinstance(s, dict)]
    scored = [(sc, s) for sc, s in scored if sc >= min_score]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:limit]]



def normalize_school_type(value: Any) -> str:
    """Backend default 'school'. Noma'lum/bo'sh → 'school'."""
    if value is None:
        return "school"
    s = str(value).strip().lower()
    if s in SCHOOL_TYPE_VALUES:
        return s
    return "school"


def school_type_label(school_type: str, ui_lang: str = "uz") -> str:
    mapping = TEXTS.get("school_type_label") or {}
    entry = mapping.get(normalize_school_type(school_type)) or mapping.get("school") or {}
    return entry.get(ui_lang) or entry.get("uz") or "Maktab"


def school_type_kb(ui_lang: str, *, show_all_fallback: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(tr(ui_lang, "school_type_school"),   callback_data="reg_school_type:school"),
        InlineKeyboardButton(tr(ui_lang, "school_type_litsey"),   callback_data="reg_school_type:litsey"),
        InlineKeyboardButton(tr(ui_lang, "school_type_texnikum"), callback_data="reg_school_type:texnikum"),
    )
    if show_all_fallback:
        kb.add(InlineKeyboardButton(tr(ui_lang, "btn_school_show_all"), callback_data="reg_school_type:any"))
    kb.row(
        InlineKeyboardButton(tr(ui_lang, "btn_back"), callback_data="reg_back:district"),
        InlineKeyboardButton(tr(ui_lang, "btn_cancel"), callback_data="reg_cancel"),
    )
    return kb


# Inline mode orqali qidirilgan natija bossanga, bot xabar matnida shu marker
# bilan school_code yashirin yuboradi. Message handler shu marker'ni topib
# tegishli maktabni FSM ga qo'yadi.
INLINE_PICK_PREFIX = "##sch##:"


# Bitta sahifada ko'rsatiladigan maktablar soni (2 ustun × 5 qator).
SCHOOLS_PAGE_SIZE = 10


def _schools_nav_row(page: int, total: int, cb_prefix: str) -> Optional[List[InlineKeyboardButton]]:
    """Sahifalash navigatsiya qatori: ⬅️  N/M  ➡️. Bitta sahifa bo'lsa None."""
    pages = max(1, (total + SCHOOLS_PAGE_SIZE - 1) // SCHOOLS_PAGE_SIZE)
    if pages <= 1:
        return None
    page = max(0, min(page, pages - 1))
    row: List[InlineKeyboardButton] = []
    if page > 0:
        row.append(InlineKeyboardButton("⬅️", callback_data=f"{cb_prefix}{page - 1}"))
    row.append(InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        row.append(InlineKeyboardButton("➡️", callback_data=f"{cb_prefix}{page + 1}"))
    return row


def schools_kb(
    ui_lang: str,
    schools: List[Dict[str, Any]],
    *,
    show_search: bool = False,
    show_back_to_full: bool = False,
    show_inline_search: bool = True,
    back_to: str = "district",
    page: int = 0,
):
    kb = InlineKeyboardMarkup(row_width=2)
    schools = schools or []
    pages = max(1, (len(schools) + SCHOOLS_PAGE_SIZE - 1) // SCHOOLS_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    start = page * SCHOOLS_PAGE_SIZE
    for s in schools[start:start + SCHOOLS_PAGE_SIZE]:
        code = str(s.get("code") or "")
        name = str(s.get("name") or code)
        if not code:
            continue
        kb.insert(InlineKeyboardButton(name[:32], callback_data=f"reg_school:{code}"))
    nav = _schools_nav_row(page, len(schools), "reg_school_page:")
    if nav:
        kb.row(*nav)
    if show_inline_search:
        # switch_inline_query_current_chat — joriy chat'da `@bot ` deb yozadi va
        # foydalanuvchi har keystroke'da real-time inline natijalarni ko'radi.
        kb.row(InlineKeyboardButton(tr(ui_lang, "btn_school_inline_search"), switch_inline_query_current_chat=""))
    if show_search:
        kb.row(InlineKeyboardButton(tr(ui_lang, "btn_school_search"), callback_data="reg_school_search"))
    if show_back_to_full:
        kb.row(InlineKeyboardButton(tr(ui_lang, "btn_school_show_all"), callback_data="reg_school_show_all"))
    kb.row(
        InlineKeyboardButton(tr(ui_lang, "btn_back"), callback_data=f"reg_back:{back_to}"),
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


def test_type_badge(test_type: Any) -> str:
    """Admin guruhi xabarlari uchun test_type badge: 🟢 ONLINE / 🔵 OFFLINE."""
    tt = normalize_test_type(test_type)
    if tt == "online":
        return "🟢 <b>ONLINE</b>"
    return "🔵 <b>OFFLINE</b>"


def _badge_from_payload(data: Any) -> str:
    if isinstance(data, dict):
        return test_type_badge(data.get("test_type") or data.get("test_intent"))
    return test_type_badge(None)


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

_SUBJECT_NAME_BY_ID: Dict[int, str] = {
    int(info["id"]): name
    for name, info in SUBJECTS_MAP.items()
    if isinstance(info, dict) and info.get("id") is not None
}


def _subject_label(subject_id: Any, fallback_name: Any = None) -> str:
    if fallback_name:
        name = str(fallback_name).strip()
        if name:
            if subject_id in (None, ""):
                return name
            return f"{name} (#{subject_id})"
    try:
        sid = int(subject_id)
    except (TypeError, ValueError):
        return str(subject_id) if subject_id not in (None, "") else "-"
    name = _SUBJECT_NAME_BY_ID.get(sid)
    if name:
        return f"{name} (#{sid})"
    return str(sid)


def build_register_details(data: dict) -> str:
    first = _subject_label(data.get("first_subject_id"), data.get("first_subject_uz"))
    second = _subject_label(data.get("second_subject_id"), data.get("second_subject_uz"))
    school_type_text = (
        school_type_label(data["school_type"], "uz")
        if data.get("school_type")
        else "-"
    )
    return (
        f"📞 <b>Phone:</b> <code>{data.get('phone','-')}</code>\n"
        f"🌍 <b>Region:</b> <code>{data.get('region','-')}</code>\n"
        f"🏙 <b>District:</b> <code>{data.get('district','-')}</code>\n"
        f"🎓 <b>School type:</b> <code>{school_type_text}</code>\n"
        f"🏫 <b>School code:</b> <code>{data.get('school_code','-')}</code>\n"
        f"🏷 <b>Class letter:</b> <code>{data.get('class_letter') or data.get('group_name') or '-'}</code>\n"
        f"🗣 <b>Exam lang:</b> <code>{data.get('exam_lang') or data.get('language') or '-'}</code>\n"
        f"🚻 <b>Gender:</b> <code>{data.get('gender','-')}</code>\n"
        f"📚 <b>Subjects:</b> <code>{first}</code> + <code>{second}</code>"
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
        f"🚨 <b>ACCOUNT REUSE ALERT</b> · {_badge_from_payload(current_payload)}\n"
        f"🕒 <b>Time:</b> {now_str()}\n"
        f"👤 <b>Telegram user:</b> {_tg_user_link(user)}\n"
        f"🆔 <b>Chat ID:</b> <code>{user.id}</code>\n\n"
        f"📌 <b>Oldingi muvaffaqiyatli register:</b> {_badge_from_payload(previous_payload)}\n"
        f"🧩 <b>Job ID:</b> <code>{prev_job_id}</code>\n"
        f"🕒 <b>Vaqt:</b> <code>{prev_time}</code>\n"
        f"{build_register_details(previous_payload)}\n"
        f"📝 <b>Full name:</b> <code>{previous_payload.get('full_name','-')}</code>\n\n"
        f"📌 <b>Hozirgi register:</b> {_badge_from_payload(current_payload)}\n"
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
    school_type_text = (
        school_type_label(data["school_type"], ui_lang)
        if data.get("school_type")
        else "-"
    )

    lines = [
        tr(ui_lang, "confirm_title").rstrip(),
        "",
        f"{lbl(ui_lang,'phone')}: {data.get('phone','-')}",
        f"{lbl(ui_lang,'fio')}: {data.get('fio','-')}",
        f"{lbl(ui_lang,'gender')}: {gender_label}",
        f"{lbl(ui_lang,'region')}: {data.get('region','-')}",
        f"{lbl(ui_lang,'district')}: {data.get('district','-')}",
        f"{lbl(ui_lang,'school_type')}: {school_type_text}",
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
def online_test_url(user_id: Optional[int] = None) -> str:
    """
    WebApp URL'ini chat_id parametri bilan qaytaradi. Frontend brauzerda
    ochilganda chat_id'ni shu URL'dan o'qib avtomatik login qiladi
    (Telegram WebApp ichida ochilsa initData ustunlik beradi).
    """
    from data.config import WEBAPP_URL
    base = (WEBAPP_URL or "").strip()
    if not user_id:
        return base
    sep = "&" if ("?" in base) else "?"
    return f"{base}{sep}chat_id={int(user_id)}"


# ============================================================
# v2 (reklama) oqim — docs/online-test-v2-promo-bot.md
# ============================================================
# /start v2: track → GET /dtm/online/subjects → 2 bosqichli fan tanlash →
# POST /dtm/online/v2/start → reply-keyboard WebApp tugma → test → web_app_data
# (sendData) → forma (FIO/tel/maktab) → POST /dtm/online/v2/complete → ball.
# PDF backend worker tomonidan avtomatik chatga keladi.

def v2_webapp_url(user_id: Optional[int] = None, lang: Optional[str] = None) -> str:
    """v2 WebApp URL. V2_WEBAPP_URL berilmasa WEBAPP_URL ishlatiladi. WebApp
    chat_id'ni initData'dan oladi; brauzer fallback uchun query'ga ham qo'yamiz.
    Test tili (lang) WebApp'ga query orqali uzatiladi."""
    from data.config import V2_WEBAPP_URL, WEBAPP_URL
    base = (V2_WEBAPP_URL or "").strip() or (WEBAPP_URL or "").strip()
    params = []
    if user_id:
        params.append(f"chat_id={int(user_id)}")
    if lang:
        params.append(f"lang={lang}")
    for p in params:
        sep = "&" if ("?" in base) else "?"
        base = f"{base}{sep}{p}"
    return base


async def _v2_api_get(path: str) -> Dict[str, Any]:
    url = f"{V2_API_V1}{path}"
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as r:
                text = await r.text()
                if r.status >= 400:
                    logger.warning(f"[v2 GET] {path} -> {r.status}: {text[:200]}")
                    return {"ok": False, "status": r.status, "text": text}
                try:
                    return {"ok": True, "status": r.status, "data": await r.json()}
                except Exception:
                    return {"ok": False, "status": r.status, "text": text}
    except Exception as e:
        logger.error(f"[v2 GET] {path} error: {repr(e)}")
        return {"ok": False, "status": 503, "text": str(e)}


async def _v2_api_post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{V2_API_V1}{path}"
    timeout = aiohttp.ClientTimeout(total=30)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as r:
                text = await r.text()
                if r.status >= 400:
                    logger.warning(f"[v2 POST] {path} -> {r.status}: {text[:200]}")
                    return {"ok": False, "status": r.status, "text": text}
                try:
                    return {"ok": True, "status": r.status, "data": await r.json()}
                except Exception:
                    return {"ok": True, "status": r.status, "data": {}, "raw": text}
    except Exception as e:
        logger.error(f"[v2 POST] {path} error: {repr(e)}")
        return {"ok": False, "status": 503, "text": str(e)}


def _v2_extract_subjects(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [s for s in data if isinstance(s, dict)]
    if isinstance(data, dict):
        for key in ("items", "results", "subjects", "data"):
            v = data.get(key)
            if isinstance(v, list):
                return [s for s in v if isinstance(s, dict)]
    return []


def _v2_subject_name(s: Dict[str, Any]) -> str:
    return str(s.get("name_uz") or s.get("name") or s.get("name_ru") or s.get("mt_id") or "")


def _v2_subjects_kb(subjects: List[Dict[str, Any]], prefix: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    btns = []
    for s in subjects:
        mt = s.get("mt_id")
        if mt is None:
            continue
        btns.append(types.InlineKeyboardButton(_v2_subject_name(s), callback_data=f"{prefix}:{mt}"))
    if btns:
        kb.add(*btns)
    return kb


def _v2_name_by_id(subjects: List[Dict[str, Any]], mt_id: int) -> str:
    for s in subjects:
        if str(s.get("mt_id")) == str(mt_id):
            return _v2_subject_name(s)
    return str(mt_id)


def _v2_norm(s: Any) -> str:
    return str(s or "").strip().lower()


def _v2_name_to_mt(subjects: List[Dict[str, Any]]) -> Dict[str, int]:
    """Backend fan nomi (uz/ru/name) -> mt_id. Normalizatsiya qilingan kalit."""
    m: Dict[str, int] = {}
    for s in subjects:
        mt = s.get("mt_id")
        if mt is None:
            continue
        for key in ("name_uz", "name", "name_ru"):
            v = s.get(key)
            if v:
                m.setdefault(_v2_norm(v), int(mt))
    return m


# (uz_first, uz_second, ru_first, ru_second)
_V2_ORDERED_PAIRS = [
    ("Matematika",            "Ingliz tili",           "Математика",                  "Английский язык"),
    ("Matematika",            "Fizika",                "Математика",                  "Физика"),
    ("Matematika",            "Ona tili va adabiyoti", "Математика",                  "Русский язык и литература"),
    ("Biologiya",             "Kimyo",                 "Биология",                    "Химия"),
    ("Biologiya",             "Ona tili va adabiyoti", "Биология",                    "Русский язык и литература"),
    ("Ingliz tili",           "Ona tili va adabiyoti", "Английский язык",             "Русский язык и литература"),
    ("Ona tili va adabiyoti", "Matematika",            "Русский язык и литература",   "Математика"),
    ("Huquq",                 "Ingliz tili",           "Право",                       "Английский язык"),
    ("Kimyo",                 "Biologiya",             "Химия",                       "Биология"),
    ("Kimyo",                 "Matematika",            "Химия",                       "Математика"),
    ("Tarix",                 "Ingliz tili",           "История",                     "Английский язык"),
    ("Tarix",                 "Ona tili va adabiyoti", "История",                     "Русский язык и литература"),
    ("Tarix",                 "Geografiya",            "История",                     "География"),
    ("Fizika",                "Matematika",            "Физика",                      "Математика"),
    ("Fizika",                "Ingliz tili",           "Физика",                      "Английский язык"),
]

_V2_NAME_ALIASES = {
    "ona tili va adabiyoti":       "ona tili va adabiyot",
    "huquq":                       "davlat va huquq asoslari",
    "русский язык и литература":   "ona tili va adabiyot",
    "право":                       "davlat va huquq asoslari",
    "история":                     "tarix",
    "география":                   "geografiya",
    "математика":                  "matematika",
    "физика":                      "fizika",
    "химия":                       "kimyo",
    "биология":                    "biologiya",
    "английский язык":             "ingliz tili",
}


def _v2_lookup_mt(name2mt: Dict[str, int], name: str) -> Optional[int]:
    norm = _v2_norm(name)
    mt = name2mt.get(norm)
    if mt is None:
        alias = _V2_NAME_ALIASES.get(norm)
        if alias:
            mt = name2mt.get(_v2_norm(alias))
    return mt


def _v2_pairs_kb(subjects: List[Dict[str, Any]], lang: str = "uz") -> Tuple[types.InlineKeyboardMarkup, int]:
    """Aniq tartibdagi juftliklar — tanlangan tilda."""
    name2mt = _v2_name_to_mt(subjects)
    kb = types.InlineKeyboardMarkup(row_width=1)
    count = 0
    for uz_first, uz_second, ru_first, ru_second in _V2_ORDERED_PAIRS:
        first_label  = ru_first  if lang == "ru" else uz_first
        second_label = ru_second if lang == "ru" else uz_second
        first_mt = _v2_lookup_mt(name2mt, uz_first) or _v2_lookup_mt(name2mt, ru_first)
        second_mt = _v2_lookup_mt(name2mt, uz_second) or _v2_lookup_mt(name2mt, ru_second)
        if first_mt is None or second_mt is None:
            continue
        kb.add(types.InlineKeyboardButton(
            f"{first_label} — {second_label}",
            callback_data=f"v2pair:{first_mt}|{second_mt}",
        ))
        count += 1
    return kb, count


def _v2_pdf_url(d: Dict[str, Any]) -> Optional[str]:
    """complete javobidan PDF havolasini topadi. Nisbiy yo'lni V2 host'iga ulaydi."""
    if not isinstance(d, dict):
        return None
    for k in ("pdf_url", "pdf", "pdf_link", "file_url", "result_pdf", "pdf_file", "url"):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            u = v.strip()
            if u.startswith("http"):
                return u
            if u.startswith("/"):
                from urllib.parse import urlsplit
                p = urlsplit(V2_API_V1)
                return f"{p.scheme}://{p.netloc}{u}"
    return None


def _v2_pdf_button_kb(url: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(text="📄 Natijani PDF'da ko'rish", url=url))
    return kb


async def _v2_send_pdf_document(message: types.Message, url: str) -> bool:
    """PDF'ni URL'dan yuklab olib chatga hujjat (fayl) sifatida yuboradi.
    Muvaffaqiyatli bo'lsa True."""
    if not url:
        return False
    try:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as r:
                if r.status >= 400:
                    logger.warning(f"[v2 pdf] download {r.status}: {url}")
                    return False
                content = await r.read()
        if not content:
            return False
        bio = io.BytesIO(content)
        bio.name = "natija.pdf"
        cert_kb = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("🎓 Sertifikatni yuklab olish", url="https://mentalaba.uz/auth?sign-in")
        )
        await message.answer_document(
            types.InputFile(bio, filename="natija.pdf"),
            caption="📄 Natijangiz (PDF)",
            reply_markup=cert_kb,
        )
        return True
    except Exception as e:
        logger.error(f"[v2 pdf] send document error: {repr(e)}")
        return False


async def _v2_send_pdf_button(message: types.Message, d: Dict[str, Any]) -> None:
    """PDF havolasi bo'lsa inline tugma + faylni hujjat ko'rinishida yuboradi.
    complete'da null bo'lsa /v2/result poll qiladi va kutish davomida
    placeholder'ni yangilab turadi (progress)."""
    url = _v2_pdf_url(d)
    if url:
        await _v2_send_pdf_document(message, url)
        return

    placeholder = await message.answer("📄 Natija PDF'i tayyorlanmoqda, biroz kuting…")
    attempts, delay = 20, 3.0
    waits = [
        "📄 Natija PDF'i tayyorlanmoqda, biroz kuting",
        "📄 PDF render qilinmoqda, deyarli tayyor",
        "📄 Natijangiz hujjati shakllanmoqda",
    ]
    path = f"/dtm/online/v2/result?bot_id={message.chat.id}"
    for i in range(attempts):
        res = await _v2_api_get(path)
        if res.get("ok"):
            dd = res.get("data") or {}
            u = _v2_pdf_url(dd)
            if u:
                try:
                    await placeholder.delete()
                except Exception:
                    pass
                await _v2_send_pdf_document(message, u)
                return
        # progress yangilash (matn har safar farqli — "not modified" bo'lmasin)
        dots = "." * (1 + i % 3)
        try:
            await placeholder.edit_text(f"{waits[i % len(waits)]}{dots}")
        except Exception:
            pass
        await asyncio.sleep(delay)

    try:
        await placeholder.edit_text("📄 PDF biroz keyinroq tayyor bo'ladi — tayyor bo'lgach yuboriladi.")
    except Exception:
        pass


async def _v2_track(state: FSMContext, *message_ids: Any) -> None:
    """Oraliq xabar id'larini yig'ib boradi — natijada o'chiriladi."""
    data = await state.get_data()
    trash = list(data.get("v2_trash") or [])
    trash.extend(int(m) for m in message_ids if m)
    await state.update_data(v2_trash=trash)


async def _v2_say(message: types.Message, state: FSMContext, text: str, **kw) -> types.Message:
    """Bot xabarini yuborib, id'sini track qiladi (oraliq xabar — keyin o'chadi)."""
    m = await message.answer(text, **kw)
    await _v2_track(state, m.message_id)
    return m


async def _v2_cleanup(bot, chat_id: int, state: FSMContext) -> None:
    """Yig'ilgan oraliq xabarlarni o'chiradi (form/cascade prompt + user javoblari)."""
    data = await state.get_data()
    for mid in (data.get("v2_trash") or []):
        try:
            await bot.delete_message(chat_id, mid)
        except Exception:
            pass


async def _v2_begin_test(call: types.CallbackQuery, state: FSMContext,
                         first_id: int, second_id: int,
                         first_name: str, second_name: str) -> None:
    """Test + 90-savol daftari yaratish, WebApp tugmasini ko'rsatish."""
    # Natija matni uchun fan nomlarini saqlab qo'yamiz
    await state.update_data(first_subject_name=first_name, second_subject_name=second_name)

    data = await state.get_data()
    payload: Dict[str, Any] = {
        "bot_id": str(call.from_user.id),
        "first_subject_id": first_id,
        "second_subject_id": second_id,
        "language": data.get("exam_lang") or "uz",
    }
    if call.from_user.username:
        payload["username"] = call.from_user.username

    lang = data.get("exam_lang") or "uz"
    res = await _v2_api_post("/dtm/online/v2/start", payload)
    if not res.get("ok"):
        txt = str(res.get("text") or "")
        if res.get("status") == 400 and "subject" in txt.lower():
            await call.message.answer(v2_tr(lang, "subject_error"))
        else:
            await call.message.answer(v2_tr(lang, "test_error").format(res.get("status")))
        await state.finish()
        return

    # Matn tagida inline tugmalar: WebApp ochish + test tugashini bildirish.
    # Eslatma: inline WebApp sendData yubormaydi — shuning uchun "Testni tugatdim"
    # tugmasi forma bosqichini qo'lda boshlaydi (v2_done_btn).
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton(
        text=v2_tr(lang, "test_start_btn"),
        web_app=types.WebAppInfo(url=v2_webapp_url(call.from_user.id, data.get("exam_lang") or "uz")),
    ))
    kb.add(types.InlineKeyboardButton(
        text=v2_tr(lang, "test_done_btn"),
        callback_data="v2done",
    ))

    await OnlineV2.in_test.set()
    try:
        await call.message.edit_text(
            v2_tr(lang, "selected_subjects").format(first_name, second_name),
            parse_mode="HTML",
        )
    except Exception:
        pass
    tayyor = await call.message.answer(
        v2_tr(lang, "ready_msg"),
        parse_mode="HTML",
        reply_markup=kb,
    )
    await _v2_track(state, call.message.message_id, tayyor.message_id)


async def _track_start_v2(tg_user) -> None:
    """v2: /start bosgan userni bazaga yozish — idempotent, best-effort.
    X-Api-Key talab qilinmaydi (ochiq endpoint). Xato test oqimini bloklamasin."""
    payload: Dict[str, Any] = {"bot_id": str(tg_user.id)}
    if tg_user.username:
        payload["username"] = tg_user.username  # @ siz; bo'sh bo'lsa yuborilmaydi
    res = await _v2_api_post("/auth/register/start", payload)
    logger.info(f"[v2 track] register/start -> {res.get('status')} user_id={tg_user.id}")


async def on_start_v2(message: types.Message, state: FSMContext) -> None:
    # 0) Kanal obunasini tekshiramiz
    not_joined = await check_subscriptions(message.from_user.id, message.bot)
    if not_joined:
        await message.answer(
            "Botdan foydalanish uchun rasmiy kanalimizga a'zo bo'ling! ✅",
            reply_markup=sub_kb(not_joined, check_callback="check_sub_v2"),
        )
        return

    # 1) tracking (best-effort, bloklamaydi)
    await _track_start_v2(message.from_user)

    # 2) fan ro'yxati — backend mt_id'lari (lokal SUBJECTS_MAP emas)
    res = await _v2_api_get("/dtm/online/subjects")
    subjects = _v2_extract_subjects(res.get("data")) if res.get("ok") else []
    if not subjects:
        await message.answer(
            "⚠️ Hozircha fanlar ro'yxatini olishda xatolik. Birozdan so'ng /start qayta urinib ko'ring."
        )
        return

    await state.update_data(v2_subjects=subjects)

    # 1-qadam: test tilini tanlash (fan tanlashdan oldin)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="v2lang:uz"),
        types.InlineKeyboardButton("🇷🇺 Русский", callback_data="v2lang:ru"),
    )
    await message.answer(
        "🎯 <b>Bepul DTM sinov testi!</b>\n\nTest tilini tanlang:",
        parse_mode="HTML",
        reply_markup=kb,
        disable_web_page_preview=True,
    )
    await OnlineV2.exam_lang.set()


async def _v2_show_subjects(message: types.Message, state: FSMContext, *, edit: bool = False) -> None:
    """Fan kombinatsiyalarini (yoki 2-bosqichli tanlovni) ko'rsatadi."""
    data = await state.get_data()
    subjects = data.get("v2_subjects") or []

    lang = data.get("exam_lang") or "uz"
    pairs_kb, n_pairs = _v2_pairs_kb(subjects, lang)
    if n_pairs:
        text = v2_tr(lang, "subjects_choose")
        kb = pairs_kb
    else:
        # Fallback: kombinatsiya tuzib bo'lmasa — 2 bosqichli tanlov
        text = v2_tr(lang, "subjects_choose_first")
        kb = _v2_subjects_kb(subjects, "v2s1")

    if edit:
        try:
            await message.edit_text(text, reply_markup=kb)
        except Exception:
            await message.answer(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)
    await OnlineV2.first_subject.set()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("v2lang:"), state=OnlineV2.exam_lang)
async def v2_pick_lang(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    lang = call.data.split(":", 1)[1]
    if lang not in ("uz", "ru"):
        lang = "uz"
    await state.update_data(exam_lang=lang)

    try:
        await call.message.edit_text(tr(lang, "flow_choose"), reply_markup=flow_choice_kb(lang))
    except Exception:
        await call.message.answer(tr(lang, "flow_choose"), reply_markup=flow_choice_kb(lang))


@dp.callback_query_handler(lambda c: c.data == "flow:test", state=OnlineV2.exam_lang)
async def v2_pick_flow_test(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await _v2_show_subjects(call.message, state, edit=True)


@dp.callback_query_handler(lambda c: c.data == "flow:mandat", state=OnlineV2.exam_lang)
async def v2_pick_flow_mandat(call: types.CallbackQuery, state: FSMContext):
    await call.answer()

    try:
        await call.message.delete()
    except Exception:
        pass

    await state.finish()
    await call.bot.send_message(call.message.chat.id, MANDAT_ASK_ID_TEXT, parse_mode="HTML")
    await MandatResult.waiting_id.set()


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("v2pair:"), state=OnlineV2.first_subject)
async def v2_pick_pair(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    lang = data.get("exam_lang") or "uz"
    try:
        raw = call.data.split(":", 1)[1]
        first_id, second_id = (int(x) for x in raw.split("|", 1))
    except Exception:
        await call.answer(v2_tr(lang, "pair_not_found"), show_alert=True)
        return

    subjects = data.get("v2_subjects") or []
    first_name = _v2_name_by_id(subjects, first_id)
    second_name = _v2_name_by_id(subjects, second_id)
    await state.update_data(
        first_subject_id=first_id, first_subject_name=first_name,
        second_subject_id=second_id, second_subject_name=second_name,
    )
    await _v2_begin_test(call, state, first_id, second_id, first_name, second_name)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("v2s1:"), state=OnlineV2.first_subject)
async def v2_pick_first(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    lang = data.get("exam_lang") or "uz"
    try:
        first_id = int(call.data.split(":", 1)[1])
    except Exception:
        await call.answer(v2_tr(lang, "subject_not_found"), show_alert=True)
        return

    subjects = data.get("v2_subjects") or []
    first_name = _v2_name_by_id(subjects, first_id)
    await state.update_data(first_subject_id=first_id, first_subject_name=first_name)

    await OnlineV2.second_subject.set()
    try:
        await call.message.edit_text(
            v2_tr(lang, "first_subject_selected").format(first_name),
            parse_mode="HTML",
            reply_markup=_v2_subjects_kb(subjects, "v2s2"),
        )
    except Exception:
        await call.message.answer(
            v2_tr(lang, "subjects_choose_second"),
            reply_markup=_v2_subjects_kb(subjects, "v2s2"),
        )


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("v2s2:"), state=OnlineV2.second_subject)
async def v2_pick_second(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    lang = data.get("exam_lang") or "uz"
    try:
        second_id = int(call.data.split(":", 1)[1])
    except Exception:
        await call.answer(v2_tr(lang, "subject_not_found"), show_alert=True)
        return

    subjects = data.get("v2_subjects") or []
    first_id = data.get("first_subject_id")
    first_name = data.get("first_subject_name") or _v2_name_by_id(subjects, first_id)
    second_name = _v2_name_by_id(subjects, second_id)

    await _v2_begin_test(call, state, first_id, second_id, first_name, second_name)


async def _v2_ask_phone(message: types.Message, state: FSMContext) -> None:
    # 1-qadam: telefon raqam — contact share tugmasi bilan
    data = await state.get_data()
    lang = data.get("exam_lang") or "uz"
    await OnlineV2.phone.set()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton(text=v2_tr(lang, "enter_phone_btn"), request_contact=True))
    sent = await message.answer(
        v2_tr(lang, "test_submitted"),
        parse_mode="HTML",
        reply_markup=kb,
    )
    await _v2_track(state, sent.message_id)


@dp.callback_query_handler(lambda c: c.data == "v2done", state=OnlineV2.in_test)
async def v2_done_btn(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    try:
        await call.message.edit_reply_markup()  # tugmalarni olib tashlash (qayta bosilmasin)
    except Exception:
        pass
    await _v2_ask_phone(call.message, state)


async def _restart_if_start(message: types.Message, state: FSMContext) -> bool:
    """Har qanday FSM state'da user /start yozsa — generic text handler tutib
    olmasin, balki to'liq /start oqimi (state.finish + cleanup) ishlasin.
    Tutib olingan bo'lsa True qaytaradi."""
    txt = (message.text or "").strip()
    if txt == "/start" or txt.startswith("/start ") or txt.startswith("/start@"):
        await start_cmd(message, state)
        return True
    return False


@dp.message_handler(content_types=types.ContentType.WEB_APP_DATA, state=OnlineV2.in_test)
async def v2_on_test_done(message: types.Message, state: FSMContext):
    # Fallback: agar WebApp sendData ishlatsa ham forma boshlanadi
    await _v2_track(state, message.message_id)
    await _v2_ask_phone(message, state)


@dp.message_handler(content_types=types.ContentType.CONTACT, state=OnlineV2.phone)
@dp.message_handler(state=OnlineV2.phone)
async def v2_get_phone(message: types.Message, state: FSMContext):
    if await _restart_if_start(message, state):
        return
    await _v2_track(state, message.message_id)  # user input (xato bo'lsa ham)
    data = await state.get_data()
    lang = data.get("exam_lang") or "uz"
    phone_text = message.contact.phone_number if message.contact else (message.text or "")
    if not is_phone_ok(phone_text):
        await _v2_say(message, state, tr(lang, "phone_invalid"))
        return
    await state.update_data(phone=normalize_uz_phone(phone_text))
    await OnlineV2.full_name.set()
    sent = await message.answer(
        v2_tr(lang, "enter_fio"),
        reply_markup=ReplyKeyboardRemove(),
    )
    await _v2_track(state, sent.message_id)


@dp.message_handler(state=OnlineV2.full_name)
async def v2_get_name(message: types.Message, state: FSMContext):
    if await _restart_if_start(message, state):
        return
    await _v2_track(state, message.message_id)  # user input (xato bo’lsa ham)
    data = await state.get_data()
    lang = data.get("exam_lang") or "uz"
    fio = normalize_fio_to_surname_name(message.text or "")
    if not fio:
        await _v2_say(message, state, tr(lang, "fio_invalid_2words"))
        return
    await state.update_data(full_name=fio)
    await _v2_ask_region(message, state)


# ---- v2 maktab tanlash: viloyat → tuman → maktab (select, matn emas) ----

def _v2_regions_kb(regions: List[str]) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    for r in _dedupe_keep_order(regions)[:60]:
        rr = str(r)[:50]
        kb.insert(types.InlineKeyboardButton(rr, callback_data=f"v2rgn:{rr}"))
    return kb


def _v2_districts_kb(districts: List[str], lang: str = "uz") -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    for d in _dedupe_keep_order(districts)[:80]:
        dd = str(d)[:50]
        kb.add(types.InlineKeyboardButton(dd, callback_data=f"v2dist:{dd}"))
    kb.row(types.InlineKeyboardButton(v2_tr(lang, "back_btn"), callback_data="v2back:region"))
    return kb


def _v2_schools_kb(schools: List[Dict[str, Any]], page: int = 0, lang: str = "uz") -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    schools = schools or []
    pages = max(1, (len(schools) + SCHOOLS_PAGE_SIZE - 1) // SCHOOLS_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    start = page * SCHOOLS_PAGE_SIZE
    for s in schools[start:start + SCHOOLS_PAGE_SIZE]:
        code = str(s.get("code") or "")
        name = str(s.get("name") or code)
        if not code:
            continue
        kb.insert(types.InlineKeyboardButton(name[:32], callback_data=f"v2sch:{code}"))
    nav = _schools_nav_row(page, len(schools), "v2schpage:")
    if nav:
        kb.row(*nav)
    kb.row(types.InlineKeyboardButton(v2_tr(lang, "back_btn"), callback_data="v2back:district"))
    return kb


async def _v2_ask_region(message: types.Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("exam_lang") or "uz"
    wait = await message.answer(v2_tr(lang, "please_wait"))
    await _v2_track(state, wait.message_id)
    res = await fetch_regions()
    regions = (res.get("regions") or []) if res.get("ok") else []
    if not regions:
        # Fallback: ro'yxat olinmasa — maktab kodini qo'lda
        await OnlineV2.school_code.set()
        try:
            await wait.edit_text(v2_tr(lang, "enter_school_code"))
        except Exception:
            sent = await message.answer(v2_tr(lang, "enter_school_code"))
            await _v2_track(state, sent.message_id)
        return
    await state.update_data(v2_regions=regions)
    await OnlineV2.region.set()
    try:
        await wait.edit_text(v2_tr(lang, "choose_region"), reply_markup=_v2_regions_kb(regions))
    except Exception:
        sent = await message.answer(v2_tr(lang, "choose_region"), reply_markup=_v2_regions_kb(regions))
        await _v2_track(state, sent.message_id)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("v2rgn:"), state=OnlineV2.region)
async def v2_pick_region(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    lang = data.get("exam_lang") or "uz"
    region = call.data.split(":", 1)[1]
    try:
        await call.message.edit_text(v2_tr(lang, "please_wait"))
    except Exception:
        pass
    res = await fetch_districts(region)
    districts = (res.get("districts") or []) if res.get("ok") else []
    if not districts:
        await OnlineV2.school_code.set()
        await call.message.answer(v2_tr(lang, "no_districts"))
        return
    await state.update_data(v2_region=region)
    await OnlineV2.district.set()
    try:
        await call.message.edit_text(
            v2_tr(lang, "region_label").format(region),
            parse_mode="HTML",
            reply_markup=_v2_districts_kb(districts, lang),
        )
    except Exception:
        await call.message.answer(v2_tr(lang, "choose_district"), reply_markup=_v2_districts_kb(districts, lang))


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("v2dist:"), state=OnlineV2.district)
async def v2_pick_district(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    district = call.data.split(":", 1)[1]
    data = await state.get_data()
    lang = data.get("exam_lang") or "uz"
    try:
        await call.message.edit_text(v2_tr(lang, "please_wait"))
    except Exception:
        pass
    region = data.get("v2_region") or ""
    res = await fetch_schools(region, district)
    schools = (res.get("schools") or []) if res.get("ok") else []
    if not schools:
        await OnlineV2.school_code.set()
        await call.message.answer(v2_tr(lang, "no_schools"))
        return
    await state.update_data(v2_district=district, v2_schools=schools)
    await OnlineV2.school.set()
    try:
        await call.message.edit_text(
            v2_tr(lang, "district_label").format(district),
            parse_mode="HTML",
            reply_markup=_v2_schools_kb(schools, lang=lang),
        )
    except Exception:
        await call.message.answer(v2_tr(lang, "choose_school"), reply_markup=_v2_schools_kb(schools, lang=lang))


@dp.callback_query_handler(lambda c: c.data == "v2back:region", state=[OnlineV2.district, OnlineV2.school])
async def v2_back_to_region(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    lang = data.get("exam_lang") or "uz"
    regions = data.get("v2_regions") or []
    await OnlineV2.region.set()
    try:
        await call.message.edit_text(v2_tr(lang, "choose_region"), reply_markup=_v2_regions_kb(regions))
    except Exception:
        await call.message.answer(v2_tr(lang, "choose_region"), reply_markup=_v2_regions_kb(regions))


@dp.callback_query_handler(lambda c: c.data == "v2back:district", state=OnlineV2.school)
async def v2_back_to_district(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    lang = data.get("exam_lang") or "uz"
    try:
        await call.message.edit_text(v2_tr(lang, "please_wait"))
    except Exception:
        pass
    region = data.get("v2_region") or ""
    res = await fetch_districts(region)
    districts = (res.get("districts") or []) if res.get("ok") else []
    await OnlineV2.district.set()
    try:
        await call.message.edit_text(
            v2_tr(lang, "region_label").format(region),
            parse_mode="HTML",
            reply_markup=_v2_districts_kb(districts, lang),
        )
    except Exception:
        await call.message.answer(v2_tr(lang, "choose_district"), reply_markup=_v2_districts_kb(districts, lang))


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("v2schpage:"), state=OnlineV2.school)
async def v2_school_page(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    page = _safe_int(call.data.split(":", 1)[1], 0)
    schools = data.get("v2_schools") or []
    lang = data.get("exam_lang") or "uz"
    try:
        await call.message.edit_reply_markup(reply_markup=_v2_schools_kb(schools, page=page, lang=lang))
    except Exception:
        pass


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("v2sch:"), state=OnlineV2.school)
async def v2_pick_school(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    code = call.data.split(":", 1)[1]
    await state.update_data(school_code=code)
    await _v2_ask_gender(call.message, state)


@dp.message_handler(state=OnlineV2.school_code)
async def v2_get_school_code(message: types.Message, state: FSMContext):
    if await _restart_if_start(message, state):
        return
    # Fallback: cascade ishlamasa maktab kodini qo'lda kiritish
    await _v2_track(state, message.message_id)
    data = await state.get_data()
    lang = data.get("exam_lang") or "uz"
    school = (message.text or "").strip()
    if not school:
        await _v2_say(message, state, v2_tr(lang, "enter_school_code"))
        return
    await state.update_data(school_code=school)
    await _v2_ask_gender(message, state)


async def _v2_ask_gender(message: types.Message, state: FSMContext) -> None:
    # Oxirgi qadam: jins tanlash (inline)
    data = await state.get_data()
    lang = data.get("exam_lang") or "uz"
    await OnlineV2.gender.set()
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(v2_tr(lang, "gender_male"), callback_data="v2gender:male"),
        types.InlineKeyboardButton(v2_tr(lang, "gender_female"), callback_data="v2gender:female"),
    )
    try:
        await message.edit_text(v2_tr(lang, "choose_gender"), reply_markup=kb)
    except Exception:
        sent = await message.answer(v2_tr(lang, "choose_gender"), reply_markup=kb)
        await _v2_track(state, sent.message_id)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("v2gender:"), state=OnlineV2.gender)
async def v2_pick_gender(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    gender = call.data.split(":", 1)[1]
    if gender not in ("male", "female"):
        gender = "male"
    await state.update_data(gender=gender)
    data = await state.get_data()
    lang = data.get("exam_lang") or "uz"
    try:
        await call.message.edit_text(v2_tr(lang, "please_wait"))
    except Exception:
        pass
    code = data.get("school_code") or ""
    result = await _v2_finish(call.message, state, code)
    if result == "bad_school":
        await OnlineV2.school_code.set()
        await _v2_say(call.message, state, v2_tr(lang, "school_not_found"))


async def _v2_finish(message: types.Message, state: FSMContext, school_code: str) -> Optional[str]:
    """v2/complete chaqiradi va natijani yuboradi.
    Maktab kodi noto'g'ri bo'lsa 'bad_school' qaytaradi (state saqlanadi);
    aks holda natija yuboriladi yoki xato beriladi, state finish qilinadi."""
    data = await state.get_data()
    res = await _v2_api_post("/dtm/online/v2/complete", {
        "bot_id": str(message.chat.id),
        "full_name": data.get("full_name"),
        "phone": data.get("phone"),
        "school_code": school_code,
        "gender": data.get("gender"),
        "language": data.get("exam_lang") or "uz",
    })

    lang = data.get("exam_lang") or "uz"
    if not res.get("ok"):
        txt = str(res.get("text") or "")
        status = res.get("status")
        if status == 400 and "school" in txt.lower():
            return "bad_school"
        await state.finish()
        if status == 404:
            await message.answer(v2_tr(lang, "test_not_found"))
        else:
            await message.answer(v2_tr(lang, "result_error").format(status))
        return None

    d = res.get("data") or {}
    first_label = data.get("first_subject_name") or "1-fan"
    second_label = data.get("second_subject_name") or "2-fan"
    # Oraliq xabarlarni (form/cascade prompt + user javoblari) o'chiramiz
    await _v2_cleanup(message.bot, message.chat.id, state)

    # Admin guruhiga ro'yxat xabari (v1 format — V2_FOR_ALL'da ham bo'lsin)
    chat = message.chat
    uname = f"@{chat.username}" if chat.username else (chat.full_name or chat.first_name or "-")
    user_link = f'<a href="tg://user?id={chat.id}">{uname}</a>'
    register_view = {
        "phone": data.get("phone"),
        "region": data.get("v2_region"),
        "district": data.get("v2_district"),
        "school_type": None,
        "school_code": school_code,
        "class_letter": None,
        "exam_lang": data.get("exam_lang") or "uz",
        "language": data.get("exam_lang") or "uz",
        "gender": data.get("gender"),
        "first_subject_id": data.get("first_subject_id"),
        "first_subject_uz": data.get("first_subject_name"),
        "second_subject_id": data.get("second_subject_id"),
        "second_subject_uz": data.get("second_subject_name"),
    }
    await notify_admins(message.bot, (
        f"🧾 <b>REGISTER SUCCESS (V2 PROMO)</b> · 🟢 ONLINE\n"
        f"🕒 <b>Time:</b> {now_str()}\n"
        f"👤 <b>User:</b> {user_link}\n"
        f"🆔 <b>Chat ID:</b> <code>{chat.id}</code>\n"
        f"📝 <b>Full name:</b> <code>{data.get('full_name','-')}</code>\n\n"
        f"{build_register_details(register_view)}\n"
        f"📊 <b>Ball:</b> <code>{d.get('total_ball','-')}</code>"
    ))

    await state.finish()

    def _ball(v: Any) -> str:
        return "-" if v in (None, "") else str(v)

    # DTM standart max: majburiy 33, asosiy 93, ikkinchi 63
    await message.answer(
        v2_tr(lang, "result_header") + "\n\n"
        "<blockquote>"
        + v2_tr(lang, "result_mandatory").format(_ball(d.get("mandatory_ball"))) + "\n"
        f"- {first_label}: {_ball(d.get('primary_ball'))} / 93\n"
        f"- {second_label}: {_ball(d.get('secondary_ball'))} / 63"
        "</blockquote>\n\n"
        + v2_tr(lang, "result_total").format(_ball(d.get("total_ball"))),
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )

    # Test natijasi PDF
    await _v2_send_pdf_button(message, d)

    # mentalaba offline-test-results'ga natijani yuboramiz (saqlash uchun, sertifikat userga yuborilmaydi).
    try:
        from data.config import ADMISSION_YEAR

        def _num(v: Any) -> float:
            try:
                return float(v)
            except (TypeError, ValueError):
                return 0.0

        school_name = school_code
        for s in (data.get("v2_schools") or []):
            if str(s.get("code") or "").strip() == str(school_code).strip():
                school_name = s.get("name") or school_code
                break

        await create_offline_test_result({
            "full_name": data.get("full_name") or "",
            "phone": data.get("phone") or "",
            "school": school_name,
            "primary_subject": first_label,
            "secondary_subject": second_label,
            "primary_subject_score": _num(d.get("primary_ball")),
            "secondary_subject_score": _num(d.get("secondary_ball")),
            "mandatory_subject_score": _num(d.get("mandatory_ball")),
            "total_score": _num(d.get("total_ball")),
            "admission_year": str(ADMISSION_YEAR),
        })
    except Exception as e:
        logger.error(f"[mentalaba] offline-test-result yuborishda xato: {e}")

    # PDF botdan yuborilmaydi — backend worker to'liq natija PDF'ini avtomatik
    # yuboradi (doc §5). Dublikat bo'lmasligi uchun bot tugma/fayl yubormaydi.
    return None


def test_type_kb(ui_lang: str = "uz", user_id: Optional[int] = None) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(text=tr(ui_lang, "btn_offline_test"), callback_data="test_type_offline"),
        types.InlineKeyboardButton(
            text=tr(ui_lang, "btn_online_test"),
            web_app=types.WebAppInfo(url=online_test_url(user_id)),
        ),
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
        # Offline (bot orqali) tugmasi vaqtincha yashirildi.
        # types.InlineKeyboardButton(
        #     text=f"{TEXTS['btn_offline_test']['uz']} / {TEXTS['btn_offline_test']['ru']}",
        #     callback_data="pre_choose_offline",
        # ),
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


def online_ready_kb(ui_lang: str = "uz", user_id: Optional[int] = None) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            text=tr(ui_lang, "btn_start_online_test"),
            web_app=types.WebAppInfo(url=online_test_url(user_id)),
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
        reply_markup=online_ready_kb(ui_lang, user_id=user_id),
    )


async def _show_online_ready(target_message: types.Message, user_id: int, ui_lang: str = "uz"):
    await target_message.bot.send_message(
        target_message.chat.id,
        tr(ui_lang, "online_ready"),
        parse_mode="HTML",
        reply_markup=online_ready_kb(ui_lang, user_id=user_id),
    )


# ----------------------------
# Subscribe check
# ----------------------------
_SUB_OK_STATUSES = ("creator", "administrator", "member")


async def check_subscriptions(user_id: int, bot) -> list:
    """Admin panelda faol qilingan har bir majburiy kanalni tekshiradi.
    Qaytadi: a'zo bo'lmagan kanallar ro'yxati (bo'sh [] — hammasiga a'zo yoki
    majburiy kanal umuman yo'q)."""
    me = await bot.get_me()
    channels = await fetch_active_subscriptions(bot_username=me.username)
    if not channels:
        return []

    not_joined = []
    for ch in channels:
        cid = ch.get("channel_id")
        try:
            member = await bot.get_chat_member(cid, user_id)
            status = member.status
        except Exception:
            status = "left"
        if status not in _SUB_OK_STATUSES:
            not_joined.append(ch)
    return not_joined



# ----------------------------
# Handlers
# ----------------------------
@dp.message_handler(CommandStart(), state="*")
async def start_cmd(message: types.Message, state: FSMContext):
    # Avval oldingi flow ning bot xabarlarini o'chiramiz, keyin state ni reset qilamiz
    await cleanup_bot_messages(message.bot, message.chat.id, state)
    await _v2_cleanup(message.bot, message.chat.id, state)  # v2 oqim oraliq xabarlari
    await state.finish()

    # Doimiy pastki menyu (reply keyboard) /start bosilishi bilan darhol
    # faollashadi — flow qaysi bo'lishidan qat'i nazar. Xabarni o'chirib
    # yubormaymiz — Telegram'da xabar o'chsa, u bilan birga reply keyboard
    # ham yo'qolib qoladi. Keyingi /start'da cleanup_bot_messages o'zi
    # tozalab, yangisini qo'yadi.
    from data.config import ADMINS
    from keyboards.default.userKeyboard import adminKeyboard_user
    menu_kb = adminKeyboard_user if str(message.from_user.id) in ADMINS else keyboard_user
    menu_msg = await message.answer("👋 Botga xush kelibsiz!", reply_markup=menu_kb)
    await state.update_data(bot_msg_ids=[menu_msg.message_id])

    # v2 (reklama) oqim: V2_FOR_ALL=true bo'lsa hamma uchun, aks holda faqat
    # /start v2 deep-link'da. Kanal obunasi va v1 registratsiya FSM yo'q.
    if V2_FOR_ALL or (message.get_args() or "").strip().lower() == "v2":
        await on_start_v2(message, state)
        return

    # Queue workerlarni ishga tushiramiz (1 marta)
    await ensure_register_workers(message.bot, workers=2)

    # 1. Majburiy obunani tekshiramiz
    not_joined = await check_subscriptions(message.from_user.id, message.bot)
    if not_joined:
        await message.answer(
            "Botdan foydalanish uchun rasmiy kanalimizga a'zo bo'ling! ✅",
            reply_markup=sub_kb(not_joined)
        )
        return

    # 2. Offline o'chirilgan — chooser ko'rsatishning hojati yo'q. Darhol
    # online flow'ga o'tkazamiz: ro'yxatdan o'tgan bo'lsa, greeting; yo'q
    # bo'lsa, registratsiya FSM.
    await _start_online_flow_from_message(message, state)


async def _start_online_flow_from_message(message: types.Message, state: FSMContext):
    intent = "online"
    user_id = message.from_user.id

    if check_user_exists_by_type(user_id, intent):
        await set_user_intent(user_id, intent)
        await _show_online_greeting(message, user_id, ui_lang="uz")
        return

    await state.update_data(test_intent=intent)
    res = await get_dtm_result(user_id)
    show_btn = bool(extract_dtm_result_data(res))
    await send_clean(
        message, state,
        f"{TEXTS['choose_ui_lang']['uz']} / {TEXTS['choose_ui_lang']['ru']}",
        reply_markup=ui_lang_kb(show_result_btn=bool(show_btn)),
    )
    await Registration.ui_lang.set()

_OFFLINE_DISABLED_NOTICE = "Offline test vaqtincha o'chirilgan. Iltimos, online testdan foydalaning."


@dp.callback_query_handler(lambda c: c.data == "test_type_offline", state="*")
async def test_type_offline_cb(call: types.CallbackQuery, state: FSMContext):
    try:
        await call.answer(_OFFLINE_DISABLED_NOTICE, show_alert=True)
    except Exception:
        pass
    await show_pre_register_test_type(call.message, state)


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
    try:
        await call.answer()
    except Exception:
        pass
    # Eski tracked xabarlarni o'chiramiz, so'ng FSM ni reset qilamiz
    await cleanup_bot_messages(call.bot, call.message.chat.id, state)
    await state.finish()

    intent = normalize_test_type(intent)

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
    # Offline flow o'chirilgan — eski cached tugmalarni bossa, online'ga
    # yo'naltiramiz va alert bilan xabar qilamiz.
    try:
        await call.answer(_OFFLINE_DISABLED_NOTICE, show_alert=True)
    except Exception:
        pass
    await _start_registration_with_intent(call, state, "online")


@dp.callback_query_handler(lambda c: c.data == "pre_choose_online", state="*")
async def pre_choose_online_cb(call: types.CallbackQuery, state: FSMContext):
    await _start_registration_with_intent(call, state, "online")


@dp.callback_query_handler(lambda c: c.data == "check_sub", state="*")
async def check_sub(call: types.CallbackQuery, state: FSMContext):
    not_joined = await check_subscriptions(call.from_user.id, call.bot)
    if not_joined:
        await call.answer("Hali obuna emassiz. Avval obuna bo’ling ✅", show_alert=True)
        return

    await call.answer("✅ Obuna tasdiqlandi")

    # Offline o’chirilgan: obunadan keyin darhol online flow’ga o’tkazamiz.
    try:
        await call.message.delete()
    except Exception:
        pass
    await _start_online_flow_from_message(call.message, state)


@dp.callback_query_handler(lambda c: c.data == "check_sub_v2", state="*")
async def check_sub_v2(call: types.CallbackQuery, state: FSMContext):
    not_joined = await check_subscriptions(call.from_user.id, call.bot)
    if not_joined:
        await call.answer("Hali obuna emassiz. Avval obuna bo’ling ✅", show_alert=True)
        return

    await call.answer("✅ Obuna tasdiqlandi")
    try:
        await call.message.delete()
    except Exception:
        pass
    await on_start_v2(call.message, state)


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
        tr(ui_lang, "flow_choose"),
        reply_markup=flow_choice_kb(ui_lang),
        disable_web_page_preview=True
    )
    await state.update_data(bot_msg_ids=[msg.message_id])
    await Registration.flow_choice.set()


@dp.callback_query_handler(lambda c: c.data == "flow:test", state=Registration.flow_choice)
async def pick_flow_test(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

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


@dp.callback_query_handler(lambda c: c.data == "flow:mandat", state=Registration.flow_choice)
async def pick_flow_mandat(call: types.CallbackQuery, state: FSMContext):
    await call.answer()

    await cleanup_bot_messages(call.bot, call.message.chat.id, state, except_ids={call.message.message_id})
    try:
        await call.message.delete()
    except Exception:
        pass

    await state.finish()
    await call.bot.send_message(call.message.chat.id, MANDAT_ASK_ID_TEXT, parse_mode="HTML")
    await MandatResult.waiting_id.set()

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
    if await _restart_if_start(message, state):
        return
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
    if await _restart_if_start(message, state):
        return
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

    # Tuman tanlangach — ta'lim turi tanlash chooser'i ochiladi.
    # "📋 Barchasini ko'rsatish" tugmasi ham bor — backend'da litsey/texnikum
    # data hali yuklanmagan bo'lsa ham foydalanuvchi maktabini topa oladi.
    await edit_clean(
        call, state,
        tr(ui_lang, "school_type_ask"),
        reply_markup=school_type_kb(ui_lang, show_all_fallback=True),
    )
    await Registration.school_type.set()


@dp.callback_query_handler(lambda c: c.data.startswith("reg_school_type:"), state=Registration.school_type)
async def reg_pick_school_type(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    raw = call.data.split(":", 1)[1].strip().lower()
    school_type = None if raw == "any" else normalize_school_type(raw)
    await state.update_data(school_type=school_type)

    region = data.get("region")
    district = data.get("district")
    res = await fetch_schools(region=region, district=district, school_type=school_type)
    if not (isinstance(res, dict) and res.get("ok")):
        await edit_clean(call, state, pretty_register_error(str(res), ui_lang), reply_markup=None)
        return

    schools = res.get("schools") or []
    if not schools:
        # Bu turdagi maktab topilmadi — chooser'ni "Barchasini ko'rsatish"
        # tugmasi bilan qaytaramiz, foydalanuvchi qutulishi mumkin.
        await edit_clean(
            call, state,
            tr(ui_lang, "schools_not_found"),
            reply_markup=school_type_kb(ui_lang, show_all_fallback=True),
        )
        return

    school_map = {}
    schools_full = []
    for s in schools:
        code = str(s.get("code") or "")
        name = str(s.get("name") or code)
        if code:
            school_map[code] = name
            schools_full.append({"code": code, "name": name})
    await state.update_data(
        school_map=school_map,
        schools_full=schools_full,
        school_view=schools_full,
        school_kb_opts={"back_to": "school_type"},
    )

    await edit_clean(
        call, state,
        tr(ui_lang, "school_pick_ask"),
        reply_markup=schools_kb(ui_lang, schools_full, back_to="school_type"),
    )
    await Registration.school.set()


@dp.callback_query_handler(lambda c: c.data == "reg_school_search", state=[Registration.school, Registration.school_search])
async def reg_school_search_prompt(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")
    msg = await call.bot.send_message(
        call.message.chat.id,
        tr(ui_lang, "school_search_ask"),
        parse_mode="HTML",
    )
    await state.update_data(bot_msg_ids=[msg.message_id])
    await Registration.school_search.set()


@dp.callback_query_handler(lambda c: c.data == "reg_school_show_all", state=[Registration.school, Registration.school_search])
async def reg_school_show_all(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")
    schools_full = data.get("schools_full") or []
    if not schools_full:
        await edit_clean(call, state, tr(ui_lang, "schools_not_found"), reply_markup=None)
        return
    await state.update_data(school_view=schools_full, school_kb_opts={})
    await edit_clean(
        call, state,
        tr(ui_lang, "school_pick_ask"),
        reply_markup=schools_kb(ui_lang, schools_full),
    )
    await Registration.school.set()


async def _handle_school_search_text(message: types.Message, state: FSMContext) -> None:
    """Real-time qidiruv: user school step'da yozgan har matn search query sifatida ishlaydi."""
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")
    query = (message.text or "").strip()

    if len(_norm_search(query)) < 2:
        await message.answer(tr(ui_lang, "school_search_too_short"))
        return

    schools_full = data.get("schools_full") or []
    matches = filter_schools_by_query(query, schools_full, limit=300)

    if not matches:
        await state.update_data(school_view=[], school_kb_opts={"show_search": False, "show_back_to_full": True})
        await message.answer(
            tr(ui_lang, "school_search_no_match"),
            reply_markup=schools_kb(ui_lang, [], show_search=False, show_back_to_full=True),
        )
        await Registration.school.set()
        return

    await state.update_data(school_view=matches, school_kb_opts={"show_search": False, "show_back_to_full": True})
    await message.answer(
        tr(ui_lang, "school_search_results"),
        reply_markup=schools_kb(ui_lang, matches, show_search=False, show_back_to_full=True),
    )
    await Registration.school.set()


async def _pick_school_by_code(message: types.Message, state: FSMContext, school_code: str) -> bool:
    """Inline natija bossanga, message_text ichidagi marker'dan school_code'ni
    olib FSM'ga qo'yamiz va class_letter step'ga o'tamiz."""
    school_code = (school_code or "").strip()
    if not school_code:
        return False

    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")
    schools_full = data.get("schools_full") or []

    school_name = school_code
    for s in schools_full:
        if str(s.get("code") or "").strip() == school_code:
            school_name = s.get("name") or school_code
            break

    await state.update_data(school_code=school_code, school_name=school_name)
    await message.answer(
        f"✅ Maktab tanlandi: {school_name}" if ui_lang == "uz" else f"✅ Школа выбрана: {school_name}",
    )
    msg = await message.answer(
        tr(ui_lang, "class_letter_ask"),
        reply_markup=class_letter_kb(ui_lang),
        disable_web_page_preview=True,
    )
    await state.update_data(bot_msg_ids=[msg.message_id])
    await Registration.class_letter.set()
    return True


def _extract_inline_school_code(text: str) -> Optional[str]:
    """Inline natija card'idan school_code'ni topish.

    Yangi card format'i: oxirgi qatorda `🏷 CODE` (yoki `🏷 <code>CODE</code>`
    render bo'lgan).
    Eski format (backward compat): `##sch##:CODE` marker.
    """
    if not text:
        return None
    m = re.search(r"🏷\s+([A-Za-z0-9_\-]{2,})\s*$", text, flags=re.MULTILINE)
    if m:
        return m.group(1)
    m = re.search(rf"{re.escape(INLINE_PICK_PREFIX)}([A-Za-z0-9_\-]+)", text)
    if m:
        return m.group(1)
    return None


@dp.message_handler(
    state=[Registration.school, Registration.school_search],
    content_types=types.ContentType.TEXT,
)
async def reg_school_search_input(message: types.Message, state: FSMContext):
    if await _restart_if_start(message, state):
        return
    text = message.text or ""

    # Inline natija orqali kelgan xabar (via_bot bilan keladi)? Code'ni
    # ajratib olib darhol school'ni pick qilamiz.
    inline_code = _extract_inline_school_code(text)
    if inline_code or message.via_bot:
        code = inline_code or _extract_inline_school_code(text)
        if code and await _pick_school_by_code(message, state, code):
            return

    await _handle_school_search_text(message, state)


# ---- Inline mode: real-time school search ----------------------------------
@dp.inline_handler(state="*")
async def inline_school_search(query: InlineQuery):
    """
    User chat'da `@bot <so'rov>` yozadi → har keystroke'da bu handler
    chaqiriladi → schools_full ichidan filter qilingan natijalarni card
    sifatida qaytaradi. User card'ni bosa, message_text bot'ga yuboriladi
    va INLINE_PICK_PREFIX orqali school_code aniqlanadi.
    """
    text = (query.query or "").strip()
    user_id = query.from_user.id

    logger.info(f"[inline_school_search] received query from user_id={user_id} text={text!r}")

    try:
        state = dp.current_state(chat=user_id, user=user_id)
        data = await state.get_data()
    except Exception as e:
        logger.exception(f"[inline_school_search] state load failed: {e}")
        data = {}

    schools_full: List[Dict[str, Any]] = data.get("schools_full") or []
    ui_lang = data.get("ui_lang", "uz")

    logger.info(f"[inline_school_search] schools_full={len(schools_full)} ui_lang={ui_lang}")

    if not schools_full:
        msg = (
            "Avval botda /start bosing va Viloyat → Tuman → Ta'lim turini tanlang."
            if ui_lang == "uz" else
            "Сначала откройте бота через /start и выберите Регион → Район → Тип учреждения."
        )
        try:
            await query.answer(
                results=[],
                cache_time=1,
                is_personal=True,
                switch_pm_text=msg[:64],
                switch_pm_parameter="start",
            )
        except Exception as e:
            logger.exception(f"[inline_school_search] empty answer failed: {e}")
        return

    if len(_norm_search(text)) < 1:
        matches = schools_full[:30]
    else:
        matches = filter_schools_by_query(text, schools_full, limit=30)

    logger.info(f"[inline_school_search] matches={len(matches)}")

    type_emoji = {"litsey": "🎓", "texnikum": "🔧", "school": "🏫"}
    type_label_uz = {"litsey": "Litsey", "texnikum": "Texnikum", "school": "Maktab"}

    # Telegram inline article card'da thumbnail maydoni mobile'da har doim
    # band bo'ladi — agar thumb_url berilmasa, default icon chiqadi. Bizning
    # card kerakli ma'lumotni title/description'da ko'rsatadi va thumbnail
    # ortiqcha — shu sababli 1x1 shaffof rasm uzatamiz (placeholder o'rniga
    # ko'rinmas joy qoladi).
    TRANSPARENT_THUMB = "https://www.google.com/images/cleardot.gif"

    results: List[InlineQueryResultArticle] = []
    for s in matches:
        code = str(s.get("code") or "").strip()
        name = str(s.get("name") or code).strip()
        region = str(s.get("region") or "").strip()
        district = str(s.get("district") or "").strip()
        stype = normalize_school_type(s.get("type"))
        if not code:
            continue

        emoji = type_emoji.get(stype, "🏫")
        type_label = type_label_uz.get(stype, "Maktab")

        # Description: location + type. Telegram card'da bitta qator
        # ostida ko'rinadi, qisqa va tabiiy.
        loc = " · ".join(p for p in (region, district) if p)
        descr_line = f"{loc} · {type_label}" if loc else type_label

        title = f"{emoji} {name}"

        # User card'ni bossanga, bot chat'iga shu format jo'natiladi —
        # toza, ko'ringan kelishimli. Oxiridagi `🏷 <code>...</code>`
        # qatori bot tomonidan school_code'ni parse qilish uchun marker.
        body_lines = [f"{emoji} <b>{html.escape(name)}</b>"]
        if region:
            body_lines.append(f"🌍 {html.escape(region)}")
        if district:
            body_lines.append(f"🏙 {html.escape(district)}")
        body_lines.append(f"📚 {html.escape(type_label)}")
        body_lines.append(f"🏷 <code>{html.escape(code)}</code>")
        body_text = "\n".join(body_lines)

        results.append(
            InlineQueryResultArticle(
                id=code[:64],
                title=title[:100],
                description=descr_line[:120],
                thumb_url=TRANSPARENT_THUMB,
                thumb_width=1,
                thumb_height=1,
                input_message_content=InputTextMessageContent(
                    message_text=body_text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                ),
            )
        )

    try:
        await query.answer(
            results=results,
            cache_time=1,
            is_personal=True,
        )
        logger.info(f"[inline_school_search] answered with {len(results)} results")
    except Exception as e:
        logger.exception(f"[inline_school_search] answer failed: {e}")


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("reg_school_page:"), state=[Registration.school, Registration.school_search])
async def reg_school_page(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")
    page = _safe_int(call.data.split(":", 1)[1], 0)
    view = data.get("school_view")
    if view is None:
        view = data.get("schools_full") or []
    opts = data.get("school_kb_opts") or {}
    try:
        await call.message.edit_reply_markup(
            reply_markup=schools_kb(ui_lang, view, page=page, **opts),
        )
    except Exception:
        pass


@dp.callback_query_handler(lambda c: c.data.startswith("reg_school:"), state=[Registration.school, Registration.school_search])
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

    if step == "school_type":
        await edit_clean(
            call, state,
            tr(ui_lang, "school_type_ask"),
            reply_markup=school_type_kb(ui_lang),
        )
        await Registration.school_type.set()
        return

    if step == "school":
        region = data.get("region")
        district = data.get("district")
        school_type = data.get("school_type")
        res = await fetch_schools(region=region, district=district, school_type=school_type)
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

        # Offline registratsiya o'chirilgan — eski FSM state'da test_intent=offline
        # qolgan userlar bo'lishi mumkin (offline tugma yashirilishidan oldin
        # registratsiyani boshlagan). Ularni majburan online'ga o'tkazamiz.
        if normalize_test_type(data.get("test_intent")) != "online":
            await state.update_data(test_intent="online")
            data = await state.get_data()

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
            test_type="online",
        )

        # ---- ONLINE: to’g’ridan API, queue kerak emas ----
        if normalize_test_type(data.get("test_intent")) == "online":
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
            f"🧾 <b>REGISTER QUEUED (BOT)</b> · {test_type_badge(payload.get('test_type'))}\n"
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
    intent = normalize_test_type(data.get("test_intent"))

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
        f"🧾 <b>REGISTER SUCCESS (BOT QUEUE)</b> · {_badge_from_payload(info.get('payload'))}\n"
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
            f"🧾 <b>REGISTER FAIL (BOT QUEUE)</b> · {_badge_from_payload(info.get('payload'))}\n"
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
    total_ball = data.get('total_ball', 0)
    subjects = data.get('subjects', []) or []

    # DTM standart max ball (pozitsiya bo'yicha): majburiy 33, 1-fan 93, 2-fan 63
    maxes = [33, 93, 63]

    def _clean_name(name: Any) -> str:
        # "24. Fizika" -> "Fizika" (oldidagi "raqam. " olib tashlanadi)
        return re.sub(r"^\s*\d+\.\s*", "", str(name or "")).strip()

    lines = []
    for i, s in enumerate(subjects):
        mx = maxes[i] if i < len(maxes) else s.get("allocated")
        lines.append(f"- {_clean_name(s.get('name'))}: {s.get('score')} / {mx}")

    msg = "<b>Test natijasi:</b>\n\n"
    if lines:
        msg += "<blockquote>" + "\n".join(lines) + "</blockquote>\n\n"
    msg += f"Jami: <b>{total_ball} ball</b>"
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
            formatted_text,
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


# ----------------------------
# Mandat natijasi (mandat.uzbmb.uz, abituriyent ID orqali)
# ----------------------------
MANDAT_ASK_ID_TEXT = (
    "🎓 <b>DTM imtihon natijasi</b>\n\n"
    "Abituriyent ID raqamingizni yuboring.\n"
    "Namuna: <code>1234567</code>"
)
MANDAT_INVALID_ID_TEXT = "❌ ID xato. Faqat raqamlardan iborat bo'lishi kerak.\nNamuna: <code>1234567</code>"
MANDAT_NOT_FOUND_TEXT = "❌ Bu ID bo'yicha natija topilmadi. ID raqamini tekshirib qayta yuboring."
MANDAT_ERROR_TEXT = "❌ Natijani olishda xatolik yuz berdi. Keyinroq qayta urinib ko'ring."


@dp.message_handler(Command("natijani_bilish"), state="*")
@dp.message_handler(Command("dtm_natija"), state="*")
@dp.message_handler(Text(equals="🎓 Natijani bilish"), state="*")
@dp.message_handler(Text(equals="🎓 DTM natija"), state="*")
async def mandat_result_entry(message: types.Message, state: FSMContext):
    await state.finish()
    not_joined = await check_subscriptions(message.from_user.id, message.bot)
    if not_joined:
        await message.answer(
            "Botdan foydalanish uchun rasmiy kanalimizga a'zo bo'ling! ✅",
            reply_markup=sub_kb(not_joined, check_callback="check_sub_mandat"),
        )
        return

    await message.answer(MANDAT_ASK_ID_TEXT, parse_mode="HTML")
    await MandatResult.waiting_id.set()


@dp.callback_query_handler(lambda c: c.data == "check_sub_mandat", state="*")
async def mandat_check_sub_cb(call: types.CallbackQuery, state: FSMContext):
    not_joined = await check_subscriptions(call.from_user.id, call.bot)
    if not_joined:
        await call.answer("Hali obuna emassiz. Avval obuna bo’ling ✅", show_alert=True)
        return

    await call.answer("✅ Obuna tasdiqlandi")
    try:
        await call.message.delete()
    except Exception:
        pass

    await call.bot.send_message(call.message.chat.id, MANDAT_ASK_ID_TEXT, parse_mode="HTML")
    await MandatResult.waiting_id.set()


@dp.message_handler(state=MandatResult.waiting_id)
async def mandat_receive_id(message: types.Message, state: FSMContext):
    entrant_id = (message.text or "").strip()

    if not is_valid_entrant_id(entrant_id):
        await message.answer(MANDAT_INVALID_ID_TEXT, parse_mode="HTML")
        return

    progress = None
    try:
        # Cache va API bilan ishlaydigan funksiyalar (lookup_cached_result,
        # fetch_mandat_result, save_result_to_cache) ichkarida xatolarni
        # o'zlari ushlab, throw qilmasdan qaytaradi — shu try/except esa
        # kutilmagan holatlar (masalan get_me/format/send xatosi) uchun
        # oxirgi himoya qatlami: bot handler ichida qulab tushmaydi.
        cached = await lookup_cached_result(entrant_id)
        if cached:
            me = await message.bot.get_me()
            text = format_mandat_result(cached, bot_username=me.username or "")
            await state.finish()
            await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
            return

        progress = await message.answer("⏳ Natija qidirilmoqda, biroz kuting...")

        res = await fetch_mandat_result(entrant_id)

        try:
            await progress.delete()
        except Exception:
            pass
        progress = None

        if not res.get("ok"):
            reason = res.get("reason")
            if reason == "not_found":
                await message.answer(MANDAT_NOT_FOUND_TEXT)
            else:
                logger.error(f"[mandat] fetch failed reason={reason} entrant_id={entrant_id}")
                await message.answer(MANDAT_ERROR_TEXT)
            return

        await save_result_to_cache(res["data"])

        me = await message.bot.get_me()
        text = format_mandat_result(res["data"], bot_username=me.username or "")

        await state.finish()
        await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"[mandat] unexpected error entrant_id={entrant_id}: {repr(e)}")
        if progress:
            try:
                await progress.delete()
            except Exception:
                pass
        try:
            await message.answer(MANDAT_ERROR_TEXT)
        except Exception:
            pass


@dp.message_handler(Command("export_excel"), state="*")
async def export_mandat_excel(message: types.Message, state: FSMContext):
    from data.config import ADMINS

    if str(message.from_user.id) not in ADMINS:
        return

    try:
        if not excel_file_exists():
            await message.answer("❌ Hali hech qanday natija yig'ilmagan.")
            return

        await message.answer_document(
            types.InputFile(EXCEL_PATH),
            caption="📊 Yig'ilgan DTM natijalari (mandat.uzbmb.uz)",
        )
    except Exception as e:
        logger.error(f"[mandat] export_excel error: {repr(e)}")
        await message.answer("❌ Excel faylni yuborishda xatolik yuz berdi.")


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
