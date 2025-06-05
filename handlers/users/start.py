from aiogram import types
from aiogram.dispatcher.filters.builtin import CommandStart
from aiogram.dispatcher import FSMContext
from loader import dp, bot
from keyboards.default.userKeyboard import keyboard_user, strong_pass
from aiogram.types import ContentType
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import re
from states.userStates import Registration
from utils.send_req import auth_check, user_register, user_verify, user_info, user_login, delete_user, upload_image, fetch_regions, district_locations, fetch_educations, upload_file
from aiogram.types import ReplyKeyboardRemove
from datetime import datetime
from keyboards.inline.user_inline import share_button, gender_button
from data.config import CHANNEL_ID
from icecream import ic
from states.userStates import Registration, FullRegistration

@dp.message_handler(CommandStart(), state="*")
async def bot_start(message: types.Message, state: FSMContext):
    await state.finish()
    user_id = message.from_user.id
    data = await state.get_data()

    # Avval tekshirilgan bo‘lsa qayta so‘ralmasin
    if not data.get("subscription_checked"):
        try:
            member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)

            if member.status not in ["member", "creator", "administrator"]:
                join_kb = InlineKeyboardMarkup().add(
                    InlineKeyboardButton("🚀 Obuna bo‘ling va imkoniyatlardan foydalaning!" \
                    "\n\n✅ Obuna bo‘lganingizdan so‘ng pastdagi tugmani bosing.", url="https://t.me/mentalaba_uz"),
                    InlineKeyboardButton("✅ Obuna bo‘ldim", callback_data="check_sub")
                )
                await message.answer(
                    "❗️Iltimos, Mentalaba kanaliga obuna bo‘ling:\n\n👉 https://t.me/mentalaba_uz",
                    reply_markup=join_kb
                )
                return
            else:
                await state.update_data(subscription_checked=True)
        except Exception as e:
            await message.answer("⚠️ Tekshiruvda xatolik. Keyinroq urinib ko‘ring.")
            return

    # Agar obuna bo‘lgan bo‘lsa (yoki allaqachon tekshirilgan bo‘lsa)
    await message.answer(
        "🎓 <b>Mentalaba botiga xush kelibsiz!</b>\n\n"
        "📲 <b>Tizimga kirish uchun telefon raqamingizni yuboring.</b>\n"
        "Iltimos, raqamni <u>faqat 9 ta raqam bilan</u> kiriting (masalan: <code>901234567</code>).",
        reply_markup=keyboard_user,
        parse_mode="HTML"
    )
    await Registration.phone.set()


@dp.callback_query_handler(lambda call: call.data == "check_sub")
async def check_subscription(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id

    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)

        if member.status in ["member", "creator", "administrator"]:
            await state.update_data(subscription_checked=True)
            await callback_query.message.delete()

            await callback_query.message.answer(
                "🎓 <b>Mentalaba botiga xush kelibsiz!</b>\n\n"
                "📲 <b>Tizimga kirish uchun telefon raqamingizni yuboring.</b>\n"
                "Iltimos, raqamni <u>faqat 9 ta raqam bilan</u> kiriting (masalan: <code>901234567</code>).",
                reply_markup=keyboard_user,
                parse_mode="HTML"
            )
            await Registration.phone.set()

        else:
            await callback_query.answer("❌ Hali obuna bo‘lmagansiz!", show_alert=True)

    except Exception as e:
        ic("Xatolik:", e)
        await callback_query.answer("⚠️ Tekshiruvda xatolik.", show_alert=True)


@dp.message_handler(content_types=[ContentType.TEXT, ContentType.CONTACT], state=Registration.phone)
async def phone_number(message: types.Message, state: FSMContext):
    if message.content_type == ContentType.CONTACT:
        phone = message.contact.phone_number
        await message.answer("Raqamingiz qabul qilindi", reply_markup=ReplyKeyboardRemove())
    else:
        raw_text = message.text.strip()
        if not re.fullmatch(r"9\d{8}", raw_text):
            await message.answer("❌ Noto‘g‘ri formatdagi raqam. Iltimos, faqat 9 ta raqam kiriting. Namuna: 901234567")
            return
        phone = "+998" + raw_text

    await state.update_data(phone=phone)
    ic(phone, 3)
    data_ = await auth_check(phone=phone)
    ic("auth_check result:", data_, type(data_))

    if data_ == "true":
        await message.answer("️️🔐 Iltimos, parolingizni kiriting. U kamida 8 ta belgidan iborat bo‘lishi lozim.", reply_markup=ReplyKeyboardRemove())
        await Registration.login.set()
    elif data_ == "false":
        await message.answer(
            "📝 <b>Ro‘yxatdan o‘tish</b>\n\n"
            "Iltimos, ro‘yxatdan o‘tish uchun kerakli ma’lumotlarni kiriting.\n"
            "<i>Parol kamida 8 ta belgidan iborat bo‘lishi shart.</i>\n\n"
            "🔑 Parolingizni kiriting:",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove()
        )
        await Registration.password.set()



