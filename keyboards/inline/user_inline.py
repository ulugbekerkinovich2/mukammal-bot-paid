from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from data.config import main_url
from utils.send_req import shorten_url_async
async def shortify_url(orginal_url):
    short_url = await shorten_url_async(orginal_url)
    return short_url['short_url']
async def share_button(token, refresh_token):
    short_url = await shortify_url(f"https://mentalaba.uz/application?from_bot={token}&from_bot_refresh={refresh_token}")
    print(short_url)
    share_button = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton(
            text="🔗 Hujjat topshirish",
            url=short_url
        )
    )
    return share_button

gender_button = InlineKeyboardMarkup(row_width=2).add(
    InlineKeyboardButton(text="👨 Erkak", callback_data="male"),
    InlineKeyboardButton(text="👩 Ayol", callback_data="female")
)

help_button = InlineKeyboardMarkup(row_width=1).add(
    InlineKeyboardButton(text="📝 Yordam", callback_data="help_uz"),
    InlineKeyboardButton(text="👤 Ma'lumotlarni qaytadan kitirish", callback_data="rewrite")
)