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
    school = State()

    class_letter = State()
    
    exam_lang = State()         
    second_subject = State()     
    verify = State()             
    gender = State()