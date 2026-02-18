from aiogram.dispatcher.filters.state import State, StatesGroup


class AdminPanel(StatesGroup):
    menu = State()
    districts_list = State()
    schools_list = State()
