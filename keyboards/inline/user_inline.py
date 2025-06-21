from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from data.config import main_url
from utils.send_req import shorten_url_async
async def shortify_url(orginal_url):
    short_url = await shorten_url_async(orginal_url)
    return short_url['short_url']
async def share_button(auth_key, chat_id):
    # org_url = f"https://mentalaba.uz/application?from_bot={token}&from_bot_refresh={refresh_token}"
    org_url = f"https://mentalaba.uz/application?auth_key={auth_key}"
    short_url = await shortify_url(org_url)
    # print(short_url)
    # share_button = InlineKeyboardMarkup(row_width=1).add(
    #     # InlineKeyboardButton(
    #     #     text="🔗 Hujjat topshirish",
    #     #     url=org_url
    #     # )
    #     InlineKeyboardButton(
    #         text="🔗 Hujjat topshirish",
    #         callback_data=f"submit:{chat_id}:{token}:{refresh_token}"
    #     )
    share_button = InlineKeyboardMarkup(row_width=1).add(
    InlineKeyboardButton(
        text="🔗 Hujjat topshirish",
        callback_data=f"submit:{chat_id}",
        url=org_url
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

forget_password_button = InlineKeyboardMarkup(row_width=1).add(
    InlineKeyboardButton(text="🔓 Parolni tiklash", callback_data="forget_password")
)