from aiogram.dispatcher.filters.state import State, StatesGroup

class Registration(StatesGroup):
    ui_lang = State()            # ✅ YANGI: /start dan keyin UI tilini tanlash (uz/ru)

    phone = State()
    fio = State()
    school_code = State()

    exam_lang = State()          # ✅ Imtihon tili (uz/ru)
    second_subject = State()     # ✅ Juftlik tanlash (pair)
    verify = State()             # ✅ Tasdiqlash
