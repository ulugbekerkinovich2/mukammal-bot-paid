# import re
# from aiogram import types
# from aiogram.dispatcher import FSMContext
# from aiogram.dispatcher.filters.builtin import CommandStart
# from aiogram.types import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
# from utils.send_req import register
# from loader import dp
# from keyboards.default.userKeyboard import keyboard_user
# from states.userStates import Registration
# from data.config import SUBJECTS_MAP
# from keyboards.inline.user_inline import language_keyboard_button
# PHONE_RE = re.compile(r"^\+?\d{9,15}$")


# # ---------- Keyboards ----------

# def confirm_kb():
#     kb = InlineKeyboardMarkup(row_width=2)
#     kb.add(
#         InlineKeyboardButton("✏️ Tahrirlash", callback_data="reg_edit"),
#         InlineKeyboardButton("❌ Bekor qilish", callback_data="reg_cancel"),
#     )
#     kb.add(cancel_btn())
#     return kb
# def cancel_btn():
#     return InlineKeyboardButton(
#         text="✅ Tasdiqlash",
#         callback_data="reg_confirm"
#     )


# def pairs_kb(lang: str = "uz"):
#     """
#     UI: har bir tugma -> 'Fan1 — Fan2'
#     1 qatorda 2ta tugma (row_width=2)
#     callback_data -> pair:<id1>|<id2>
#     """
#     kb = InlineKeyboardMarkup(row_width=1)

#     for first_uz, info in SUBJECTS_MAP.items():
#         first_label = first_uz if lang == "uz" else info.get("ru", first_uz)
#         first_id = info["id"]

#         rel_uz_list = info.get("relative", {}).get("uz", [])
#         rel_ru_list = info.get("relative", {}).get("ru", [])

#         for i, second_uz in enumerate(rel_uz_list):
#             second_label = second_uz
#             if lang == "ru":
#                 if i < len(rel_ru_list):
#                     second_label = rel_ru_list[i]

#             # second id: mapdan topamiz
#             second_info = SUBJECTS_MAP.get(second_uz)
#             if not second_info:
#                 continue
#             second_id = second_info["id"]

#             btn_text = f"{first_label} — {second_label}"
#             kb.insert(
#                 InlineKeyboardButton(
#                     text=btn_text,
#                     callback_data=f"pair:{first_id}|{second_id}",
#                 )
#             )

#     # kb.add(InlineKeyboardButton("❌ Bekor qilish", callback_data="reg_cancel"))
#     kb.add(cancel_btn())
#     return kb


# # ---------- Helpers ----------

# def normalize_phone(phone: str) -> str:
#     phone = phone.strip()
#     if not phone.startswith("+"):
#         phone = "+" + phone
#     return phone


# def find_subject_by_id(sid: int):
#     for uz_name, info in SUBJECTS_MAP.items():
#         if info["id"] == sid:
#             return uz_name, info.get("ru", uz_name)
#     return None, None


# def pair_is_allowed(first_uz: str, second_uz: str) -> bool:
#     info = SUBJECTS_MAP.get(first_uz)
#     if not info:
#         return False
#     return second_uz in info.get("relative", {}).get("uz", [])


# # ---------- Handlers ----------

# @dp.message_handler(CommandStart(), state="*")
# async def start_cmd(message: types.Message, state: FSMContext):
#     await state.finish()
#     await message.answer(
#         "Assalomu alaykum! Telefon raqamingizni yuboring:",
#         reply_markup=keyboard_user
#     )
#     await Registration.phone.set()


# @dp.callback_query_handler(lambda c: c.data == "reg_cancel", state="*")
# async def reg_cancel(call: types.CallbackQuery, state: FSMContext):
#     await call.answer()
#     await state.finish()
#     await call.message.edit_text(
#         "❌ Ro‘yxatdan o‘tish bekor qilindi.\n/start bosib qayta boshlashingiz mumkin."
#     )


# @dp.message_handler(content_types=types.ContentType.CONTACT, state=Registration.phone)
# async def reg_phone_contact(message: types.Message, state: FSMContext):
#     phone = normalize_phone(message.contact.phone_number)

#     await state.update_data(phone=phone, lang="uz")
#     await message.answer("FIO kiriting:\nNamuna: Ism Familiya", reply_markup=ReplyKeyboardRemove())
#     await Registration.fio.set()


# @dp.message_handler(state=Registration.phone)
# async def reg_phone_text(message: types.Message, state: FSMContext):
#     phone = message.text.strip()
#     if not PHONE_RE.match(phone):
#         return await message.answer("❌ Telefon xato. Tugma orqali yuboring yoki +998... formatda yozing.")

#     phone = normalize_phone(phone)

