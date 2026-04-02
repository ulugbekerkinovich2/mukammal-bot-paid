from aiogram.dispatcher.filters import Command, Text
from aiogram.types import Message, ReplyKeyboardRemove, KeyboardButton,ReplyKeyboardMarkup,InlineKeyboardButton,InlineKeyboardMarkup
# from keyboards.default.registerKeyBoardButton import menu, menu_full, application, ask_delete_account,exit_from_account, update_personal_info,finish_edit,update_education_info
# from keyboards.inline.menukeyboards import update_personal_info_inline,edit_user_education_inline,edit_user_education_transfer_inline
import datetime
import html
import io
import re
import time
from keyboards.default.userKeyboard import keyboard_user, adminKeyboard_user
from loader import dp
from utils import send_req
from aiogram import types
from aiogram.dispatcher import FSMContext
# from icecream import ic
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
from data.config import ADMINS, ADMIN_CHAT_IDs


def _parse_admin_ids(*values) -> set:
    ids = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, int):
            ids.add(str(value))
            continue
        if isinstance(value, (list, tuple, set)):
            for item in value:
                s = str(item).strip()
                if s:
                    ids.add(s)
            continue
        s = str(value).strip()
        if s:
            ids.add(s)
    return ids


ADMIN_ACCESS_IDS = _parse_admin_ids(ADMINS, ADMIN_CHAT_IDs)


def _is_admin(message_user_id: int) -> bool:
    return str(message_user_id) in ADMIN_ACCESS_IDS


def _guess_image_content_type(filename: str, mime_type: str = "") -> str:
    mime = (mime_type or "").lower()
    if mime in {"image/jpeg", "image/jpg", "image/png"}:
        return "image/jpeg" if mime == "image/jpg" else mime

    lower_name = (filename or "").lower()
    if lower_name.endswith(".png"):
        return "image/png"
    return "image/jpeg"


def _extract_dtm_image_meta(message: types.Message):
    file_id = None
    filename = "sheet.jpg"
    mime_type = "image/jpeg"

    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document:
        mime_type = (message.document.mime_type or "").lower()
        if not mime_type.startswith("image/"):
            return None
        file_id = message.document.file_id
        if message.document.file_name:
            filename = message.document.file_name

    if not file_id:
        return None

    return {
        "dtm_file_id": file_id,
        "dtm_filename": filename,
        "dtm_content_type": _guess_image_content_type(filename, mime_type),
    }


async def _send_dtm_read_result(message: types.Message, payload: dict):
    def fix_url(url):
        if url and "127.0.0.1:8000" in str(url):
            return str(url).replace("http://127.0.0.1:8000", "https://dtmpaperreaderapi.mentalaba.uz")
        return url

    upload_image_fixed = fix_url(payload.get("upload_image", "-"))
    pdf_file_fixed = fix_url(payload.get("pdf_file", "-"))
    
    upload_image = html.escape(str(upload_image_fixed))
    pdf_file = html.escape(str(pdf_file_fixed))
    
    total_point = payload.get("total_point", "-")
    updated_answers = payload.get("updated_answers", "-")
    total_detected = payload.get("total_detected", "-")
    book_id = payload.get("book_id", "-")
    detail_point = payload.get("detail_point") or {}
    image_link = f'<a href="{upload_image}">Rasmni ochish</a>' if str(upload_image_fixed).startswith("http") else upload_image
    pdf_link = f'<a href="{pdf_file}">PDFni ochish</a>' if str(pdf_file_fixed).startswith("http") else pdf_file

    summary = (
        "✅ <b>DTM natija tayyor</b>\n\n"
        f"🆔 <b>Book ID:</b> <code>{book_id}</code>\n"
        f"📊 <b>Umumiy ball:</b> <code>{total_point}</code>\n\n"
        "📈 <b>Ball tafsiloti</b>\n"
        f"Majburiy: <code>{detail_point.get('mandatory', '-')}</code>\n"
        f"Asosiy: <code>{detail_point.get('primary', '-')}</code>\n"
        f"Ikkinchi fan: <code>{detail_point.get('secondary', '-')}</code>\n\n"
        "📌 <b>Statistika</b>\n"
        f"Yangilangan javoblar: <code>{updated_answers}</code>\n"
        f"Aniqlangan jami: <code>{total_detected}</code>\n\n"
        f"🔗 {image_link} | {pdf_link}"
    )
    await message.answer(summary, reply_markup=adminMenu, disable_web_page_preview=True)

@dp.message_handler(Text(equals='📊 Admin Panel'), state='*')
async def admin_command(message: types.Message, state: FSMContext):
    print(message.from_user.id)
    if not _is_admin(message.from_user.id):
        return
    await message.answer("📊 Admin Panel", reply_markup=adminMenu)