@dp.message_handler(state=Registration.password)
async def password_user(message: types.Message, state: FSMContext):
    get_user_password = message.text.strip()
    await state.update_data(password=get_user_password)

    user_data = await state.get_data()
    phone = user_data.get("phone")
    password = user_data.get("password")

    response, status_ = await user_register(phone=phone, password=password)
    ic(response)
    if status_ == 201:
        await message.answer("Raqamingizga yuborilgan tasdiqlash kodini kiriting.")
        ic("Registered:", response)
        await Registration.verify.set()
    else:
        await message.answer("Sms yuborish limiti cheklangan")

@dp.message_handler(state=Registration.verify)
async def verify_user(message: types.Message, state: FSMContext):
    # Foydalanuvchi kiritgan kod raqam ekanligini tekshirish
    if not message.text.strip().isdigit():
        await message.answer("❌ Kod noto‘g‘ri formatda. Iltimos, faqat raqam kiriting.")
        return

    data = await state.get_data()
    phone = data.get("phone")
    code = int(message.text.strip())

    try:
        response, status_ = await user_verify(phone=phone, code=code)
        token = response.get("token")
        auth_key = response.get("auth_key")
        haveApplicationForm = response.get("haveApplicationForm")

        await state.update_data(token=token, auth_key=auth_key, haveApplicationForm=haveApplicationForm)
        # Aytaylik, server True/False yoki JSON qaytaradi
        if status_ == 201:
            await message.answer("️️Passport yoki ID karta seriya raqamini kiriting.")
            await Registration.pinfl.set()
        else:
            await message.answer("❌ Kod noto‘g‘ri yoki muddati o‘tgan. Qayta urinib ko‘ring.")
    except Exception as e:
        ic("Xatolik:", e)
        await message.answer("⚠️ Ichki tizimda xatolik yuz berdi. Iltimos, keyinroq urinib ko‘ring.")


@dp.message_handler(state=Registration.pinfl)
async def login_user(message: types.Message, state: FSMContext):
    pinfl = message.text.strip().upper()
    ic("PINFL:", pinfl)

    # Regex orqali formatni tekshiramiz: 2 ta harf + 7 ta raqam
    if re.fullmatch(r"[A-Z]{2}\d{7}", pinfl):
        await state.update_data(pinfl=pinfl)
        await message.answer("📅 Tug‘ilgan kuningizni yuboring\nNamuna: <b>28-08-2000</b>", parse_mode="HTML")
        await Registration.birth_date.set()
    else:
        await message.answer("❌ Passport seriyasi noto‘g‘ri. To‘g‘ri format: <b>AA1234567</b>", parse_mode="HTML")
        return
    