#     await state.update_data(phone=phone, lang="uz")
#     await message.answer("FIO kiriting:", reply_markup=ReplyKeyboardRemove())
#     await Registration.fio.set()

# FULL_NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЎўҚқҒғҲҳЁё\s]{5,}$")
# @dp.message_handler(state=Registration.fio)
# async def reg_fio(message: types.Message, state: FSMContext):
#     fio = message.text.strip()

#     parts = fio.split()
#     if len(parts) < 2:
#         return await message.answer(
#             "❌ FIO xato.\nIltimos, Ism va Familiyani kiriting.\nMasalan: Ulug‘bek Erkinov"
#         )

#     if not FULL_NAME_RE.match(fio):
#         return await message.answer(
#             "❌ FIO faqat harflardan iborat bo‘lishi kerak.\nMasalan: Ulug‘bek Erkinov"
#         )

#     if any(len(p) < 2 for p in parts):
#         return await message.answer(
#             "❌ Ism yoki familiya juda qisqa.\nQayta kiriting:"
#         )

#     await state.update_data(fio=fio)
#     await message.answer("Maktab kodini kiriting (masalan: YU132):")
#     await Registration.school_code.set()



# @dp.message_handler(state=Registration.school_code)
# async def reg_school(message: types.Message, state: FSMContext):
#     school_code = message.text.strip().upper()
#     if len(school_code) < 3:
#         return await message.answer("❌ Maktab kodi xato. Qayta kiriting:")

#     await state.update_data(school_code=school_code)
#     data = await state.get_data()
#     lang = data.get("lang", "uz")

#     await message.answer(
#         "1-fan va 2-fanni birga tanlang (juftlik):",
#         reply_markup=pairs_kb(lang=lang)
#     )
#     await Registration.second_subject.set()  # endi pair tanlaymiz


# @dp.callback_query_handler(lambda c: c.data.startswith("pair:"), state=Registration.second_subject)
# async def pick_pair(call: types.CallbackQuery, state: FSMContext):
#     await call.answer()
#     payload = call.data.split("pair:", 1)[1]  # "<id1>|<id2>"
#     first_id_str, second_id_str = payload.split("|", 1)

#     first_id = int(first_id_str)
#     second_id = int(second_id_str)

#     first_uz, first_ru = find_subject_by_id(first_id)
#     second_uz, second_ru = find_subject_by_id(second_id)

#     if not first_uz or not second_uz:
#         return await call.message.answer("❌ Fan topilmadi. Qayta tanlang.")

#     # xavfsizlik: haqiqatan allowedmi?
#     if not pair_is_allowed(first_uz, second_uz):
#         return await call.message.answer("❌ Bu juftlik ruxsat etilmagan. Qayta tanlang.")

#     await state.update_data(
#         first_subject_id=first_id,
#         first_subject_uz=first_uz,
#         first_subject_ru=first_ru,
#         second_subject_id=second_id,
#         second_subject_uz=second_uz,
#         second_subject_ru=second_ru,
#     )

#     data = await state.get_data()
#     text = (
#         "🧾 Ma'lumotlaringiz:\n\n"
#         f"📞 Phone: {data['phone']}\n"
#         f"👤 FIO: {data['fio']}\n"
#         f"🏫 School code: {data['school_code']}\n"
#         f"📘 1-fan: {data['first_subject_uz']}\n"
#         f"📗 2-fan: {data['second_subject_uz']}\n\n"
#         "Tasdiqlaysizmi?"
#     )
#     await call.message.edit_text(text, reply_markup=confirm_kb())
#     await Registration.verify.set()


# @dp.callback_query_handler(lambda c: c.data in ["reg_confirm", "reg_edit"], state=Registration.verify)
# async def reg_verify(call: types.CallbackQuery, state: FSMContext):
#     await call.answer()

#     if call.data == "reg_edit":
#         data = await state.get_data()
#         lang = data.get("lang", "uz")
#         await call.message.answer(
#             "Juftlikni qayta tanlang:",
#             reply_markup=pairs_kb(lang=lang)
#         )
#         await Registration.second_subject.set()
#         return

#     data = await state.get_data()

#     # 🔄 Loading message
#     loading_msg = await call.message.answer("⏳ Iltimos, kuting... Siz uchun test savollari yaratilmoqda")

#     try:
#         result = register(
#             bot_id=call.from_user.id,
#             full_name=data["fio"],
#             phone=data["phone"],
#             school_code=data["school_code"],
#             first_subject_id=data["first_subject_id"],
#             second_subject_id=data["second_subject_id"],
#             password="1111"
#         )

#         # agar shu yerga kelsa — hammasi OK
#         await loading_msg.edit_text("✅ Ro‘yxatdan muvaffaqiyatli o‘tdingiz!")
#         await state.finish()

