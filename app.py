# from aiogram import executor

# from loader import dp
# import middlewares, filters, handlers
# from utils.notify_admins import on_startup_notify
# from utils.set_bot_commands import set_default_commands
# from utils.send_req import startup, shutdown

# async def on_startup(dispatcher):
#     # Birlamchi komandalar (/star va /help)
#     await set_default_commands(dispatcher)

#     # Bot ishga tushgani haqida adminga xabar berish
#     await on_startup_notify(dispatcher)


# if __name__ == '__main__':
#     # executor.start_polling(dp, on_startup=on_startup)
#     executor.start_polling(dp, on_startup=lambda _: startup(), on_shutdown=lambda _: shutdown())
import logging
import re
from data.config import BOT_TOKEN


class _TokenMaskFilter(logging.Filter):
    """Log yozuvlaridan bot tokenni yashiradi."""
    _TOKEN_RE = re.compile(r'\d{5,12}:[A-Za-z0-9_-]{35,}')

    def __init__(self):
        super().__init__()
        self._literal = BOT_TOKEN or ""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if self._literal and self._literal in msg:
            record.msg = record.msg.replace(self._literal, "***")
            record.args = ()
        record.msg = self._TOKEN_RE.sub("***", str(record.msg))
        record.args = ()
        return True


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger().addFilter(_TokenMaskFilter())

from aiogram import executor

from loader import dp
import middlewares, filters, handlers
from utils.notify_admins import on_startup_notify
from utils.set_bot_commands import set_default_commands
from handlers.users.start import startup_register_services


async def on_startup(dispatcher):
    await set_default_commands(dispatcher)
    await on_startup_notify(dispatcher)
    await startup_register_services(dispatcher.bot, workers=2)

if __name__ == "__main__":
    # Telegram default allowed_updates inline_query'ni har doim ham yubormaydi
    # (avvalgi sessiya allowed_updates ni kesh qilib qo'ygan bo'lishi mumkin).
    # Inline mode ishlashi uchun aniq ko'rsatamiz.
    ALLOWED_UPDATES = [
        "message",
        "edited_message",
        "callback_query",
        "inline_query",
        "chosen_inline_result",
        "my_chat_member",
        "chat_member",
    ]
    executor.start_polling(
        dp,
        on_startup=on_startup,
        skip_updates=True,
        allowed_updates=ALLOWED_UPDATES,
    )