import re
import json
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.builtin import CommandStart
from aiogram.types import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton

from loader import dp
from keyboards.default.userKeyboard import keyboard_user
from states.userStates import Registration
from data.config import SUBJECTS_MAP
from keyboards.inline.user_inline import language_keyboard_button, gender_kb

# ✅ NEW: register_job (queue/job)
from utils.send_req import register_job
from typing import Optional

PHONE_RE = re.compile(r"^\+?\d{9,15}$")
FULL_NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЎўҚқҒғҲҳЁёO‘o‘G‘g‘ʼ'\-\s]{5,}$")
from datetime import datetime
import asyncio
from data.config import ADMINS as ADMIN_IDS, ADMIN_CHAT_ID, CHANNEL_USERNAME,CHANNEL_LINK 
# ADMIN_IDS = [123456789]  # <-- admin chat_id larni yozing (list)
# ----------------------------
# i18n TEXTS (UI tili bo‘yicha)
# ----------------------------
TEXTS = {
    "choose_ui_lang": {"uz": "Tilni tanlang:", "ru": "Выберите язык:"},

    "phone_ask": {
        "uz": "Telefon raqamingizni yuboring yoki qo‘lda yozing.\n"
              "Namuna: 941234567 (yoki +998941234567)",
        "ru": "Отправьте номер телефона или введите вручную.\n"
              "Пример: 941234567 (или +998941234567)"
    },
    "phone_invalid": {
        "uz": "❌ Telefon xato.\nNamuna: 941234567 yoki +998941234567",
        "ru": "❌ Неверный номер.\nПример: 941234567 или +998941234567"
    },

    "fio_ask": {"uz": "FIO kiriting:\nNamuna: Ism Familiya", "ru": "Введите ФИО:\nПример: Имя Фамилия"},
    "fio_invalid_2words": {
        "uz": "❌ FIO xato.\nIltimos, Ism va Familiyani kiriting.\nMasalan: Ulug‘bek Erkinov",
        "ru": "❌ ФИО неверно.\nВведите Имя и Фамилию.\nПример: Ulug‘bek Erkinov"
    },
    "fio_invalid_letters": {
        "uz": "❌ FIO faqat harflardan iborat bo‘lishi kerak.\nMasalan: Ulug‘bek Erkinov",
        "ru": "❌ ФИО должно содержать только буквы.\nПример: Ulug‘bek Erkinov"
    },
    "ask_gender": {"uz": "Jinsini tanlang:", "ru": "Выберите пол:"},
    "gender_invalid": {"uz": "❌ Noto‘g‘ri tanlov.", "ru": "❌ Неверный выбор."},

    "fio_too_short": {
        "uz": "❌ Ism yoki familiya juda qisqa.\nQayta kiriting:",
        "ru": "❌ Имя или фамилия слишком короткие.\nВведите снова:"
    },
    "school_ask": {"uz": "Maktab kodini kiriting (masalan: YU132):", "ru": "Введите код школы (например: YU132):"},
    "school_invalid": {"uz": "❌ Maktab kodi xato. Qayta kiriting:", "ru": "❌ Код школы неверный. Введите снова:"},

    "exam_lang_ask": {"uz": "Imtihon tilini tanlang:", "ru": "Выберите язык экзамена:"},
    "pair_ask": {"uz": "Juftlikni tanlang:", "ru": "Выберите пару:"},
    "pair_not_found": {"uz": "❌ Fan topilmadi. Qayta tanlang.", "ru": "❌ Предмет не найден. Выберите снова."},
    "pair_not_allowed": {"uz": "❌ Bu juftlik ruxsat etilmagan. Qayta tanlang.", "ru": "❌ Эта пара не разрешена. Выберите снова."},

    "confirm_title": {"uz": "🧾 Ma'lumotlaringiz:\n\n", "ru": "🧾 Ваши данные:\n\n"},
    "confirm_question": {"uz": "Tasdiqlaysizmi?", "ru": "Подтверждаете?"},
    "cancelled": {
        "uz": "❌ Ro‘yxatdan o‘tish bekor qilindi.\n/start bosib qayta boshlashingiz mumkin.",
        "ru": "❌ Регистрация отменена.\nНажмите /start чтобы начать заново."
    },
    "loading": {
        "uz": "⏳ Iltimos, kuting... Siz uchun test savollari yaratilmoqda",
        "ru": "⏳ Подождите... Генерируем тестовые вопросы"
    },
    "success": {"uz": "✅ Ro‘yxatdan muvaffaqiyatli o‘tdingiz!", "ru": "✅ Регистрация прошла успешно!"},
    "edit_exam_lang": {"uz": "Imtihon tilini qayta tanlang:", "ru": "Выберите язык экзамена снова:"},
    "selected_exam_lang": {"uz": "✅ Tanlandi:", "ru": "✅ Выбрано:"},
}

