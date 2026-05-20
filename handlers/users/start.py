from aiogram import types
from aiogram.dispatcher.filters.builtin import CommandStart
from aiogram.dispatcher import FSMContext
from loader import dp, bot
from keyboards.default.userKeyboard import keyboard_user, strong_pass, continue_button, restart_markup, adminKeyboard_user
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, InputFile, ContentType
import re
from states.userStates import Registration, FullRegistration, DeleteUser
from utils.send_req import auth_check, user_register, user_verify, user_info, user_login, delete_user, upload_image, fetch_regions, district_locations, fetch_educations,\
upload_file, me, update_application_form, get_user, add_chat_id, change_password, reset_password, user_verify_by_id, save_chat_id
from datetime import datetime
from keyboards.inline.user_inline import share_button, gender_button, help_button, forget_password_button
from data.config import CHANNEL_ID, ADMINS
from icecream import ic
from utils.my_redis import redis
import json
from middlewares.throttling import save_user_state
import pandas as pd
import io
import asyncio

# redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# from loader import dp, redis  # siz allaqachon redis = Redis(...) deb yozgansiz

@dp.message_handler(CommandStart(), state="*")
async def bot_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    # subscription_checked redis dan o'qiymiz (FSM finish() ni omon qoladi)
    sub_key = f"{user_id}_subscription_checked"
    subscription_checked = await redis.exists(sub_key)

    await state.finish()

    # user 5 va 7 ni parallel tekshirish
    get_user_id_5, get_user_id_7 = await asyncio.gather(
        get_user(user_id, 5),
        get_user(user_id, 7),
    )

    if get_user_id_5 is None:
        try:
            await add_chat_id(
                chat_id_user=user_id,
                first_name_user=message.from_user.first_name or "not found",
                last_name_user=message.from_user.last_name or "not found",
                pin=message.from_user.username or "not found",
                phone="1",
                username=message.from_user.username or "not found",
                date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        except Exception as e:
            ic("add_chat_id failed:", e)

    if get_user_id_7 is None:
        # sync requests.post — event loop ni bloklamaslik uchun executor da
        try:
            loop = asyncio.get_event_loop()
            ads = await loop.run_in_executor(
                None,
                save_chat_id,
                user_id,
                message.from_user.first_name or "not found",
                message.from_user.last_name or "not found",
                7,
                message.from_user.username or "not found",
                "active",
            )
            print(ads)
        except Exception as e:
            ic("save_chat_id executor failed:", e)

    # Subscription gate
    if not subscription_checked:
        try:
            member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)

            if member.status not in ["member", "creator", "administrator"]:
                join_kb = InlineKeyboardMarkup(row_width=1).add(
                    InlineKeyboardButton("📲 Kanalga obuna bo‘lish", url="https://t.me/mentalaba_uz"),
                    InlineKeyboardButton("✅ Obuna bo‘ldim", callback_data="check_sub")
                )

                await message.answer(
                    "Quyidagi kanalga obuna bo‘ling va keyin 'Obuna bo‘ldim' tugmasini bosing 👇",
                    reply_markup=join_kb
                )
                return
            else:
                await redis.set(sub_key, "1", ex=86400)  # 24h cache
        except Exception as e:
            ic("subscription check failed:", type(e).__name__, str(e))
            await message.answer("⚠️ Tekshiruvda xatolik. Keyinroq urinib ko‘ring.")
            return

    if str(user_id) in ADMINS:
        keyboard = adminKeyboard_user
    else:
        keyboard = keyboard_user

    await message.answer(
        "🎓 <b>Mentalaba botiga xush kelibsiz!</b>\n\n"
        "📲 <b>Tizimga kirish uchun telefon raqamingizni yuboring.</b>\n"
        "Iltimos, raqamni <u>faqat 9 ta raqam bilan</u> kiriting "
        "(masalan: <code>901234567</code>).",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

    # Phone state — admin uchun ham (admin panel state='*' bilan ishlaydi, konflikt yo'q)
    await Registration.phone.set()

    await save_user_state(user_id=user_id, state="startni bosgan", username=message.from_user.username, saved_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


@dp.callback_query_handler(lambda call: call.data == "check_sub")
async def check_subscription(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id

    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)

        if member.status in ["member", "creator", "administrator"]:
            await redis.set(f"{user_id}_subscription_checked", "1", ex=86400)
            await callback_query.message.delete()

            kb = adminKeyboard_user if str(user_id) in ADMINS else keyboard_user
            await callback_query.message.answer(
                "🎓 <b>Mentalaba botiga xush kelibsiz!</b>\n\n"
                "📲 <b>Tizimga kirish uchun telefon raqamingizni yuboring.</b>\n"
                "Iltimos, raqamni <u>faqat 9 ta raqam bilan</u> kiriting (masalan: <code>901234567</code>).",
                reply_markup=kb,
                parse_mode="HTML"
            )
            await Registration.phone.set()
            user_id = callback_query.from_user.id
            await save_user_state(user_id=user_id, state="obunani bosgan, obuna bo'lgan",username=callback_query.from_user.username, saved_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        else:
            await callback_query.answer("❌ Hali obuna bo‘lmagansiz!", show_alert=True)
            user_id = callback_query.from_user.id
            await save_user_state(user_id=user_id, state="obunani bosgan, obuna emas", username=callback_query.from_user.username, saved_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    except Exception as e:
        ic("Xatolik:", e)
        await callback_query.answer("⚠️ Tekshiruvda xatolik.", show_alert=True)


@dp.message_handler(content_types=[ContentType.TEXT, ContentType.CONTACT], state=Registration.phone)
async def phone_number(message: types.Message, state: FSMContext):
    user_chat_id = message.from_user.id
    
    if message.content_type == ContentType.CONTACT:
        phone = message.contact.phone_number
        await message.answer("Raqamingiz qabul qilindi", reply_markup=ReplyKeyboardRemove())
        user_id = message.from_user.id
        await save_user_state(user_id=user_id, state="raqam yuborgan, qabul qilingan", username=message.from_user.username, saved_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    else:
        raw_text = message.text.strip()
        # if not re.fullmatch(r"9\d{8}", raw_text):
        if not re.fullmatch(r"(50|9[0-9]|33|88|77)\d{7}", raw_text):

            await message.answer("❌ Noto‘g‘ri formatdagi raqam. Iltimos, faqat 9 ta raqam kiriting. Namuna: 901234567")
            user_id = message.from_user.id
            await save_user_state(user_id=user_id, state="raqam yuborgan, qabul qilinmagan", username=message.from_user.username, saved_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            return
        phone = "+998" + raw_text




    if not phone.startswith('+'):
        phone = '+' + phone
    ic(phone, 3)
    key = f"{user_chat_id}_phone"
    data = {
        "phone": phone
    }
    # har safar yangilash — user telefon o'zgartirsa stale qolmasin
    await redis.set(key, json.dumps(data), ex=157680000)

    try:
        data_ = await auth_check(phone=phone)
    except Exception as e:
        ic("auth_check exception:", e)
        await message.answer("⚠️ Server bilan bog'lanishda xatolik. Iltimos, keyinroq urinib ko'ring.")
        return

    ic("auth_check result:", data_, type(data_))
    normalized = (data_ or "").strip().strip('"').lower()
    await state.update_data(phone=phone)
    if normalized == "true":
        await message.answer("️️🔐 Iltimos, parolingizni kiriting. U kamida 8 ta belgidan iborat bo‘lishi lozim.", reply_markup=ReplyKeyboardRemove())
        await Registration.login.set()
    elif normalized == "false":
        await message.answer(
            "📝 <b>Ro‘yxatdan o‘tish</b>\n\n"
            "Iltimos, ro‘yxatdan o‘tish uchun kerakli ma’lumotlarni kiriting.\n"
            "<i>Parol kamida 8 ta belgidan iborat bo‘lishi shart.</i>\n\n"
            "🔑 Parolingizni kiriting:",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove()
        )
        await Registration.password.set()
        user_id = message.from_user.id
        await save_user_state(user_id=user_id, state="ro'yhatga o'tishga yuborildi", username=message.from_user.username, saved_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    else:
        ic("auth_check unexpected response:", repr(data_))
        await message.answer("⚠️ Serverdan kutilmagan javob qaytdi. Iltimos, qaytadan urinib ko'ring yoki /start ni bosing.")



@dp.message_handler(state=Registration.password)
async def password_user(message: types.Message, state: FSMContext):
    get_user_password = message.text.strip()

    if len(get_user_password) < 8:
        await message.answer("❌ Parol kamida 8 ta belgidan iborat bo'lishi kerak. Qaytadan kiriting.")
        return

    await state.update_data(password=get_user_password)
    user_data = await state.get_data()
    phone = user_data.get("phone")
    password = user_data.get("password")

    try:
        response, status_ = await user_register(phone=phone, password=password)
    except Exception as e:
        ic("user_register exception:", type(e).__name__, str(e))
        await message.answer("⚠️ Server bilan bog'lanishda xatolik. Iltimos, keyinroq urinib ko'ring.")
        return

    ic(response)
    user_id = message.from_user.id
    if status_ == 201:
        await message.answer("Raqamingizga yuborilgan tasdiqlash kodini kiriting.")
        ic("Registered:", response)
        await Registration.verify.set()
        await save_user_state(user_id=user_id, state="raqamga tasdiqlash kodi yuborilgan", username=message.from_user.username, saved_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    else:
        await message.answer("Sms yuborish limiti cheklangan 5 daqiqadan so'ng urinib ko'ring.")
        await save_user_state(user_id=user_id, state="raqamga tasdiqlash kodi yuborilgan, limitdan o'tgan", username=message.from_user.username, saved_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

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
        ic(154, response, status_)

        if status_ != 201:
            await message.answer("❌ Kod noto'g'ri yoki muddati o'tgan. Qayta urinib ko'ring.")
            return

        if not isinstance(response, dict):
            ic("user_verify unexpected response shape:", repr(response))
            await message.answer("⚠️ Serverdan kutilmagan javob. /start ni qaytadan bosing.")
            return

        token = response.get("token")
        auth_key = response.get("auth_key")
        haveApplicationForm = response.get("haveApplicationForm")
        await state.update_data(token=token, auth_key=auth_key, haveApplicationForm=haveApplicationForm)

        await message.answer("️️Passport yoki ID karta seriya raqamini kiriting.\nNamuna: AC1234567")
        await Registration.pinfl.set()
        user_id = message.from_user.id
        await save_user_state(user_id=user_id, state="passport so'raldi", username=message.from_user.username, saved_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
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
            await message.answer(response_data['message'], reply_markup=help_button)
            await state.finish()
            return
        elif status == 404:
            await message.answer_photo(
             photo="https://api.mentalaba.uz/logo/b3ccc6f7-aaad-42e2-a256-5cc8e8dc0d70.webp",
             caption="Profil rasmini yuklang\n\nHajmi 5 mb dan katta bo'lmagan, .png, .jpg, .jpeg formatdagi oq yoki ko’k fonda olingan 3x4 razmerdagi rasmingizni yuklang."
             )
            await FullRegistration.profile_image.set()
        
        me_user, status_ = await me(token=token)
        ic(me_user, status_)
        if status_ == 401:
            await message.answer("❌ Parol noto'g'ri kiritilgan!, Qayta urinib ko‘ring.", reply_markup=forget_password_button)
            return
        user_educations = me_user.get("user_educations")
        auth_key = me_user.get("auth_key")
        await state.update_data(auth_key=auth_key)
        ic(226, user_educations, type(user_educations))
        if user_educations is None:
            await message.answer("Ta’lim ma'lumotlaringizni to'ldiring.") #, reply_markup=continue_button)
            # await FullRegistration.extra_phone.set()
            # return
            data = await state.get_data()
            token = data.get("token")
            extra_phone = message.text.strip()
            await state.update_data(extra_phone=extra_phone)
            await message.answer("Ta’lim dargohi joylashgan viloyatni tanlang.", reply_markup=ReplyKeyboardRemove())
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
        if status != 409 and status != 404 and user_educations is not None:
            # 7. Foydalanuvchiga javob
            # await message.answer("✅ Ma'lumotlar qabul qilindi. Endi hujjatlaringizni topshiring.")
            text = (
                "✅ <b>Siz tizimga muvaffaqiyatli kirdingiz.</b>\n\n"
                "🎓 <b>Endi siz tanlagan universitetlarga hujjat topshirish imkoniyatiga egasiz.</b>\n\n"
                # "📄 <i>Iltimos, davom etish uchun kerakli bo‘limni tanlang.</i>"
            )
            user_id = message.from_user.id
            await save_user_state(user_id=user_id, state="tizimga kirdi", username=message.from_user.username, saved_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            # Foydalanuvchiga yuborish
            user_chat_id = message.chat.id
            find_user = await redis.get(f"{user_chat_id}_phone")
            if find_user:
                find_user = json.loads(find_user)
                # await redis.set(f"user:{user_chat_id}", find_user)
            else:
                find_user = None
            #     await redis.set(f"user:{user_chat_id}", response_data)
            # await redis.set(f"user:{user_chat_id}", response_data)
            # if find_user is not None:
            auth_data = {
                "token": token,
                "refresh_token": refreshToken
            }
            await redis.set(
                f"auth:{user_chat_id}",
                json.dumps(auth_data),
                ex=60 * 60 * 24 * 365 * 5  # 5 yil
            )
            
            share_button_ = await share_button(auth_key=auth_key, chat_id=user_chat_id)
            await message.answer(text, reply_markup=share_button_, parse_mode="HTML")  
            await state.set_state(None) 

    except ValueError:
        await message.answer("❌ Noto‘g‘ri sana formati. Iltimos, DD-MM-YYYY formatida kiriting (masalan: 28-08-2000).")

# 3. Callback handlerda tokenlarni qayta yukla
@dp.callback_query_handler(lambda c: c.data.startswith("submit:"))
async def handle_submit(callback: types.CallbackQuery):
    print('submit ishladi')
    chat_id = callback.data.split(":")[1]

    # 🔐 Bosgan user - asl usermi, tekshiramiz
    if str(callback.from_user.id) != chat_id:
        await callback.answer("⛔ Bu tugma sizga tegishli emas!", show_alert=True)
        return
    auth_data_raw = await redis.get(f"auth:{chat_id}")
    if not auth_data_raw:
        await callback.message.answer("⛔ Token topilmadi yoki muddati o‘tgan.")
        return
    auth_data = json.loads(auth_data_raw)
    token = auth_data.get("token")
    refresh_token = auth_data.get("refresh_token")
    
    await callback.message.answer(f"✅ Token bilan ishlashga tayyorman:\n\n🔑 {token}")



@dp.callback_query_handler(lambda call: call.data.startswith("help_uz"), state="*")
async def help_uz(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("" \
    "Agar sizda savollar, texnik muammolar yoki tizimdan foydalanish bo‘yicha tushunmovchiliklar bo‘lsa, iltimos, bizning rasmiy yordam markazimizga murojaat qiling: @Mentalaba_help")

@dp.callback_query_handler(lambda call: call.data.startswith("rewrite"), state="*")
async def rewrite(call: types.CallbackQuery, state: FSMContext):
    await state.finish()  # Avvalgi holatni tugatish
    await bot_start(call.message, state)



@dp.message_handler(state=FullRegistration.profile_image, content_types=types.ContentTypes.PHOTO | types.ContentTypes.DOCUMENT)
async def profile_image_user(message: types.Message, state: FSMContext):
    data = await state.get_data()
    token_ = data.get("token")

    # Rasmni olish
    if message.photo:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_id = photo.file_id
    elif message.document and message.document.mime_type.startswith("image/"):
        file = await bot.get_file(message.document.file_id)
        file_id = message.document.file_id
    else:
        await message.answer("Iltimos, rasm yuboring.")
        return

    file_path = file.file_path
    photo_bytes = await bot.download_file(file_path)
    temp_path = f"/tmp/{file_id}.jpg"

    with open(temp_path, "wb") as f:
        f.write(photo_bytes.read())

    # Upload qilish
    response, status = await upload_image(token_, temp_path)
    print(response, status)

    os.remove(temp_path)

    # Statega yozish (agar kerak bo‘lsa)
    await state.update_data(profile_image=response.get("url"))

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
    await message.answer("Ta’lim dargohi joylashgan viloyatni tanlang.", reply_markup=ReplyKeyboardRemove())
    response, status_ = await fetch_regions(token)
    keyboard = InlineKeyboardMarkup(row_width=2)
    for region in response:
        keyboard.insert(
            InlineKeyboardButton(
                text=region['name_uz'],
                callback_data=f"region_{region['id']}"
            )
        )
    keyboard.insert(
        InlineKeyboardButton(
            text="🔙 Ortga",
            callback_data="back_to_region"
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
    await state.update_data(region_id=region_id)
    data_ = await state.get_data()
    ic(data_)
    ic(region_id)
    token = data_.get("token")
    response, status_ = await district_locations(int(region_id), token)

    await bot.edit_message_reply_markup(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=None
    )

    keyboard = InlineKeyboardMarkup(row_width=2)
    for region in response:
        keyboard.insert(
            InlineKeyboardButton(
                text=region['name_uz'],
                callback_data=f"location_{region['id']}"
            )
        )
    keyboard.insert(
        InlineKeyboardButton(
            text="🔙 Ortga",
            callback_data="back_to_district"
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
    location_id = call.data.split("_")[1]
    await state.update_data(district_id=location_id)
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
    text_mess = "Ta'lim dargohi nomini kiriting:"
    if int(university_id) == 1:
        text_mess = "Ta'lim dargohi nomini kiriting:\nNamuna: 12-maktab"
    elif int(university_id) == 2:
        text_mess = "Ta'lim dargohi nomini kiriting:\nLitsey: Diplomatiya litseyi"
    elif int(university_id) == 3:
        text_mess = "Ta'lim dargohi nomini kiriting:\nToshkent turizm va mehmonxona menejmenti texnikumi"
    elif int(university_id) == 4:
        text_mess = "Ta'lim dargohi nomini kiriting:\nToshkent moliya instituti"
    # await call.message.answer("📆 Tamomlagan yilingizni kiriting.\nNamuna: 2022")
    await call.message.answer(text_mess)
    await FullRegistration.edu_name.set()

# @dp.callback_query_handler(lambda call: call.data == "back_to_region", state="*")
# async def back_to_region(call: types.CallbackQuery, state: FSMContext):
#     data = await state.get_data()
#     token = data.get("token")
#     response, status_ = await fetch_regions(token)

#     keyboard = InlineKeyboardMarkup(row_width=2)
#     for region in response:
#         keyboard.insert(
#             InlineKeyboardButton(
#                 text=region['name_uz'],
#                 callback_data=f"region_{region['id']}"
#             )
#         )

#     await state.set_state(FullRegistration.select_edu_plase)  # ✅ State oldin yangilanadi

#     await bot.edit_message_text(
#         chat_id=call.message.chat.id,
#         message_id=call.message.message_id,
#         text="📍 Viloyatlardan birini tanlang:",
#         reply_markup=keyboard
#     )



@dp.callback_query_handler(lambda call: call.data.startswith("back_to_district"), state="*")
async def back_to_district(call: types.CallbackQuery, state: FSMContext):
    import time
    print('keldi back_to_district')
    data_ = await state.get_data()
    token = data_.get("token")
    region_id = data_.get("region_id")
    response, status_ = await district_locations(int(region_id), token)
    print(status_)
    keyboard = InlineKeyboardMarkup(row_width=2)
    for region in response:
        keyboard.insert(
            InlineKeyboardButton(
                text=region['name_uz'],
                callback_data=f"location_{region['id']}"
            )
        )
    keyboard.insert(
        InlineKeyboardButton(
            text="🔙 Ortga",
            # callback_data="back_to_region"
            callback_data=f"back_to_region_{int(time.time())}"
        )
    )

    await state.set_state(FullRegistration.district_place)  # ✅ Birinchi

    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="📍 Tumanlardan birini tanlang:",
        reply_markup=keyboard
    )
    print('ketdi javob 568')

@dp.callback_query_handler(lambda call: call.data.startswith("back_to_region"), state="*")
async def back_to_region(call: types.CallbackQuery, state: FSMContext):
    await call.answer(cache_time=0)
    data = await state.get_data()
    token = data.get("token")
    response, status_ = await fetch_regions(token)

    keyboard = InlineKeyboardMarkup(row_width=2)
    for region in response:
        keyboard.insert(
            InlineKeyboardButton(
                text=region['name_uz'],
                callback_data=f"region_{region['id']}"
                
            )
        )

    await state.set_state(FullRegistration.select_edu_plase)  # ✅ State oldin yangilanadi

    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="📍 Viloyatlardan birini tanlang:",
        reply_markup=keyboard
    )

@dp.message_handler(state=FullRegistration.edu_name)
async def university_name_user(message: types.Message, state: FSMContext):
    university_name = message.text.strip()
    await state.update_data(university_name=university_name)
    await message.answer("📆 Ta'lim muassasasini tamomlagan yilingizni kiriting.\nNamuna: 2022")
    await FullRegistration.ended_year.set()

@dp.message_handler(state=FullRegistration.ended_year)
async def ended_year_user(message: types.Message, state: FSMContext):
    ended_year = message.text.strip()
    await state.update_data(ended_year=ended_year)
    await message.answer("Diplom faylini yuklang fayl formatda yuboring.\nFayl va rasmni telegram orqali yuborishda hajmini siqish funksiyasidan foydalanmasdan yuboring\n\nRuxsat etilgan formatlar: PDF, JPG, JPEG, PNG\nFayl hajmi 5mb dan katta bo'lmasligi kerak")
    await FullRegistration.diplom_file.set()

# @dp.message_handler(state=FullRegistration.diplom_file, content_types=[types.ContentType.DOCUMENT, types.ContentType.PHOTO])
# async def edu_name_user(message: types.Message, state: FSMContext):
#     data = await state.get_data()
#     refreshToken = data.get("refreshToken")
#     token_ = data.get("token")
#     file = message.document
#     auth_key = data.get("auth_key")
#     # Telegram faylni olish
#     file_info = await bot.get_file(file.file_id)
#     file_path = file_info.file_path

#     # Faylni vaqtinchalik yuklab olish
#     local_path = f"/tmp/{file.file_name}"  # Linux/macOS uchun
#     await bot.download_file(file_path, destination=local_path)

#     # Faylni upload qilish
#     response, status_ = await upload_file(token_, local_path)
#     ic(493, response, status_)
#     # Clean up: vaqtinchalik faylni o‘chirish
#     if os.path.exists(local_path):
#         os.remove(local_path)
#     ic(response.get("path"), response['path'])
#     # Statega yozish
#     await state.update_data(diplom_file=response["path"])
#     # await message.answer("📎 Diplom fayli yuklandi!")
#     ic(data.get("diplom_file"), data)
#     update_user_applicaition_form, status_ = await update_application_form(
#         token=token_,
#         district_id=data.get("district_id"),
#         region_id=data.get("region_id"),
#         institution_name=data.get("university_name"),
#         graduation_year=data.get("ended_year"),
#         file_path=response['path']
#     )
#     ic(update_user_applicaition_form, status_)
#     text = (
#         "✅ <b>Siz tizimga muvaffaqiyatli kirdingiz.</b>\n\n"
#         "🎓 <b>Endi siz tanlagan universitetlarga hujjat topshirish imkoniyatiga egasiz.</b>\n\n"
#         # "📄 <i>Iltimos, davom etish uchun kerakli bo‘limni tanlang.</i>"
#     )
#     share_button_ = await share_button(auth_key=auth_key, chat_id=message.from_user.id)
#     # Foydalanuvchiga yuborish
#     await message.answer(text, reply_markup=share_button_, parse_mode="HTML")

#     await state.set_data(None)


@dp.message_handler(state=FullRegistration.diplom_file, content_types=[types.ContentType.DOCUMENT, types.ContentType.PHOTO])
async def edu_name_user(message: types.Message, state: FSMContext):
    data = await state.get_data()
    refreshToken = data.get("refreshToken")
    token_ = data.get("token")
    auth_key = data.get("auth_key")

    # Telegram faylni olish
    if message.document:
        file_info = await bot.get_file(message.document.file_id)
        file_name = message.document.file_name
    elif message.photo:
        photo = message.photo[-1]  # eng yuqori sifatli rasm
        file_info = await bot.get_file(photo.file_id)
        file_name = f"{photo.file_unique_id}.jpg"
    else:
        await message.answer("Fayl topilmadi.")
        return

    file_path = file_info.file_path
    local_path = f"/tmp/{file_name}"

    # Faylni vaqtinchalik yuklab olish
    await bot.download_file(file_path, destination=local_path)

    # Faylni upload qilish
    response, status_ = await upload_file(token_, local_path)
    ic(493, response, status_)

    # Faylni o'chirish
    if os.path.exists(local_path):
        os.remove(local_path)

    await state.update_data(diplom_file=response["path"])
    ic(response.get("path"), response['path'])

    update_user_applicaition_form, status_ = await update_application_form(
        token=token_,
        district_id=data.get("district_id"),
        region_id=data.get("region_id"),
        institution_name=data.get("university_name"),
        graduation_year=data.get("ended_year"),
        file_path=response['path']
    )
    ic(update_user_applicaition_form, status_)

    text = (
        "✅ <b>Siz tizimga muvaffaqiyatli kirdingiz.</b>\n\n"
        "🎓 <b>Endi siz tanlagan universitetlarga hujjat topshirish imkoniyatiga egasiz.</b>\n\n"
    )
    user_id = message.from_user.id
    await save_user_state(user_id=user_id, state="tizimga kirdi", username=message.from_user.username, saved_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    share_button_ = await share_button(auth_key=auth_key, chat_id=message.from_user.id)
    await message.answer(text, reply_markup=share_button_, parse_mode="HTML")

    await state.set_data(None)



@dp.message_handler(state=Registration.login)
async def pinfl_user(message: types.Message, state: FSMContext):
    get_user_password = message.text.strip()
    await state.update_data(password=get_user_password)
    full_data = await state.get_data()
    ic(full_data)
    token_ = full_data.get("token")
    ic(497, token_)
    if len(get_user_password) < 8:
        await message.answer("❌ Parol kamida 8 ta belgidan iborat bo‘lishi lozim.")
        return
    await state.update_data(password=get_user_password)



    # if user_educations is not None:
    user_data = await state.get_data()
    phone = user_data.get("phone")
    password = user_data.get("password")
    token = user_data.get("token")
    refreshToken = user_data.get("refreshToken")
    response, status_ = await user_login(phone=phone, password=password)
    ic(708, response, status_)
    token_ = response.get("token")
    await state.update_data(token=response.get("token"), refreshToken=refreshToken)
    
    me_user, status_ = await me(token=token_)
    ic(me_user, status_)
    if status_ == 401:
        await message.answer("❌ Parol noto'g'ri kiritilgan!", reply_markup=forget_password_button)
        return
    user_educations = me_user.get("user_educations")
    auth_key = me_user.get("auth_key")
    ic(user_educations, type(user_educations))
    refreshToken = response.get("refreshToken")
    ic(530, token_,token,  refreshToken)
    await state.update_data(token=token_)
    await state.update_data(refreshToken=refreshToken)
    if user_educations is None:
        await message.answer("Passport yoki ID karta seriya raqamini kiriting.\nNamuna: AC12345678", reply_markup=ReplyKeyboardRemove())
        await Registration.pinfl.set()
        return

    if user_educations is not None:
        first_name = response.get("first_name")
        refreshToken = response.get("refreshToken")
        ic(530, token_, refreshToken)
        await state.update_data(token=token)
        await state.update_data(refreshToken=refreshToken)
        
        if status_ == 401:
            await message.answer()
            await message.answer("❌ Parol noto'g'ri kiritilgan!", reply_markup=forget_password_button)
            return
        if first_name is None:
            await state.update_data(token=token_)
            await message.answer("️️Passport yoki ID karta seriya raqamini kiriting.\nNamuna: AC12345678")
            await Registration.pinfl.set()
            # await message.answer('kirdiz')
        else:
            text = (
                "✅ <b>Siz tizimga muvaffaqiyatli kirdingiz.</b>\n\n"
                "🎓 <b>Endi siz tanlagan universitetlarga hujjat topshirish imkoniyatiga egasiz.</b>\n\n"
                # "📄 <i>Iltimos, davom etish uchun kerakli bo‘limni tanlang.</i>"
            )

            user_id = message.from_user.id
            await save_user_state(user_id=user_id, state="tizimga kirdi", username=message.from_user.username, saved_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            share_button_ = await share_button(auth_key=auth_key, chat_id=message.chat.id)
            # Foydalanuvchiga yuborish
            await message.answer(text, reply_markup=share_button_, parse_mode="HTML")
            await FullRegistration.next()


@dp.callback_query_handler(lambda call: call.data == "forget_password", state="*")
async def forget_passwords(call: types.CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    redis_key = f"forget_password_lock:{user_id}"

    # 1. Redisda lock borligini tekshirish
    if await redis.exists(redis_key):
        ttl = await redis.ttl(redis_key)
        await call.answer(f"❗ Kuting, {ttl} soniyadan so‘ng qayta urinishingiz mumkin.", show_alert=True)
        return

    # 2. 120 soniyaga lock o‘rnatish
    await redis.set(redis_key, "locked", ex=60)

    # 3. Jarayonni davom ettirish
    data = await state.get_data()
    phone = data.get("phone")

    # Agar phone yo'q bo‘lsa, oldindan tekshirishni unutmang
    if not phone:
        await call.answer("❗ Telefon raqamingiz topilmadi. Avval ro‘yxatdan o‘ting.", show_alert=True)
        return

    response_data, status = await change_password(phone=phone)
    state_id = response_data.get("id")

    await state.update_data(state_id=state_id)
    await call.answer("✅ Kod yuborildi. Iltimos, tasdiqlash kodini kiriting.")
    await FullRegistration.change_password.set()



@dp.message_handler(state=FullRegistration.change_password)
async def change_passwords(message: types.Message, state: FSMContext):
    get_user_password6 = message.text.strip()
    data = await state.get_data()
    await state.update_data(get_user_password6=get_user_password6)
    state_id = data.get("state_id")
    data_reset, status_ = await user_verify_by_id(id=state_id, code=get_user_password6)
    if status_ != 200 or status_ != 201:
        ic(data_reset)
        await message.answer("Yangi parolni yuboring, kamida 8ta belgidan iborat bo'lishi lozim.")
        await FullRegistration.reset_password.set()

@dp.message_handler(state=FullRegistration.reset_password)
async def reset_passwords(message: types.Message, state: FSMContext):
    data = await state.get_data()
    state_id = data.get("state_id")
    user_password_profile = message.text.strip()
    phone = data.get("phone")
    await state.update_data(user_password_profile=user_password_profile)
    data_reset, status_ = await reset_password(id=state_id, password=user_password_profile, phone=phone)
    if status_ == 200:
        await message.answer("Parol muvaffaqiyatli o'zgartirildi.", reply_markup=restart_markup)
        await FullRegistration.next()
    else:
        await message.answer("Parol o'zgartirishda muammo yuz berdi.")
# @dp.message_handler(commands=['delete_user'], state='*')
# async def delete(message: types.Message, state: FSMContext):
#     await state.set_state(None)
#     data = await state.get_data()
#     ic(data)
#     token_ = data.get("token")
#     phone_ = data.get("phone")
#     password = data.get("password")
#     user_login_, status = await user_login(phone=phone_, password=password)
#     ic(user_login_)
#     token_user = user_login_.get("token")
#     ic(token_user)

#     try:
#         response, status = await delete_user(token=token_user, phone=phone_, password=password)
#         ic(response, status)

#         if status == 200:  # yoki o'zgaruvchining tuzilishiga qarab
#             await message.answer("Siz ro'yxatdan muvaffaqiyatli o'chirildingiz.")
#         else:
#             await message.answer("O'chirishda muammo yuz berdi.")
#     except Exception as e:
#         ic(e)
#         await message.answer("Xatolik yuz berdi. Iltimos, keyinroq urinib ko‘ring.")


# @dp.message_handler(commands=['delete_user'], state='*')
# async def confirm_delete_user(message: types.Message, state: FSMContext):
#     answer = message.text.strip().lower()
    
#     if answer == "ha":
#         data = await state.get_data()
#         token_ = data.get("token")
#         phone_ = data.get("phone")
#         password = data.get("password")
        
#         user_login_, status = await user_login(phone=phone_, password=password)
#         token_user = user_login_.get("token")

#         try:
#             response, status = await delete_user(token=token_user, phone=phone_, password=password)
#             if status == 200:
#                 await message.answer("✅ Siz ro'yxatdan muvaffaqiyatli o'chirildingiz.")
#             else:
#                 await message.answer("❌ O'chirishda muammo yuz berdi.")
#         except Exception as e:
#             await message.answer("⚠️ Xatolik yuz berdi. Keyinroq urinib ko‘ring.")
    
#     elif answer == "yoq" or answer == "yo‘q":
#         await message.answer("❎ O'chirish bekor qilindi.")
    
#     else:
#         await message.answer("Iltimos, faqat *Ha* yoki *Yo‘q* deb javob bering.", parse_mode='Markdown')
#         return  # qayta so‘rash
    
#     await state.finish()  # holatni tozalaymiz


@dp.message_handler(commands=['delete_user'], state='*')
async def delete_user_confirm(message: types.Message, state: FSMContext):
    await DeleteUser.confirm.set()
    await message.answer("🔒 Siz rostdan ham ro‘yxatdan o‘chmoqchimisiz?\n\nIltimos, *Ha* yoki *Yo‘q* deb javob bering.", parse_mode="Markdown")


@dp.message_handler(state=DeleteUser.confirm)
async def handle_delete_confirmation(message: types.Message, state: FSMContext):
    answer = message.text.strip().lower()

    if answer == "ha":
        data = await state.get_data()
        token_ = data.get("token")
        phone_ = data.get("phone")
        password = data.get("password")

        if not all([phone_, password]):
            await message.answer("❗ Ma’lumotlar yetarli emas. Iltimos, qayta ro‘yxatdan o‘ting.")
            await state.finish()
            return

        user_login_, status = await user_login(phone=phone_, password=password)
        token_user = user_login_.get("token")

        try:
            response, status = await delete_user(token=token_user, phone=phone_, password=password)
            if status == 200:
                await message.answer("✅ Siz ro'yxatdan muvaffaqiyatli o'chirildingiz.")
            else:
                await message.answer("❌ O'chirishda muammo yuz berdi.")
        except Exception as e:
            await message.answer("⚠️ Xatolik yuz berdi. Keyinroq urinib ko‘ring.")

    elif answer in ["yoq", "yo‘q", "yo'q"]:
        await message.answer("❎ O'chirish bekor qilindi.")
    else:
        await message.answer("Iltimos, faqat *Ha* yoki *Yo‘q* deb javob bering.", parse_mode="Markdown")
        return  # noto‘g‘ri javobda qayta kutadi

    await state.finish()

    
@dp.message_handler(commands=['extract_data'], state='*')
async def extract_data_handler(message: types.Message):
    keys = await redis.keys("user_id:*")
    if not keys:
        await message.answer("Redisda hech qanday user data topilmadi.")
        return

    data = []
    for key in keys:
        key_str = key.decode("utf-8") if isinstance(key, bytes) else key
        user_id = key_str.split(":")[1]

        val = await redis.get(key)
        if isinstance(val, bytes):
            val = val.decode("utf-8")

        # Har doim JSON deb och
        val_json = {}
        try:
            val_json = json.loads(val)
        except Exception:
            pass  # fallback bo‘lsa bo‘sh dict

        state = val_json.get("state", "")
        username = val_json.get("username", "")
        saved_at = val_json.get("saved_at", "")

        data.append({
            "user_id": user_id,
            "username": username,
            "state": state,
            "saved_at": saved_at
        })

    df = pd.DataFrame(data)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='UserStates')

    output.seek(0)
    excel_file = InputFile(output, filename="user_states.xlsx")

    await message.answer_document(excel_file, caption="Tozalangan user state jadvali.")