from aiogram.dispatcher.filters.state import StatesGroup, State

class PersonalData(StatesGroup):
    phone = State()
    secret_code = State()
    document = State()
    birth_date = State()
    

