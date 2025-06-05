from aiogram.dispatcher.filters.state import StatesGroup, State

class Registration(StatesGroup):
    phone = State()
    register = State()
    password = State()
    login = State()
    verify = State()
    pinfl = State()
    birth_date = State()

class FullRegistration(StatesGroup):
    profile_image = State()
    surename = State()
    first_name = State()
    third_name = State()
    gender = State()
    birth_place = State()
    passport_image1 = State()
    passport_image2 = State()
    extra_phone = State()
    edu_place = State()
    select_edu_plase = State()
    district_place = State()
    edu_name = State()
    select_edu_name = State()
    ended_year = State()
    diplom_file = State()
    