@dp.message_handler(Text(equals='📢 Reklama yuborish'), state='*')
async def admin_commandAds(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
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
    if not _is_admin(message.from_user.id):
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
    # ic('getting post')
    data = await state.get_data()

    if callback_query.data == "cancel_post":
        await callback_query.message.edit_text("Yuborish bekor qilindi.")
        await state.finish()
        return

    channel = data["post_data"]["channel"]
    post_id = data["post_data"]["post_id"]

    all_users = send_req.get_all_users()  # foydalanuvchi ro'yxati [{chat_id:...}, ...]
    # print(all_users)
    # time.sleep(10)
    count, failed = 0, 0

    for idx, user in enumerate(all_users, start=1):
        chat_id = user['chat_id']
        print(91, chat_id)
        if chat_id == "935920479":
        # if bot_id != 8:
        #     continue
            try:

                await bot.forward_message(
                    chat_id=user['chat_id'],
                    from_chat_id=channel,
                    message_id=post_id
                )
                count += 1
                # updated = send_req.update_user(user['id'], user['chat_id'],user['firstname'], user['lastname'],user['bot_id'],user['username'],"active",user['created_at'])
                send_req.update_user_status(user['chat_id'], user['bot_id'], "active")
                # ic(f"User {user['chat_id']} ga yuborildi")
            except Exception as e:
                failed += 1
                # ic(user)
                send_req.update_user_status(user['chat_id'], user['bot_id'], "blocked")
                # updated = send_req.update_user(user['id'], user['chat_id'],user['firstname'], user['lastname'],user['bot_id'],user['username'],"blocked",user['created_at'])
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


@dp.message_handler(Text(equals='🧠 DTM javoblarni o‘qish'), state='*')
async def start_dtm_read(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    await state.finish()
    await message.answer(
        "Rasmni yuboring. Foto yoki image document bo‘lishi mumkin.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await NewAdsState.dtm_read_image.set()


@dp.message_handler(content_types=[types.ContentType.PHOTO, types.ContentType.DOCUMENT], state='*')
async def catch_admin_dtm_image_anytime(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    meta = _extract_dtm_image_meta(message)
    if not meta:
        return

    await state.update_data(**meta)
    await message.answer(
        "Rasm qabul qilindi. Endi `book_id` ni yuboring. Faqat raqam bo‘lsin.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    await NewAdsState.dtm_read_book_id.set()


@dp.message_handler(content_types=[types.ContentType.PHOTO, types.ContentType.DOCUMENT], state=NewAdsState.dtm_read_image)
async def get_dtm_read_image(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    meta = _extract_dtm_image_meta(message)
    if not meta:
        await message.answer("Rasm topilmadi. Qayta yuboring.")
        return

    await state.update_data(**meta)
    await message.answer("Endi `book_id` ni yuboring. Faqat raqam bo‘lsin.", parse_mode="Markdown")
    await NewAdsState.dtm_read_book_id.set()


@dp.message_handler(state=NewAdsState.dtm_read_image)
async def invalid_dtm_read_image(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await message.answer("Avval rasm yuboring.")


@dp.message_handler(state=NewAdsState.dtm_read_book_id)
async def submit_dtm_read_request(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    book_id = (message.text or "").strip()
    if not book_id.isdigit():
        await message.answer("`book_id` faqat son bo‘lishi kerak.", parse_mode="Markdown")
        return

    data = await state.get_data()
    file_id = data.get("dtm_file_id")
    filename = data.get("dtm_filename") or "sheet.jpg"
    content_type = data.get("dtm_content_type") or _guess_image_content_type(filename)
    if not file_id:
        await message.answer("Rasm topilmadi. Qaytadan boshlang.", reply_markup=adminMenu)
        await state.finish()
        return

    await message.answer("⏳ API ga yuboryapman, biroz kuting...")

    telegram_file = await bot.get_file(file_id)
    file_buffer = io.BytesIO()
    await bot.download_file(telegram_file.file_path, destination=file_buffer)
    image_bytes = file_buffer.getvalue()

    res = await send_req.submit_dtm_read(
        image_bytes=image_bytes,
        filename=filename,
        book_id=book_id,
        content_type=content_type,
    )

    if not res.get("ok"):
        err_text = str(res.get("text", "Noma'lum xato"))[:3000]
        await message.answer(
            f"❌ API xato\n\nStatus: <code>{res.get('status')}</code>\n<code>{err_text}</code>",
            reply_markup=adminMenu,
        )
        await state.finish()
        return

    payload = res.get("data")
    if not isinstance(payload, dict):
        await message.answer("❌ API noto‘g‘ri format qaytardi.", reply_markup=adminMenu)
        await state.finish()
        return

    await _send_dtm_read_result(message, payload)
    await state.finish()



@dp.message_handler(text="📊 Statistika")  # Assuming you have a function or logic to check if the user is an admin
async def bot_starts(message: types.Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
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
    # ic('admin command')
    user_id = str( message.from_user.id)
    if not _is_admin(message.from_user.id):
        return
    if _is_admin(message.from_user.id):
        await message.answer("Admin Reklama paneliga xush kelibsiz", reply_markup=adminKeyboard_user)
    else:
        await message.answer("Admin Reklama paneliga xush kelibsiz", reply_markup=keyboard_user)
