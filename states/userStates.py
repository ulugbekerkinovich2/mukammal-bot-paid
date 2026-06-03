from aiogram.dispatcher.filters.state import State, StatesGroup

class Registration(StatesGroup):
    ui_lang = State()            
    first_name = State()
    last_name = State()
    phone = State()
    fio = State()
    school_code = State()

    region = State()
    district = State()
    school_type = State()
    school = State()
    school_search = State()

    class_letter = State()
    
    exam_lang = State()
    second_subject = State()
    verify = State()
    gender = State()


class OnlineV2(StatesGroup):
    # v2 (reklama) oqim: bot fanlarni so'raydi → v2/start → WebApp test →
    # web_app_data → forma → v2/complete.
    first_subject = State()
    second_subject = State()
    in_test = State()        # WebApp test davom etmoqda (sendData kutilmoqda)
    full_name = State()
    phone = State()
    region = State()
    district = State()
    school = State()
    school_code = State()