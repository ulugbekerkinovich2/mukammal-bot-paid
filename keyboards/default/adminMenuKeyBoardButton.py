from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

adminMenu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text='📢 Reklama yuborish'),
            KeyboardButton(text='📊 Statistika'),
        ],
        [
            KeyboardButton(text='🧠 DTM javoblarni o‘qish'),
            KeyboardButton(text='📊 Mening natijam'),
        ],
        [
            # KeyboardButton(text='⚙️ Sozlamalar'),
            KeyboardButton(text='🔙 Orqaga')
        ],
    ],
    resize_keyboard=True
)

adsMenu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text='📹 Video yuborish'),
            # KeyboardButton(text='📝 Matn yuborish'),
            KeyboardButton(text='🖼 Rasm yuborish'),
        ],
        [
            KeyboardButton(text='🔙 Orqaga*'),
        ],
    ],
    resize_keyboard=True
)

adminConfirm = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text='✅ Yuborish'),
            KeyboardButton(text='❌ Bekor qilish'),
        ],
    ],
    resize_keyboard=True
)

adminKeyboard_user = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("📊 Admin Panel")],
        [KeyboardButton("📊 Mening natijam")],
        [KeyboardButton("📞Raqamni yuborish", request_contact=True)]
    ],
    resize_keyboard=True
)