#     except Exception as e:
#         # bu joyga faqat server xatolari tushadi
#         await loading_msg.edit_text(
#             f"❌ Ro‘yxatdan o‘tishda xatolik:\n{str(e)}"
#         )

#     except Exception as e:
#         # kutilmagan xatolar
#         await loading_msg.edit_text(
#             "❌ Nomaʼlum xatolik yuz berdi. Keyinroq urinib ko‘ring."
#         )
#         print("UNEXPECTED ERROR:", e)

import re
from datetime import datetime
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.builtin import CommandStart
from aiogram.types import ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton

from utils.send_req import register
from loader import dp
from keyboards.default.userKeyboard import keyboard_user
from states.userStates import Registration
from data.config import SUBJECTS_MAP
from keyboards.inline.user_inline import language_keyboard_button

PHONE_RE = re.compile(r"^\+?\d{9,15}$")
FULL_NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЎўҚқҒғҲҳЁё\s]{5,}$")


# ---------- Keyboards ----------

def confirm_kb():
    kb = InlineKeyboardMarkup(row_width=2)

    # 1-qator: Tahrirlash | Bekor qilish
    kb.row(
        InlineKeyboardButton("✏️ Tahrirlash", callback_data="reg_edit"),
        InlineKeyboardButton("❌ Bekor qilish", callback_data="reg_cancel"),
    )

    # 2-qator: Tasdiqlash (pastda)
    kb.row(
        InlineKeyboardButton("✅ Tasdiqlash", callback_data="reg_confirm")
    )

    return kb



def pairs_kb(lang: str = "uz"):
    """
    Har bir tugma -> 'Fan1 — Fan2'
    callback_data -> pair:<id1>|<id2>
    """
    kb = InlineKeyboardMarkup(row_width=1)

    for first_uz, info in SUBJECTS_MAP.items():
        first_label = first_uz if lang == "uz" else info.get("ru", first_uz)
        first_id = info["id"]

        rel_uz_list = info.get("relative", {}).get("uz", [])
        rel_ru_list = info.get("relative", {}).get("ru", [])

        for i, second_uz in enumerate(rel_uz_list):
            second_label = second_uz
            if lang == "ru" and i < len(rel_ru_list):
                second_label = rel_ru_list[i]

            second_info = SUBJECTS_MAP.get(second_uz)
            if not second_info:
                continue
            second_id = second_info["id"]

            btn_text = f"{first_label} — {second_label}"
            kb.insert(
                InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"pair:{first_id}|{second_id}",
                )
            )

    kb.add(InlineKeyboardButton("❌ Bekor qilish", callback_data="reg_cancel"))
    return kb


# ---------- Helpers ----------

def normalize_phone(phone: str) -> str:
    phone = phone.strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    return phone


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


# ---------- Handlers ----------