@dp.message_handler(state=Registration.birth_date)
async def birth_date_user(message: types.Message, state: FSMContext):
    birth_date_str = message.text.strip()
    data = await state.get_data()
    ic(138, data)
    pinfl = data.get("pinfl")
    token = data.get("token")
    refreshToken = data.get("refreshToken")
    if not pinfl or not token:
        await message.answer("❌ Ichki xatolik: token yoki PINFL mavjud emas.")
        return
    try:
        # 1. Sana formatini tekshirish
        birth_date = datetime.strptime(birth_date_str, "%d-%m-%Y")

        # 2. Kelajakdagi sanalarni rad etish
        if birth_date > datetime.now():
            await message.answer("❌ Tug‘ilgan sana kelajakdagi sana bo‘lishi mumkin emas.")
            return

        # 3. 10 yoshdan kichik foydalanuvchilarni rad etish
        age = (datetime.now() - birth_date).days // 365
        if age < 10:
            await message.answer("❌ Yoshingiz 10 yoshdan katta bo‘lishi kerak.")
            return

        # 4. Holatga tug‘ilgan sanani saqlash
        await state.update_data(birth_date=birth_date_str)

        # 5. Sana formatini YYYY-MM-DD shakliga o‘zgartirish
        formatted_date = birth_date.strftime("%Y-%m-%d")

        # 6. user_info funksiyasiga yuborish
        response_data, status = await user_info(formatted_date, pinfl, token)
        ic(response_data, status)
        if status == 409:
            await message.answer(response_data['message'])
        elif status == 404:
            await message.answer_photo("https://api.mentalaba.uz/logo/b3ccc6f7-aaad-42e2-a256-5cc8e8dc0d70.webp", caption="Profil rasmini yuklang\n\nHajmi 5 mb dan katta bo'lmagan, .png, .jpg, .jpeg formatdagi oq yoki ko’k fonda olingan 3x4 razmerdagi rasmingizni yuklang.")
            await FullRegistration.profile_image.set()
        if status != 409 and status != 404:
            # 7. Foydalanuvchiga javob
            # await message.answer("✅ Ma'lumotlar qabul qilindi. Endi hujjatlaringizni topshiring.")
            text = (
                "✅ <b>Siz tizimga muvaffaqiyatli kirdingiz.</b>\n\n"
                "🎓 <b>Endi siz tanlagan universitetlarga hujjat topshirish imkoniyatiga egasiz.</b>\n\n"
                # "📄 <i>Iltimos, davom etish uchun kerakli bo‘limni tanlang.</i>"
            )
            await state.set_state(None)

            # Foydalanuvchiga yuborish
            share_button_ = share_button(token=token, refresh_token=refreshToken)
            await message.answer(text, reply_markup=share_button_, parse_mode="HTML")    

    except ValueError:
        await message.answer("❌ Noto‘g‘ri sana formati. Iltimos, DD-MM-YYYY formatida kiriting (masalan: 28-08-2000).")



import os

@dp.message_handler(state=FullRegistration.profile_image, content_types=types.ContentType.PHOTO)
async def profile_image_user(message: types.Message, state: FSMContext):
    data = await state.get_data()
    token_ = data.get("token")

    # 1. Rasmni olish
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_path = file.file_path

    # 2. Faylni lokalga yuklab olish
    photo_bytes = await bot.download_file(file_path)
    temp_path = f"/tmp/{photo.file_id}.jpg"

    with open(temp_path, "wb") as f:
        f.write(photo_bytes.read())

    # 3. Upload qilish
    response, status = await upload_image(token_, temp_path)
    print(response, status)
    # 4. Faylni o‘chirish
    os.remove(temp_path)

    # 5. Statega yozish (agar kerak bo‘lsa)
    await state.update_data(profile_image=response.get("url"))  # yoki image_id

    await message.answer("Familiyangizni kiriting.")
    await FullRegistration.surename.set()

@dp.message_handler(state=FullRegistration.surename)
async def surename_user(message: types.Message, state: FSMContext):
    surename = message.text.strip()
    await state.update_data(surename=surename)
    await message.answer("Ismingizni kiriting.")
    await FullRegistration.first_name.set()

@dp.message_handler(state=FullRegistration.first_name)
async def first_name_user(message: types.Message, state: FSMContext):
    first_name = message.text.strip()
    await state.update_data(first_name=first_name)
    await message.answer("Otangizni ismini kiriting.")
    await FullRegistration.third_name.set()

@dp.message_handler(state=FullRegistration.third_name)
async def third_name_user(message: types.Message, state: FSMContext):
    third_name = message.text.strip()
    await state.update_data(third_name=third_name)
    await message.answer("Jinsingizni tanlang.", reply_markup=gender_button)
    await FullRegistration.gender.set()

@dp.callback_query_handler(lambda call: call.data in ["male", "female"], state=FullRegistration.gender)
async def gender_user(call: types.CallbackQuery, state: FSMContext):
    gender = call.data
    await state.update_data(gender=gender)
    await call.message.answer("Tug‘ilgan joyingizni kiriting.\nNamuna: Toshkent")
    await FullRegistration.birth_place.set()

@dp.message_handler(state=FullRegistration.birth_place)
async def birth_date_user(message: types.Message, state: FSMContext):
    birth_date_raw = message.text.strip()
    await state.update_data(birth_place=birth_date_raw)
    await message.answer("📌 Passport yoki ID karta oldi tarafini yuklang")
    await FullRegistration.passport_image1.set()