def tr(ui_lang: str, key: str) -> str:
    return TEXTS.get(key, {}).get(ui_lang, TEXTS.get(key, {}).get("uz", ""))

def pretty_register_error(raw: str, ui_lang: str = "uz") -> str:
    """
    raw: exception str yoki API qaytargan text/json
    """
    # ichida json bo'lsa ajratib olamiz
    m = re.search(r"(\{.*\})", raw)
    detail = None

    if m:
        try:
            payload = json.loads(m.group(1))
            detail = payload.get("detail")
        except Exception:
            detail = None

    # Agar bu bizning queue/http res dict bo'lsa:
    # {"ok": False, "status": 400, "text": "..."}
    if raw.strip().startswith("{") and raw.strip().endswith("}"):
        try:
            p = json.loads(raw)
            if isinstance(p, dict) and "text" in p and "status" in p:
                raw = p.get("text") or raw
        except Exception:
            pass

    if not detail:
        return raw[:500]

    mapping = {
        "User already exists": {
            "uz": "🚫 Siz allaqachon ro‘yxatdan o‘tib bo‘lgansiz.\n🔁 /start bosib davom eting yoki @Mentalaba_help bilan bog‘laning.",
            "ru": "🚫 Вы уже зарегистрированы.\n🔁 Нажмите /start чтобы продолжить или свяжитесь с @Mentalaba_help."
        },
        "Invalid phone": {
            "uz": "📞 Telefon raqam noto‘g‘ri formatda.\nNamuna: 941234567 yoki +998941234567",
            "ru": "📞 Неверный формат номера.\nПример: 941234567 или +998941234567"
        },
    }

    if detail in mapping:
        return mapping[detail]["uz"] if ui_lang == "uz" else mapping[detail]["ru"]

    return (f"❌ Ошибка: {detail}" if ui_lang == "ru" else f"❌ Xatolik: {detail}")


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

            btn_text = f"{first_label} — {second_label}"
            kb.add(
                InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"pair:{first_id}|{second_id}",
                )
            )

    kb.add(InlineKeyboardButton("❌ Cancel" if ui_lang == "ru" else "❌ Bekor qilish", callback_data="reg_cancel"))
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

def is_phone_ok(text: str) -> bool:
    s = (text or "").strip().replace(" ", "").replace("-", "")
    if not s:
        return False
    if s.isdigit() and len(s) == 9:
        return True
    if s.isdigit() and len(s) == 12 and s.startswith("998"):
        return True
    return bool(PHONE_RE.match(s))

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton



def sub_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("✅ Kanalga obuna bo‘lish", url=CHANNEL_LINK))
    kb.add(InlineKeyboardButton("🔄 Tekshirish", callback_data="check_sub"))
    return kb

async def is_subscribed(user_id: int, bot) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        # member.status: "creator", "administrator", "member", "left", "kicked"
        return member.status in ("creator", "administrator", "member")
    except Exception:
        # bot admin bo'lmasa yoki kanal topilmasa shu yerga tushishi mumkin
        return False

# ----------------------------
# Handlers
# ----------------------------
@dp.message_handler(CommandStart(), state="*")
async def start_cmd(message: types.Message, state: FSMContext):
    await state.finish()

    ok = await is_subscribed(message.from_user.id, message.bot)
    if not ok:
        await message.answer(
            "Davom etish uchun kanalga majburiy obuna bo‘ling:\n"
            "Obuna bo‘lgach, 🔄 Tekshirish tugmasini bosing.",
            reply_markup=sub_kb()
        )
        return

    # ✅ Obuna bo'lsa — sizning hozirgi flow
    await message.answer(
        f"{TEXTS['choose_ui_lang']['uz']} / {TEXTS['choose_ui_lang']['ru']}",
        reply_markup=ui_lang_kb()
    )
    await Registration.ui_lang.set()

@dp.callback_query_handler(lambda c: c.data == "check_sub", state="*")
async def check_sub(call: types.CallbackQuery, state: FSMContext):
    # ok = await is_subscribed(call.from_user.id, call.bot)
    # if not ok:
    #     await call.answer("Hali obuna emassiz. Avval obuna bo‘ling ✅", show_alert=True)
    #     return

    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(
        f"{TEXTS['choose_ui_lang']['uz']} / {TEXTS['choose_ui_lang']['ru']}",
        reply_markup=ui_lang_kb()
    )
    await Registration.ui_lang.set()
    await call.answer("✅ Obuna tasdiqlandi")



