from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

from data.config import WEBAPP_URL

keyboard_user = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("📞Raqamni yuborish", request_contact=True)],
        [KeyboardButton("📊 Mening natijam")],
        [KeyboardButton("📝 Online test", web_app=WebAppInfo(url=WEBAPP_URL))],
    ],
    resize_keyboard=True

)


continue_button = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("Davom etish")]
    ],
    resize_keyboard=True
)

restart_markup = ReplyKeyboardMarkup(resize_keyboard=True)
restart_markup.add(KeyboardButton("/start"))


adminKeyboard_user = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("📊 Admin Panel")],
        [KeyboardButton("📞Raqamni yuborish", request_contact=True)],
        [KeyboardButton("📊 Mening natijam")],
        [KeyboardButton("📝 Online test", web_app=WebAppInfo(url=WEBAPP_URL))],
    ],
    resize_keyboard=True
)
