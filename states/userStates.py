from aiogram.dispatcher.filters.state import State, StatesGroup

class Registration(StatesGroup):
    phone = State()
    fio = State()
    school_code = State()
    exam_lang = State()          # ✅ YANGI: imtihon tili tanlash
    second_subject = State()     # pair tanlash
    verify = State()