@dp.callback_query_handler(lambda c: c.data == "reg_cancel", state="*")
async def reg_cancel(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await state.finish()
    txt = TEXTS["cancelled"]["uz"] + "\n\n" + TEXTS["cancelled"]["ru"]
    try:
        await call.message.edit_text(txt)
    except Exception:
        await call.message.answer(txt)


@dp.callback_query_handler(lambda c: c.data in ["ui:uz", "ui:ru"], state=Registration.ui_lang)
async def pick_ui_language(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    ui_lang = call.data.split(":", 1)[1]
    await state.update_data(ui_lang=ui_lang)

    await call.message.answer(tr(ui_lang, "phone_ask"), reply_markup=keyboard_user)
    await Registration.phone.set()


@dp.message_handler(content_types=types.ContentType.CONTACT, state=Registration.phone)
async def reg_phone_contact(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    phone = normalize_phone(message.contact.phone_number)
    await state.update_data(phone=phone)

    await message.answer(tr(ui_lang, "fio_ask"), reply_markup=ReplyKeyboardRemove())
    await Registration.fio.set()


@dp.message_handler(state=Registration.phone)
async def reg_phone_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    raw_phone = (message.text or "").strip()
    if not is_phone_ok(raw_phone):
        return await message.answer(tr(ui_lang, "phone_invalid"))

    phone = normalize_uz_phone(raw_phone)
    await state.update_data(phone=phone)

    await message.answer(tr(ui_lang, "fio_ask"), reply_markup=ReplyKeyboardRemove())
    await Registration.fio.set()


@dp.message_handler(state=Registration.fio)
async def reg_fio(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    fio = (message.text or "").strip()
    parts = fio.split()

    if len(parts) < 2:
        return await message.answer(tr(ui_lang, "fio_invalid_2words"))

    if not FULL_NAME_RE.match(fio):
        return await message.answer(tr(ui_lang, "fio_invalid_letters"))

    if any(len(p) < 2 for p in parts):
        return await message.answer(tr(ui_lang, "fio_too_short"))

    await state.update_data(fio=fio)
    await message.answer(tr(ui_lang, "ask_gender"), reply_markup=gender_kb(ui_lang))
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

    try:
        await call.message.edit_reply_markup()
    except Exception:
        pass

    await call.message.answer(tr(ui_lang, "school_ask"))
    await Registration.school_code.set()
    await call.answer()


@dp.message_handler(state=Registration.school_code)
async def reg_school(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    school_code = (message.text or "").strip().upper()
    if len(school_code) < 3:
        return await message.answer(tr(ui_lang, "school_invalid"))

    await state.update_data(school_code=school_code)

    await message.answer(tr(ui_lang, "exam_lang_ask"), reply_markup=language_keyboard_button)
    await Registration.exam_lang.set()


@dp.callback_query_handler(lambda c: c.data in ["uz", "ru"], state=Registration.exam_lang)
async def pick_exam_language(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    exam_lang = call.data
    await state.update_data(exam_lang=exam_lang)

    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    label = "🇺🇿 O‘zbekcha" if exam_lang == "uz" else "🇷🇺 Русский"
    try:
        await call.message.edit_text(f"{tr(ui_lang, 'selected_exam_lang')} {label}", reply_markup=None)
    except Exception:
        pass

    await call.message.answer(tr(ui_lang, "pair_ask"), reply_markup=pairs_kb(ui_lang=ui_lang))
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
        return await call.message.answer(tr(ui_lang, "pair_not_found"))

    # bu yerda pair_is_allowed first_uz second_uz bilan tekshiradi
    if not pair_is_allowed(first_uz, second_uz):
        return await call.message.answer(tr(ui_lang, "pair_not_allowed"))

    await state.update_data(
        first_subject_id=first_id,
        first_subject_uz=first_uz,
        first_subject_ru=first_ru,
        second_subject_id=second_id,
        second_subject_uz=second_uz,
        second_subject_ru=second_ru,
    )

    data = await state.get_data()
    exam_lang = data.get("exam_lang", "uz")

    first_label = data["first_subject_uz"] if ui_lang == "uz" else (data["first_subject_ru"] or data["first_subject_uz"])
    second_label = data["second_subject_uz"] if ui_lang == "uz" else (data["second_subject_ru"] or data["second_subject_uz"])

    exam_lang_label = (
        ("O‘zbekcha" if exam_lang == "uz" else "Ruscha")
        if ui_lang == "uz"
        else ("Узбекский" if exam_lang == "uz" else "Русский")
    )

    text = (
        tr(ui_lang, "confirm_title")
        + f"📞 Phone: {data['phone']}\n"
        + f"👤 FIO: {data['fio']}\n"
        + f"👥 Gender: {data['gender']}\n"
        + f"🏫 School code: {data['school_code']}\n"
        + (("🗣 Imtihon tili: " if ui_lang == "uz" else "🗣 Язык экзамена: ") + exam_lang_label + "\n")
        + (("📘 1-fan: " if ui_lang == "uz" else "📘 Предмет 1: ") + first_label + "\n")
        + (("📗 2-fan: " if ui_lang == "uz" else "📗 Предмет 2: ") + second_label + "\n\n")
        + tr(ui_lang, "confirm_question")
    )

    await call.message.edit_text(text, reply_markup=confirm_kb(ui_lang))
    await Registration.verify.set()



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
    except Exception:
        pass

def build_register_details(data: dict) -> str:
    phone = data.get("phone", "-")
    school_code = data.get("school_code", "-")
    exam_lang = data.get("exam_lang", data.get("language", "-"))
    gender = data.get("gender", "-")
    s1 = data.get("first_subject_id", "-")
    s2 = data.get("second_subject_id", "-")

    return (
        f"📞 <b>Phone:</b> <code>{phone}</code>\n"
        f"🏫 <b>School code:</b> <code>{school_code}</code>\n"
        f"🗣 <b>Exam lang:</b> <code>{exam_lang}</code>\n"
        f"🚻 <b>Gender:</b> <code>{gender}</code>\n"
        f"📚 <b>Subjects:</b> <code>{s1}</code> + <code>{s2}</code>"
    )

def admin_register_message(
    *,
    status: str,                 # "SUCCESS" / "FAIL"
    user: types.User,
    full_name: str,
    ok: bool,
    error: Optional[str] = None,
    details: Optional[str] = None
) -> str:
    t = now_str()
    user_link = _tg_user_link(user)

    text = (
        f"🧾 <b>REGISTER {status}</b>\n"
        f"🕒 <b>Time:</b> {t}\n"
        f"👤 <b>User:</b> {user_link}\n"
        f"🆔 <b>Chat ID:</b> <code>{user.id}</code>\n"
        f"📝 <b>Full name:</b> {full_name}\n"
        f"✅ <b>OK:</b> {'YES' if ok else 'NO'}"
    )

    if details:
        text += "\n\n" + details

    if error:
        err = str(error).strip()
        if len(err) > 1200:
            err = err[:1200] + "…"
        text += f"\n\n❗ <b>Error:</b>\n<code>{err}</code>"

    return text


@dp.callback_query_handler(lambda c: c.data in ["reg_confirm", "reg_edit"], state=Registration.verify)
async def reg_verify(call: types.CallbackQuery, state: FSMContext):
    await call.answer()

    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")

    if call.data == "reg_edit":
        await call.message.answer(tr(ui_lang, "edit_exam_lang"), reply_markup=language_keyboard_button)
        await Registration.exam_lang.set()
        return

    full_name = data.get("fio") or "-"
    details = build_register_details(data)

    # ✅ USER: darrov "ro'yhatdan o'tdingiz" (loader yo'q)
    # Muhim: bu optimistik xabar, agar backend fail bo'lsa keyin errorga almashtiramiz
    user_msg = await call.message.answer(tr(ui_lang, "success"))

    try:
        res = await register_job(
            bot_id=str(call.from_user.id),
            full_name=data["fio"],
            phone=data["phone"],
            school_code=data["school_code"],
            first_subject_id=data["first_subject_id"],
            second_subject_id=data["second_subject_id"],
            password="1111",
            language=data.get("exam_lang", "uz"),
            gender=data.get("gender", "male"),
        )

        # SUCCESS
        if isinstance(res, dict) and res.get("ok"):
            admin_text = admin_register_message(
                status="SUCCESS",
                user=call.from_user,
                full_name=full_name,
                ok=True,
                error=None,
                details=details
            )
            await notify_admins(call.bot, admin_text)

            await state.finish()
            return

        # FAIL (backend javobi)
        err_txt = None
        if isinstance(res, dict):
            err_txt = res.get("text") or res.get("raw") or str(res)
        else:
            err_txt = str(res)

        # ✅ USER: successni errorga almashtiramiz
        await user_msg.edit_text(pretty_register_error(err_txt, ui_lang=ui_lang))

        # ✅ ADMIN: fail + detail
        admin_text = admin_register_message(
            status="FAIL",
            user=call.from_user,
            full_name=full_name,
            ok=False,
            error=err_txt,
            details=details
        )
        await notify_admins(call.bot, admin_text)

    except Exception as e:
        # ✅ USER: successni errorga almashtiramiz
        await user_msg.edit_text(pretty_register_error(str(e), ui_lang=ui_lang))

        # ✅ ADMIN: exception fail + detail
        admin_text = admin_register_message(
            status="FAIL",
            user=call.from_user,
            full_name=full_name,
            ok=False,
            error=str(e),
            details=details
        )
        await notify_admins(call.bot, admin_text)