@dp.message_handler(state=FullRegistration.passport_image1, content_types=types.ContentType.PHOTO)
async def passport_image1_user(message: types.Message, state: FSMContext):
    data = await state.get_data()
    token_ = data.get("token")

    # 1. Rasmni olish
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_path = file.file_path

    # 2. Faylni lokalga yuklab olish
    photo_bytes = await bot.download_file(file_path)
    temp_path = f"/tmp/{photo.file_id}.jpg"

    with open(temp_path, "wb") as f:
        f.write(photo_bytes.read())

    # 3. Upload qilish
    response, status = await upload_image(token_, temp_path)
    print(response, status)
    # 4. Faylni o‘chirish
    os.remove(temp_path)

    # 5. Statega yozish (agar kerak bo‘lsa)
    await state.update_data(passport_image1=response.get("url"))  # yoki image_id

    await message.answer("📌 Passport yoki ID karta orqa tarafini yuklang:")
    await FullRegistration.passport_image2.set()
    

@dp.message_handler(state=FullRegistration.passport_image2, content_types=types.ContentType.PHOTO)
async def passport_image2_user(message: types.Message, state: FSMContext):
    data = await state.get_data()
    token_ = data.get("token")

    # 1. Rasmni olish
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_path = file.file_path

    # 2. Faylni lokalga yuklab olish
    photo_bytes = await bot.download_file(file_path)
    temp_path = f"/tmp/{photo.file_id}.jpg"

    with open(temp_path, "wb") as f:
        f.write(photo_bytes.read())

    # 3. Upload qilish
    response, status = await upload_image(token_, temp_path)
    print(response, status)
    # 4. Faylni o‘chirish
    os.remove(temp_path)

    # 5. Statega yozish (agar kerak bo‘lsa)
    await state.update_data(passport_image2=response.get("url"))  # yoki image_id
    await message.answer("Qo'shimcha telefon raqamingizni kiriting.\nNamuna: +998991234567")
    await FullRegistration.extra_phone.set()

@dp.message_handler(state=FullRegistration.extra_phone)
async def extra_phone_user(message: types.Message, state: FSMContext):
    data = await state.get_data()
    token = data.get("token")
    extra_phone = message.text.strip()
    await state.update_data(extra_phone=extra_phone)
    await message.answer("Ta’lim dargohi joylashgan viloyatni tanlang.")
    response, status_ = await fetch_regions(token)
    keyboard = InlineKeyboardMarkup(row_width=2)
    for region in response:
        keyboard.insert(
            InlineKeyboardButton(
                text=region['name_uz'],
                callback_data=f"region_{region['id']}"
            )
        )

    await bot.send_message(
        chat_id=message.chat.id,
        text="📍 Viloyatlardan birini tanlang:",
        reply_markup=keyboard
    )
    await FullRegistration.select_edu_plase.set()

@dp.callback_query_handler(lambda call: call.data.startswith("region_"), state=FullRegistration.select_edu_plase)
async def region_user(call: types.CallbackQuery, state: FSMContext):
    region_id = call.data.split("_")[1]
    data_ = await state.get_data()
    ic(data_)
    ic(region_id)
    token = data_.get("token")
    response, status_ = await district_locations(int(region_id), token)
    keyboard = InlineKeyboardMarkup(row_width=2)
    for region in response:
        keyboard.insert(
            InlineKeyboardButton(
                text=region['name_uz'],
                callback_data=f"location_{region['id']}"
            )
        )

    await bot.send_message(
        chat_id=call.message.chat.id,
        text="📍 Tumanlardan birini tanlang:",
        reply_markup=keyboard
    )
    await FullRegistration.district_place.set()



@dp.callback_query_handler(lambda call: call.data.startswith("location_"), state=FullRegistration.district_place)
async def location_user(call: types.CallbackQuery, state: FSMContext):
    # location_id = call.data.split("_")[1]
    data = await state.get_data()
    token = data.get("token")
    response, status_ = await fetch_educations(token)
    keyboard = InlineKeyboardMarkup(row_width=2)
    for region in response:
        keyboard.insert(
            InlineKeyboardButton(
                text=region['name_uz'],
                callback_data=f"university_{region['id']}"
            )
        )

    await bot.send_message(
        chat_id=call.message.chat.id,
        text="📍 Ta'lim turini tanlang:",
        reply_markup=keyboard
    )
    await FullRegistration.select_edu_name.set()

@dp.callback_query_handler(lambda call: call.data.startswith("university_"), state=FullRegistration.select_edu_name)
async def university_user(call: types.CallbackQuery, state: FSMContext):
    university_id = call.data.split("_")[1]
    await state.update_data(university_id=university_id)

    await call.message.answer("📆 Tamomlagan yilingizni kiriting.\nNamuna: 2022")
    await FullRegistration.ended_year.set()


