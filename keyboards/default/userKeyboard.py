from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

keyboard_user = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("📞Raqamni yuborish", request_contact=True)]
    ],
    resize_keyboard=True

)

adminKeyboard_user = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("📊 Admin Panel")],
        [KeyboardButton("📞Raqamni yuborish", request_contact=True)]
    ],
    resize_keyboard=True
)

strong_pass = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("🔑 Kuchli parol yaratish")]
    ],
    resize_keyboard=True
)

continue_button = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("Davom etish")]
    ],
    resize_keyboard=True
)

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

restart_markup = ReplyKeyboardMarkup(resize_keyboard=True)
restart_markup.add(KeyboardButton("/start"))