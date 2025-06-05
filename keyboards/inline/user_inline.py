from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from data.config import main_url

# def shortify_url(orginal_url):
#     short_url = shorten_url(orginal_url)
#     return short_url
def share_button(token, refresh_token):
    share_button = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton(
            text="🔗 Hujjat topshirish",
            url=f"https://mentalaba.uz/application?from_bot={token}&from_bot_refresh={refresh_token}"
        )
    )
    return share_button

gender_button = InlineKeyboardMarkup(row_width=2).add(
    InlineKeyboardButton(text="👨 Erkak", callback_data="male"),
    InlineKeyboardButton(text="👩 Ayol", callback_data="female")
)