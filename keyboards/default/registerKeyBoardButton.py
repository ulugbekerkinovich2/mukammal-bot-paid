from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

reset_password = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text='Kodni qayta yuborish'),
        ],
    ],
    resize_keyboard=True
)

