import asyncio
import logging
from typing import Iterable

from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware

logger = logging.getLogger(__name__)

# Faqat shu prefiks(lar) bilan boshlanuvchi callbacklar uchun klaviatura
# olib tashlanadi. Bu — eski/cache xavfi bor bo'lgan tugmalar (offline
# tugmasi yashirilgan, lekin user eski xabardagi tugmani bosishi mumkin).
# Boshqa callbacklar uchun handler o'zi xabarni edit/delete qiladi —
# shuning uchun bu middleware ularda ortiqcha API chaqiruvi qilmaydi.
_STALE_PREFIXES: tuple = (
    "pre_choose_",
    "test_type_offline",
)


def _matches_any(call_data: str, prefixes: Iterable[str]) -> bool:
    if not call_data:
        return False
    return any(call_data.startswith(p) for p in prefixes)


class InlineCleanupMiddleware(BaseMiddleware):
    """
    Eski/stale inline tugmalarni darhol o'chirib qo'yadi (chat tarixida
    qolgan tugma user qayta bosa olmasin uchun).

    Performance: barcha callbacklar uchun emas, faqat _STALE_PREFIXES
    ro'yxatidagi callbacklar uchun ishlaydi — qolganlarni handler o'zi
    edit qiladi, shuning uchun ortiqcha API chaqiruv yo'q.

    Strip operatsiyasi `asyncio.create_task` orqali fonda ishga tushadi —
    handler kutmasdan davom etadi, shu sababli flow tezligi tushmaydi.
    """

    def __init__(self, stale_prefixes: Iterable[str] = _STALE_PREFIXES):
        super().__init__()
        self._stale_prefixes = tuple(stale_prefixes)

    async def on_pre_process_callback_query(self, call: types.CallbackQuery, data: dict):
        message = call.message
        if not message:
            return
        if not getattr(message, "reply_markup", None):
            return
        if not _matches_any(call.data or "", self._stale_prefixes):
            return

        async def _strip() -> None:
            try:
                await message.edit_reply_markup(reply_markup=None)
            except Exception as e:
                logger.debug("InlineCleanup edit_reply_markup skipped: %r", e)

        asyncio.create_task(_strip())
