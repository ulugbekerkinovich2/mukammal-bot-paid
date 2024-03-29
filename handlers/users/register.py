from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from utils import send_req
from loader import dp
from states.personalData import PersonalData
from keyboards.default.registerKeyBoardButton import reset_password


@dp.message_handler(Command("register"))
async def register(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    button_phone = types.KeyboardButton(text='☎️ Telefon raqamni yuborish', request_contact=True)
    keyboard.add(button_phone)
    await message.answer("☎️ Telefon raqamingizni yuboring\nNamuna: 998991234567", reply_markup=keyboard)
    await PersonalData.phone.set()

# @dp.message_handler(content_types=types.ContentTypes.CONTACT, state=PersonalData.phone)
@dp.message_handler(state=PersonalData.phone, content_types=types.ContentTypes.CONTACT)
async def phone_contact_received(message: types.Message, state: FSMContext):
    # await message.answer(message.json())
    # print(message)
    # print(message.text)
    try:
        contact = message.contact
        phone_num = contact.phone_number
        print('auto:', phone_num)
    except AttributeError:
        phone_num = None
        contact = None
    print('next')
    try:
        custom_writened_phone = message.text
        print(custom_writened_phone)
    except AttributeError:
        custom_writened_phone = None

    if contact is not None and phone_num is not None:
        custom_phone = f'+{phone_num}'
        print(phone_num)
        if len(phone_num) == 12:
            print(phone_num)
            check_user = send_req.check_number(custom_phone)
            print('check_user', check_user.json())
            if str(check_user.json()) == 'True':

                await state.update_data(phone=phone_num)
                user_login = send_req.user_login(custom_phone)
                print('user_login: ',user_login)
                if user_login.status_code == 200:
                    remove_keyboard = types.ReplyKeyboardRemove()
                    await message.answer("Telefon raqamingiz qabul qilindi. Telefon raqamingizga yuborilgan kodni yuboring", reply_markup=remove_keyboard)
                    await PersonalData.secret_code.set()

            elif str(check_user.json()) == 'False':
                print('check_user', check_user)
                await state.update_data(phone_num)
                user_register = send_req.user_register(custom_phone)
                print('user_register: ',user_register)
                if user_register.status_code == 201:
                    await message.answer("Telefon raqamingiz qabul qilindi. Telefon raqamingizga yuborilgan kodni yuboring", reply_markup=remove_keyboard)
                    await PersonalData.secret_code.set()
    elif custom_writened_phone is not None:
        custom_writened_phone = custom_writened_phone.strip()
        print('custom_writened_phone: ',custom_writened_phone)
        status_while = True
        while status_while:
            
            phone_num = custom_writened_phone.strip()
            if len(phone_num) != 12 and not phone_num.isdigit():
                await message.answer("Telefon raqam no\'to\'g\'ri kiritildi!")
                response_msg = await dp.bot.send_message(message.chat.id, "Iltimos, to'g'ri formatda telefon raqamni yuboring.")
                response = await dp.bot.wait_for("message", timeout=30)
                custom_writened_phone = message.text.strip() if response.text else None
                if custom_writened_phone:
                    phone_num = custom_writened_phone
                else:
                    break

            elif len(phone_num) == 12:
                print('keldi')
                status_while = False
                custom_phone = f'+{phone_num}'
                check_user = send_req.check_number(custom_phone)
                if str(check_user.json()) == 'True':
                    await state.update_data(phone=phone_num)
                    user_login = send_req.user_login(custom_phone)
                    if user_login.status_code == 200:
                        remove_keyboard = types.ReplyKeyboardRemove()
                        # await message.send(" ", )
                        await message.answer("Telefon raqamingiz qabul qilindi. Telefon raqamingizga yuborilgan kodni yuboring",reply_markup=remove_keyboard)
                        # , reply_markup=reset_password)
                        
                        await PersonalData.secret_code.set()
                if str(check_user.json()) == 'False':
                    await state.update_data(phone=phone_num)
                    user_register = send_req.user_register(custom_phone)
                    print('user_register', user_register.json())
                    if user_register.status_code == 201:
                        remove_keyboard_ = types.ReplyKeyboardRemove()
                        await message.answer("Telefon raqamingiz qabul qilindi. Telefon raqamingizga yuborilgan kodni yuboring", reply_markup=remove_keyboard_)
                        await PersonalData.secret_code.set()


@dp.message_handler(state=PersonalData.secret_code)
async def secret_code(message: types.Message, state: FSMContext):
    secret_code = message.text
    await state.update_data(secret_code=secret_code)
    await message.answer("Kod qabul qilindi")
    await message.answer("Passport seriyangizni yuboring")
    await PersonalData.document.set()

@dp.message_handler(state=PersonalData.document)
async def document(message: types.Message, state: FSMContext):
    document = message.text
    await state.update_data(document=document)
    await message.answer('Tug\'ilgan kuningingizni yuboring quidagi formatda\nkun.oy.yil')
    await PersonalData.birth_date.set()

@dp.message_handler(state=PersonalData.birth_date)
async def birth_date(message: types.Message, state: FSMContext):
    birth_date = message.text
    await state.update_data(birth_date=birth_date)
    await message.answer('Tu\'gilgan kuningiz qabul qilindi. Ma\'lumotlaringiz muvaffaqiyatli saqlandi.')
    await state.finish()
