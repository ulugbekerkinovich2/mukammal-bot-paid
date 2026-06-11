from aiogram.dispatcher.filters.state import State, StatesGroup


class V2Form(StatesGroup):
    phone = State()
    fio = State()
    university = State()
