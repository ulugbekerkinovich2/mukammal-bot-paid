import asyncio

from aiogram import types, Dispatcher
from aiogram.dispatcher import DEFAULT_RATE_LIMIT
from aiogram.dispatcher.handler import CancelHandler, current_handler
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.utils.exceptions import Throttled
from aiogram.dispatcher import FSMContext

from utils.my_redis import redis
import json
from datetime import datetime

async def save_user_state(user_id: int, state: str, username: str = None, saved_at: str = None):
    key = f"user_id:{user_id}"
    timestamp = datetime.utcnow().isoformat()
    value = json.dumps({"state": state, "saved_at": saved_at, "username":username })
    await redis.set(key, value, ex=60*60*24*365)

class StateSaverMiddleware(BaseMiddleware):
    async def on_process_message(self, message: types.Message, data: dict):
        state: FSMContext = data.get('state')
        if not state:
            return
        current_state = await state.get_state()
        if current_state is None:
            return

        user_id = message.from_user.id
        await save_user_state(user_id, current_state)

class ThrottlingMiddleware(BaseMiddleware):
    """
    Simple middleware
    """

    def __init__(self, limit=DEFAULT_RATE_LIMIT, key_prefix='antiflood_'):
        self.rate_limit = limit
        self.prefix = key_prefix
        super(ThrottlingMiddleware, self).__init__()

    async def on_process_message(self, message: types.Message, data: dict):
        handler = current_handler.get()
        dispatcher = Dispatcher.get_current()
        if handler:
            limit = getattr(handler, "throttling_rate_limit", self.rate_limit)
            key = getattr(handler, "throttling_key", f"{self.prefix}_{handler.__name__}")
        else:
            limit = self.rate_limit
            key = f"{self.prefix}_message"
        try:
            await dispatcher.throttle(key, rate=limit)
        except Throttled as t:
            await self.message_throttled(message, t)
            raise CancelHandler()

    async def message_throttled(self, message: types.Message, throttled: Throttled):
        if throttled.exceeded_count <= 2:
            await message.reply("Too many requests!")
