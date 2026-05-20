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
from data.config import ADMINS, TEST_MODE, TEST_CHAT_ID

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

    # sync requests — executor da bajariladi, event loop ni bloklamasin
    loop = asyncio.get_event_loop()
    all_users = await loop.run_in_executor(None, send_req.get_all_users)

    if not all_users:
        await callback_query.message.edit_text(
            "⚠️ <b>Foydalanuvchilar ro'yxatini olib bo'lmadi.</b>\n\n"
            "Ads service (<code>ads.misterdev.uz</code>) ulanmadi yoki bo'sh javob qaytardi.\n"
            "Iltimos, keyinroq qayta urinib ko'ring.",
            parse_mode="HTML"
        )
        await state.finish()
        return

    # ⚠️ LOCAL TEST MODE — .env da TEST_MODE=False qilib prodga chiqar
    if TEST_MODE and TEST_CHAT_ID:
        all_users = [u for u in all_users if int(u['chat_id']) == TEST_CHAT_ID]

    total = len(all_users)
    count, failed = 0, 0
    start_ts = datetime.datetime.now()

    progress_msg = await callback_query.message.edit_text(
        f"📢 <b>Yuborish boshlandi...</b>\n\n"
        f"👥 Jami: <b>{total:,}</b>\n"
        f"✅ Yuborilgan: <b>0</b>\n"
        f"❌ Xato: <b>0</b>\n"
        f"⏳ Progress: 0%",
        parse_mode="HTML"
    )

    last_edit = datetime.datetime.now()
    EDIT_EVERY_N = 25
    EDIT_EVERY_SEC = 2.5

    for idx, user in enumerate(all_users, start=1):
        try:
            await bot.forward_message(
                chat_id=user['chat_id'],
                from_chat_id=channel,
                message_id=post_id
            )
            count += 1
            send_req.update_user_status(user['chat_id'], user['bot_id'], "active")
            ic(f"User {user['chat_id']} ga yuborildi")
        except Exception as e:
            failed += 1
            ic(user)
            send_req.update_user_status(user['chat_id'], user['bot_id'], "blocked")
            print(f"User {user['chat_id']} ga yuborilmadi: {e}")

        now = datetime.datetime.now()
        time_since_edit = (now - last_edit).total_seconds()
        if idx == total or (idx % EDIT_EVERY_N == 0 and time_since_edit >= EDIT_EVERY_SEC):
            elapsed = (now - start_ts).total_seconds()
            rate = idx / elapsed if elapsed > 0 else 0
            remaining = (total - idx) / rate if rate > 0 else 0
            percent = (idx / total * 100) if total else 100
            try:
                await progress_msg.edit_text(
                    f"📢 <b>Yuborilmoqda...</b>\n\n"
                    f"👥 Jami: <b>{total:,}</b>\n"
                    f"✅ Yuborilgan: <b>{count:,}</b>\n"
                    f"❌ Xato: <b>{failed:,}</b>\n"
                    f"📈 Ishlangan: <b>{idx:,}/{total:,}</b> ({percent:.1f}%)\n"
                    f"⚡ Tezlik: <b>{rate:.1f}</b> msg/s\n"
                    f"⏱ O'tgan vaqt: <b>{int(elapsed)}s</b>\n"
                    f"⏳ Qolgan (taxminiy): <b>{int(remaining)}s</b>",
                    parse_mode="HTML"
                )
                last_edit = now
            except Exception as e:
                ic(f"progress edit fail: {e}")

        if idx % 100 == 0:
            await asyncio.sleep(1)

    elapsed_total = (datetime.datetime.now() - start_ts).total_seconds()
    try:
        await progress_msg.edit_text(
            f"📢 <b>Post yuborish tugadi</b> ✅\n\n"
            f"👥 Jami: <b>{total:,}</b>\n"
            f"✅ Yuborilganlar: <b>{count:,}</b>\n"
            f"❌ Yuborilmaganlar: <b>{failed:,}</b>\n"
            f"⏱ Umumiy vaqt: <b>{int(elapsed_total)}s</b>",
            parse_mode="HTML"
        )
    except Exception as e:
        ic(f"final edit fail: {e}")
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