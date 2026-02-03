from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

language_keyboard_button = InlineKeyboardMarkup(row_width=2).add(
    InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="uz"),
    InlineKeyboardButton(text="🇷🇺 Русский", callback_data="ru")
)



_GENDER_TEXT = {
    "uz": {"male": "Erkak", "female": "Ayol"},
    "ru": {"male": "Мужчина", "female": "Женщина"},
    "en": {"male": "Male", "female": "Female"},
}

def gender_kb(ui_lang: str) -> InlineKeyboardMarkup:
    lang = ui_lang if ui_lang in _GENDER_TEXT else "uz"

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(text=_GENDER_TEXT[lang]["male"], callback_data="gender:male"),
        InlineKeyboardButton(text=_GENDER_TEXT[lang]["female"], callback_data="gender:female"),
    )
    return kb
