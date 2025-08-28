from aiogram.dispatcher.filters import Command, Text
from aiogram.types import Message, ReplyKeyboardRemove, KeyboardButton,ReplyKeyboardMarkup,InlineKeyboardButton,InlineKeyboardMarkup
# from keyboards.default.registerKeyBoardButton import menu, menu_full, application, ask_delete_account,exit_from_account, update_personal_info,finish_edit,update_education_info
# from keyboards.inline.menukeyboards import update_personal_info_inline,edit_user_education_inline,edit_user_education_transfer_inline
import datetime
import re
from keyboards.default.userKeyboard import keyboard_user, adminKeyboard_user
from loader import dp
from utils import send_req
from aiogram import types
from aiogram.dispatcher import FSMContext
from icecream import ic
from states.advertiser_command import NewAdsState
# from utils.send_req import grant_languages, grant_directions, grant_applicant
# from handlers.users.register import saved_message,select_region,type_your_edu_name,example_diploma_message,wait_file_is_loading,select_type_certificate,example_certification_message,not_found_country,search_university,select_one
start_button = KeyboardButton('/start')  # The text on the button
start_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True).add(start_button)
# escape_markdown = send_req.escape_markdown
# convert_time = send_req.convert_time
from keyboards.default import adminMenuKeyBoardButton
from loader import dp, bot
import asyncio
from keyboards.default.adminMenuKeyBoardButton import adminMenu
from data.config import ADMINS

@dp.message_handler(Text(equals='📊 Admin Panel'), state='*')
async def admin_command(message: types.Message, state: FSMContext):
    print(message.from_user.id)
    if str(message.from_user.id) not in ADMINS:
        return
    await message.answer("📊 Admin Panel", reply_markup=adminMenu)

@dp.message_handler(Text(equals='📢 Reklama yuborish'), state='*')
async def admin_commandAds(message: types.Message, state: FSMContext):
    if str(message.from_user.id) not in ADMINS:
        return
    await state.finish()
    await message.answer(
        "Reklama paneli.\nIltimos, kanal post linkini yuboring (https://t.me/kanal_username/post_id)",
        reply_markup=None
    )
    await NewAdsState.post_url.set()

# Post linkini qabul qilish
@dp.message_handler(state=NewAdsState.post_url)
async def get_post_url(message: types.Message, state: FSMContext):
    if str(message.from_user.id) not in ADMINS:
        return

    post_url = message.text.strip()
    match = re.search(r't.me/([^/]+)/(\d+)', post_url)
    if not match:
        await message.reply("URL noto'g'ri formatda! Iltimos, to'g'ri link yuboring.")
        return

    channel_username = f"@{match.group(1)}"
    post_id = int(match.group(2))

    await state.update_data(post_data={"channel": channel_username, "post_id": post_id})

    # Tasdiqlash tugmalari
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("✅ Tasdiqlash", callback_data="confirm_post"))
    keyboard.add(InlineKeyboardButton("❌ Bekor qilish", callback_data="cancel_post"))

    await message.answer(f"Postni yuborishni tasdiqlaysizmi?", reply_markup=keyboard)
    await NewAdsState.confirm_post.set()

# Callback handler: tasdiqlash yoki bekor qilish
@dp.callback_query_handler(lambda c: c.data in ["confirm_post", "cancel_post"], state=NewAdsState.confirm_post)
async def send_post_to_users(callback_query: types.CallbackQuery, state: FSMContext):
    ic('getting post')
    data = await state.get_data()

    if callback_query.data == "cancel_post":
        await callback_query.message.edit_text("Yuborish bekor qilindi.")
        await state.finish()
        return

    channel = data["post_data"]["channel"]
    post_id = data["post_data"]["post_id"]

    all_users = send_req.get_all_users()  # foydalanuvchi ro'yxati [{chat_id:...}, ...]
    count, failed = 0, 0

    for idx, user in enumerate(all_users, start=1):
        try:
            await bot.forward_message(
                chat_id=user['chat_id'],
                from_chat_id=channel,
                message_id=post_id
            )
            count += 1
            ic(f"User {user['chat_id']} ga yuborildi")
        except Exception as e:
            failed += 1
            print(f"User {user['chat_id']} ga yuborilmadi: {e}")

        # har 100 tadan keyin 1 sekund kutish
        if idx % 100 == 0:
            await asyncio.sleep(1)

    await callback_query.message.edit_text(
        f"📢 Post foydalanuvchilarga yuborish tugadi ✅\n\n"
        f"✅ Yuborilganlar: {count}\n"
        f"❌ Yuborilmaganlar: {failed}\n"
        f"👥 Jami: {len(all_users)}"
    )
    await state.finish()



@dp.message_handler(text="📊 Statistika")  # Assuming you have a function or logic to check if the user is an admin
async def bot_starts(message: types.Message, state: FSMContext):
    await state.finish()
    time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count_of_users = send_req.get_all_users()
    active = 0
    blocked = 0
    for user in count_of_users:
        if user['status'] == 'active':
            active += 1
        elif user['status'] == 'blocked':
            blocked += 1
    response_message = (
        f"📊 <b>Bot foydalanuvchi statistikasi</b>\n\n"
        f"📅 Sana: <b>{time}</b>\n"
        f"👥 Umumiy foydalanuvchilar: <b>{len(count_of_users):,}</b> ta\n"
        f"✅ Aktiv foydalanuvchilar: <b>{active:,}</b> ta\n"
        f"🚫 Bloklangan foydalanuvchilar: <b>{blocked:,}</b> ta"
    )
    await message.answer(response_message)

@dp.message_handler(Text(equals='🔙 Orqaga'), state='*')
async def admin_commandBack(message: types.Message, state: FSMContext):
    await state.finish()
    ic('admin command')
    user_id = str( message.from_user.id)
    if user_id not in ADMINS:
        return
    if user_id in ADMINS:
        await message.answer("Admin Reklama paneliga xush kelibsiz", reply_markup=adminKeyboard_user)
    else:
        await message.answer("Admin Reklama paneliga xush kelibsiz", reply_markup=keyboard_user)