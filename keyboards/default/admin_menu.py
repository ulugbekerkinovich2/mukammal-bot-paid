from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def kb_admin_start():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🛠 Admin"))
    kb.add(KeyboardButton("📝 Ro‘yxatdan o‘tish"))
    return kb


def kb_admin_only():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🛠 Admin"))
    return kb
