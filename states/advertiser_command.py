from aiogram.dispatcher.filters.state import StatesGroup, State



class User(StatesGroup):
    get_command = State()
    send_message = State()
    image = State()
    text = State()
    reklama_admin_image_all = State()
    reklama_admin_image_text_for_admins = State()
    reklama_admin_video_or_image_all = State()
    photo_broadcast = State()
    confirm_reklama = State()

# class User(StatesGroup):
#     reklama_admin_video_or_image_all = State()
#     confirm_reklama = State()


class GranState(StatesGroup):
    direction = State()
    after_lang = State()
    language = State()

class NewAdsState(StatesGroup):
    post_url = State()
    confirm_post = State()