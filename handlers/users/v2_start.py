import re
import logging

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from loader import dp, bot
from states.v2States import V2Form
from data.config import CHANNEL_ADS_ID, CHANNEL_ADS_THREAD_ID

logger = logging.getLogger(__name__)

V2_COMPLETE_URL = "https://mentalaba.uz/application?degree=1&page=1"

_phone_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton("📞 Raqamni yuborish", request_contact=True)]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

_PHONE_RE = re.compile(r"^\+?\d{9,15}$")


def _normalize_phone(raw: str) -> str:
    s = raw.strip().replace(" ", "").replace("-", "")
    if s.isdigit() and len(s) == 9:
        return "+998" + s
    if s.isdigit() and len(s) == 12 and s.startswith("998"):
        return "+" + s
    return raw.strip() if raw.strip().startswith("+") else "+" + s


def _is_phone_ok(text: str) -> bool:
    s = (text or "").strip().replace(" ", "").replace("-", "")
    if s.isdigit() and len(s) == 9:
        return True
    if s.isdigit() and len(s) == 12 and s.startswith("998"):
        return True
    return bool(_PHONE_RE.match(s))


def _complete_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Mentalaba.uz", url=V2_COMPLETE_URL))
    return kb


async def start_v2_flow(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer(
        "🎓 Assalomu alaykum!\n\n"
        "Mentalaba orqali universitet kontrakt narxlarini solishtiring va o'zingizga mos OTMni toping.\n\n"
        "📲 Davom etish uchun telefon raqamingizni qoldiring va maxsus linkni oling 👇",
        reply_markup=_phone_kb,
    )
    await V2Form.phone.set()


@dp.message_handler(content_types=types.ContentType.CONTACT, state=V2Form.phone)
async def v2_phone_contact(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone
    await state.update_data(phone=phone)
    await message.answer(
        "Rahmat ✅\n\nEndi ismingizni yozib yuboring 👇",
        reply_markup=ReplyKeyboardRemove(),
    )
    await V2Form.fio.set()


@dp.message_handler(lambda m: not (m.text or "").startswith("/"), state=V2Form.phone)
async def v2_phone_text(message: types.Message, state: FSMContext):
    raw = (message.text or "").strip()
    if not _is_phone_ok(raw):
        await message.answer(
            "❌ Noto'g'ri raqam.\nNamuna: 941234567 yoki +998941234567"
        )
        return
    await state.update_data(phone=_normalize_phone(raw))
    await message.answer(
        "Rahmat ✅\n\nEndi ismingizni yozib yuboring 👇",
        reply_markup=ReplyKeyboardRemove(),
    )
    await V2Form.fio.set()


@dp.message_handler(lambda m: not (m.text or "").startswith("/"), state=V2Form.fio)
async def v2_fio(message: types.Message, state: FSMContext):
    fio = (message.text or "").strip()
    if len(fio) < 2:
        await message.answer("❌ Ismingizni kiriting:")
        return
    await state.update_data(fio=fio)
    parts = fio.split()
    ism = parts[0]
    await message.answer(
        f"Ajoyib, {ism} 👍\n\n"
        "Qaysi universitetga topshirishni rejalashtiryapsiz?\n\n"
        "✍️ Universitet nomini yozing\n(Misol: AIFU, TMC, TAFU)"
    )
    await V2Form.university.set()


@dp.message_handler(lambda m: not (m.text or "").startswith("/"), state=V2Form.university)
async def v2_university(message: types.Message, state: FSMContext):
    university = (message.text or "").strip()
    if not university:
        await message.answer("❌ OTM nomini kiriting:")
        return

    data = await state.get_data()
    phone = data.get("phone", "-")
    fio = data.get("fio", "-")
    user = message.from_user

    tg_link = (
        f"@{user.username}"
        if user.username
        else f'<a href="tg://user?id={user.id}">{user.full_name}</a>'
    )

    channel_text = (
        "📝 <b>Yangi ariza</b>\n\n"
        f"👤 <b>F.I.O:</b> <code>{fio}</code>\n"
        f"📞 <b>Telefon:</b> <code>{phone}</code>\n"
        f"🏛 <b>OTM:</b> <code>{university}</code>\n"
        f"🆔 <b>Telegram:</b> {tg_link}\n"
        f"🔢 <b>Chat ID:</b> <code>{user.id}</code>"
    )

    try:
        await bot.send_message(
            CHANNEL_ADS_ID,
            channel_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            message_thread_id=CHANNEL_ADS_THREAD_ID or None,
        )
    except Exception as e:
        logger.error(f"[V2] channel send error: {repr(e)}")

    await state.finish()

    await message.answer(
        "Zo'r tanlov 🎯\n\n"
        "Siz tanlagan universitet va boshqa alternativalarning kontrakt narxlarini shu yerda ko'rishingiz mumkin:",
        reply_markup=_complete_kb(),
    )