@dp.message_handler(CommandStart(), state="*")
async def start_cmd(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer(
        "Assalomu alaykum! Telefon raqamingizni yuboring:",
        reply_markup=keyboard_user
    )
    await Registration.phone.set()


@dp.callback_query_handler(lambda c: c.data == "reg_cancel", state="*")
async def reg_cancel(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await state.finish()
    try:
        await call.message.edit_text(
            "❌ Ro‘yxatdan o‘tish bekor qilindi.\n/start bosib qayta boshlashingiz mumkin."
        )
    except Exception:
        await call.message.answer(
            "❌ Ro‘yxatdan o‘tish bekor qilindi.\n/start bosib qayta boshlashingiz mumkin."
        )


@dp.message_handler(content_types=types.ContentType.CONTACT, state=Registration.phone)
async def reg_phone_contact(message: types.Message, state: FSMContext):
    phone = normalize_phone(message.contact.phone_number)

    await state.update_data(phone=phone, ui_lang="uz")  # ui_lang hozircha uz
    await message.answer(
        "FIO kiriting:\nNamuna: Ism Familiya",
        reply_markup=ReplyKeyboardRemove()
    )
    await Registration.fio.set()


@dp.message_handler(state=Registration.phone)
async def reg_phone_text(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    if not PHONE_RE.match(phone):
        return await message.answer("❌ Telefon xato. Tugma orqali yuboring yoki +998... formatda yozing.")

    phone = normalize_phone(phone)
    await state.update_data(phone=phone, ui_lang="uz")
    await message.answer("FIO kiriting:", reply_markup=ReplyKeyboardRemove())
    await Registration.fio.set()


@dp.message_handler(state=Registration.fio)
async def reg_fio(message: types.Message, state: FSMContext):
    fio = message.text.strip()
    parts = fio.split()

    if len(parts) < 2:
        return await message.answer(
            "❌ FIO xato.\nIltimos, Ism va Familiyani kiriting.\nMasalan: Ulug‘bek Erkinov"
        )

    if not FULL_NAME_RE.match(fio):
        return await message.answer(
            "❌ FIO faqat harflardan iborat bo‘lishi kerak.\nMasalan: Ulug‘bek Erkinov"
        )

    if any(len(p) < 2 for p in parts):
        return await message.answer("❌ Ism yoki familiya juda qisqa.\nQayta kiriting:")

    await state.update_data(fio=fio)
    await message.answer("Maktab kodini kiriting (masalan: YU132):")
    await Registration.school_code.set()


@dp.message_handler(state=Registration.school_code)
async def reg_school(message: types.Message, state: FSMContext):
    school_code = message.text.strip().upper()
    if len(school_code) < 3:
        return await message.answer("❌ Maktab kodi xato. Qayta kiriting:")

    await state.update_data(school_code=school_code)

    # ✅ YANGI BOSQICH: Imtihon tili tanlash
    await message.answer(
        "Imtihon tilini tanlang:",
        reply_markup=language_keyboard_button
    )
    await Registration.exam_lang.set()


# ✅ language_keyboard_button callback_data: "uz" / "ru" deb turibdi
@dp.callback_query_handler(lambda c: c.data in ["uz", "ru"], state=Registration.exam_lang)
async def pick_exam_language(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    exam_lang = call.data  # "uz" yoki "ru"

    await state.update_data(exam_lang=exam_lang)

    data = await state.get_data()
    ui_lang = data.get("ui_lang", "uz")  # UI uchun
    await call.message.edit_text(
        f"✅ Tanlandi: {'🇺🇿 O‘zbekcha' if exam_lang == 'uz' else '🇷🇺 Русский'}\n\n"
        "Endi 1-fan va 2-fanni birga tanlang (juftlik):"
    )
    await call.message.answer(
        "Juftlikni tanlang:",
        reply_markup=pairs_kb(lang=ui_lang)
    )
    await Registration.second_subject.set()


@dp.callback_query_handler(lambda c: c.data.startswith("pair:"), state=Registration.second_subject)
async def pick_pair(call: types.CallbackQuery, state: FSMContext):
    await call.answer()

    payload = call.data.split("pair:", 1)[1]  # "<id1>|<id2>"
    first_id_str, second_id_str = payload.split("|", 1)

    first_id = int(first_id_str)
    second_id = int(second_id_str)

    first_uz, first_ru = find_subject_by_id(first_id)
    second_uz, second_ru = find_subject_by_id(second_id)

    if not first_uz or not second_uz:
        return await call.message.answer("❌ Fan topilmadi. Qayta tanlang.")

    if not pair_is_allowed(first_uz, second_uz):
        return await call.message.answer("❌ Bu juftlik ruxsat etilmagan. Qayta tanlang.")

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

    text = (
        "🧾 Ma'lumotlaringiz:\n\n"
        f"📞 Phone: {data['phone']}\n"
        f"👤 FIO: {data['fio']}\n"
        f"🏫 School code: {data['school_code']}\n"
        f"🗣 Imtihon tili: {'O‘zbekcha' if exam_lang == 'uz' else 'Ruscha'}\n"
        f"📘 1-fan: {data['first_subject_uz']}\n"
        f"📗 2-fan: {data['second_subject_uz']}\n\n"
        "Tasdiqlaysizmi?"
    )

    await call.message.edit_text(text, reply_markup=confirm_kb())
    await Registration.verify.set()


@dp.callback_query_handler(lambda c: c.data in ["reg_confirm", "reg_edit"], state=Registration.verify)
async def reg_verify(call: types.CallbackQuery, state: FSMContext):
    await call.answer()

    if call.data == "reg_edit":
        data = await state.get_data()

        # avval tilni qayta tanlatamiz (xohlasang), yoki to'g'ridan pairga qaytar
        await call.message.answer(
            "Imtihon tilini qayta tanlang:",
            reply_markup=language_keyboard_button
        )
        await Registration.exam_lang.set()
        return

    data = await state.get_data()

    loading_msg = await call.message.answer("⏳ Iltimos, kuting... Siz uchun test savollari yaratilmoqda")

    try:
        result = register(
            bot_id=call.from_user.id,
            full_name=data["fio"],
            phone=data["phone"],
            school_code=data["school_code"],
            first_subject_id=data["first_subject_id"],
            second_subject_id=data["second_subject_id"],
            language=data.get("exam_lang", "uz"),  # ✅ API ga yuborildi
            password="1111",
        )

        await loading_msg.edit_text("✅ Ro‘yxatdan muvaffaqiyatli o‘tdingiz!")
        await state.finish()

    except Exception as e:
        await loading_msg.edit_text(f"❌ Ro‘yxatdan o‘tishda xatolik:\n{str(e)}")