@dp.message_handler(state=FullRegistration.ended_year)
async def ended_year_user(message: types.Message, state: FSMContext):
    ended_year = message.text.strip()
    await state.update_data(ended_year=ended_year)
    await message.answer("Diplom faylini yuklang file formatda.")
    await FullRegistration.diplom_file.set()

@dp.message_handler(state=FullRegistration.diplom_file, content_types=types.ContentType.DOCUMENT)
async def edu_name_user(message: types.Message, state: FSMContext):
    data = await state.get_data()
    refreshToken = data.get("refreshToken")
    token_ = data.get("token")
    file = message.document

    # Telegram faylni olish
    file_info = await bot.get_file(file.file_id)
    file_path = file_info.file_path

    # Faylni vaqtinchalik yuklab olish
    local_path = f"/tmp/{file.file_name}"  # Linux/macOS uchun
    await bot.download_file(file_path, destination=local_path)

    # Faylni upload qilish
    response, status_ = await upload_file(token_, local_path)

    # Clean up: vaqtinchalik faylni o‘chirish
    if os.path.exists(local_path):
        os.remove(local_path)

    # Statega yozish
    await state.update_data(diplom_file=response.get("url"))
    # await message.answer("📎 Diplom fayli yuklandi!")
    await state.set_data(None)
    text = (
        "✅ <b>Siz tizimga muvaffaqiyatli kirdingiz.</b>\n\n"
        "🎓 <b>Endi siz tanlagan universitetlarga hujjat topshirish imkoniyatiga egasiz.</b>\n\n"
        # "📄 <i>Iltimos, davom etish uchun kerakli bo‘limni tanlang.</i>"
    )
    share_button_ = share_button(token=token_, refresh_token=refreshToken)
    # Foydalanuvchiga yuborish
    await message.answer(text, reply_markup=share_button_, parse_mode="HTML")


    


@dp.message_handler(state=Registration.login)
async def pinfl_user(message: types.Message, state: FSMContext):
    get_user_password = message.text.strip()
    await state.update_data(password=get_user_password)
    if len(get_user_password) < 8:
        await message.answer("❌ Parol kamida 8 ta belgidan iborat bo‘lishi lozim.")
        return
    await state.update_data(password=get_user_password)

    user_data = await state.get_data()
    phone = user_data.get("phone")
    password = user_data.get("password")
    token = user_data.get("token")
    refreshToken = user_data.get("refreshToken")
    response, status_ = await user_login(phone=phone, password=password)
    ic(response, status_)
    token_ = response.get("token")
    
    first_name = response.get("first_name")
    refreshToken = response.get("refreshToken")
    await state.update_data(token=token_)
    await state.update_data(refreshToken=refreshToken)
    if status_ == 401:
        await message.answer("❌ Parol noto'g'ri kiritilgan!")
        return
    if first_name is None:
        await state.update_data(token=token_)
        await message.answer("️️Passport yoki ID karta seriya raqamini kiriting.")
        await Registration.pinfl.set()
        # await message.answer('kirdiz')
    else:
        text = (
            "✅ <b>Siz tizimga muvaffaqiyatli kirdingiz.</b>\n\n"
            "🎓 <b>Endi siz tanlagan universitetlarga hujjat topshirish imkoniyatiga egasiz.</b>\n\n"
            # "📄 <i>Iltimos, davom etish uchun kerakli bo‘limni tanlang.</i>"
        )
        share_button_ = share_button(token=token_, refresh_token=refreshToken)
        # Foydalanuvchiga yuborish
        await message.answer(text, reply_markup=share_button_, parse_mode="HTML")
        await state.set_state(None)


@dp.message_handler(commands=['delete_user'], state='*')
async def delete(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ic(data)
    token_ = data.get("token")
    phone_ = data.get("phone")
    password = data.get("password")

    try:
        response, status = await delete_user(token=token_, phone=phone_, password=password)
        ic(response, status)

        if status == 200:  # yoki o'zgaruvchining tuzilishiga qarab
            await message.answer("Siz ro'yxatdan muvaffaqiyatli o'chirildingiz.")
        else:
            await message.answer("O'chirishda muammo yuz berdi.")
    except Exception as e:
        ic(e)
        await message.answer("Xatolik yuz berdi. Iltimos, keyinroq urinib ko‘ring.")
