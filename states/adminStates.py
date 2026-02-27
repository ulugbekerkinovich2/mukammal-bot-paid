from aiogram.dispatcher.filters.state import State, StatesGroup


class AdminPanel(StatesGroup):
    menu = State()
    districts_list = State()
    district_selected = State()
    schools_list = State()
    district_schools_list = State()