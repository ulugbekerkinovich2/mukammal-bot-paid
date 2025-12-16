from aiogram.dispatcher.filters.state import StatesGroup, State

class Registration(StatesGroup):
    phone = State()
    fio = State()
    school_code = State()
    first_subject = State()
    second_subject = State()
    verify = State()