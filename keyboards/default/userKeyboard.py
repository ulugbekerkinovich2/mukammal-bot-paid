from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

keyboard_user = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("📞Raqamni yuborish", request_contact=True)],
        [KeyboardButton("📊 Mening natijam")],
    ],
    resize_keyboard=True,
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
    ],
    resize_keyboard=True,
)
