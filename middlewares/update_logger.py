import logging
from typing import Any

from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware

logger = logging.getLogger("update_logger")


def _summarize(update: types.Update) -> str:
    """Update'ning eng muhim qismini bitta qator sifatida qaytaradi."""
    try:
        if update.message:
            m = update.message
            user = m.from_user
            text = (m.text or m.caption or f"<{m.content_type}>")[:60]
            return (
                f"MESSAGE from={user.id if user else '?'} "
                f"chat={m.chat.id} text={text!r}"
            )
        if update.callback_query:
            cq = update.callback_query
            return (
                f"CALLBACK from={cq.from_user.id} "
                f"data={(cq.data or '')[:80]!r}"
            )
        if update.inline_query:
            iq = update.inline_query
            return (
                f"INLINE_QUERY from={iq.from_user.id} "
                f"query={(iq.query or '')[:80]!r} offset={iq.offset!r}"
            )
        if update.chosen_inline_result:
            cir = update.chosen_inline_result
            return (
                f"CHOSEN_INLINE from={cir.from_user.id} "
                f"result_id={cir.result_id!r} query={(cir.query or '')[:80]!r}"
            )
        if update.edited_message:
            em = update.edited_message
            return f"EDITED_MESSAGE from={em.from_user.id if em.from_user else '?'}"
        if update.my_chat_member:
            return "MY_CHAT_MEMBER update"
        if update.chat_member:
            return "CHAT_MEMBER update"
        return f"OTHER update_id={update.update_id}"
    except Exception as e:
        return f"<summarize failed: {e!r}>"


class UpdateLoggerMiddleware(BaseMiddleware):
    """
    Telegram'dan kelgan har bir update'ni bitta INFO log qatori qilib yozadi.
    Diagnostika uchun: agar pm2 logsda INLINE_QUERY ko'rinmasa, Telegram inline
    update'larni bot'ga yubormayapti (BotFather /setinline yoki allowed_updates
    muammosi).
    """

    async def on_pre_process_update(self, update: types.Update, data: dict):
        logger.info("[UPDATE] %s", _summarize(update))
