import logging
from typing import Iterable

from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware

logger = logging.getLogger(__name__)

# Callback data prefixlari — bu prefiksdagi callbacklar bossanga ham
# inline klaviaturani saqlab qolish kerak (handler o'zi edit qiladi).
# Hozircha kerak bo'lmasa bo'sh, kerak bo'lsa shu yerga qo'shing.
_KEEP_KB_PREFIXES: tuple = ()


def _should_keep(call_data: str, keep_prefixes: Iterable[str]) -> bool:
    if not call_data:
        return False
    return any(call_data.startswith(p) for p in keep_prefixes)


class InlineCleanupMiddleware(BaseMiddleware):
    """
    Inline tugma bosilishi bilan asl xabardagi reply_markup ni olib tashlaydi
    (oldindan), shu sababli foydalanuvchi eski tugmalarni qayta bosa olmaydi.

    Ishlash tartibi:
      - Telegram callback yuboradi.
      - Bu middleware *handler ishlamasdan oldin* xabardan klaviaturani
        olib tashlaydi.
      - Handler o'z ishini bajaradi (yangi xabar yuborish, edit_text bilan
        yangi klaviatura qo'yish va h.k.) — bu doim middleware'dan keyin
        ishlaydi, shuning uchun handler tomonidan o'rnatilgan klaviatura
        joyida qoladi.
    """

    def __init__(self, keep_prefixes: Iterable[str] = _KEEP_KB_PREFIXES):
        super().__init__()
        self._keep_prefixes = tuple(keep_prefixes)

    async def on_pre_process_callback_query(self, call: types.CallbackQuery, data: dict):
        message = call.message
        if not message:
            return
        if not getattr(message, "reply_markup", None):
            return
        if _should_keep(call.data or "", self._keep_prefixes):
            return
        try:
            await message.edit_reply_markup(reply_markup=None)
        except Exception as e:
            # Xabar bot tomonidan emas, eski (>48s), allaqachon o'chirilgan, va h.k.
            logger.debug("InlineCleanup edit_reply_markup skipped: %r", e)
