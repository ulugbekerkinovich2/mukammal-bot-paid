from environs import Env

# environs kutubxonasidan foydalanish
env = Env()
env.read_env()

# .env fayl ichidan quyidagilarni o'qiymiz
BOT_TOKEN = env.str("BOT_TOKEN")  # Bot toekn
ADMINS = env.list("ADMINS")  # adminlar ro'yxati
IP = env.str("ip")  # Xosting ip manzili
# main_url = env.str("base_url")
# CHANNEL_ID = env.str('CHANNEL_ID')

SUBJECTS_MAP = {
    "Fizika": {
        "id": 100,
        "ru": "Физика",
        "relative": {
            "uz": ["Matematika", "Ingliz tili"],
            "ru": ["Математика", "Английский язык"],
        },
    },
    "Tarix": {
        "id": 101,
        "ru": "История",
        "relative": {
            "uz": ["Matematika", "Geografiya", "Ingliz tili", "Ona tili va adabiyot"],
            "ru": ["Математика", "География", "Английский язык", "Родной язык и литература"],
        },
    },
    "Matematika": {
        "id": 102,
        "ru": "Математика",
        "relative": {
            "uz": ["Fizika", "Geografiya", "Ingliz tili", "Ona tili va adabiyot"],
            "ru": ["Физика", "География", "Английский язык", "Родной язык и литература"],
        },
    },
    "Geografiya": {
        "id": 103,
        "ru": "География",
        "relative": {
            "uz": ["Matematika"],
            "ru": ["Математика"],
        },
    },
    "Ingliz tili": {
        "id": 104,
        "ru": "Английский язык",
        "relative": {
            "uz": ["Ona tili va adabiyot"],
            "ru": ["Родной язык и литература"],
        },
    },
    "Ona tili va adabiyot": {
        "id": 105,
        "ru": "Родной язык и литература",
        "relative": {
            "uz": ["Matematika", "Ingliz tili"],
            "ru": ["Математика", "Английский язык"],
        },
    },
    "Biologiya": {
        "id": 106,
        "ru": "Биология",
        "relative": {
            "uz": ["Ona tili va adabiyot", "Kimyo"],
            "ru": ["Родной язык и литература", "Химия"],
        },
    },
    "Kimyo": {
        "id": 107,
        "ru": "Химия",
        "relative": {
            "uz": ["Matematika", "Biologiya"],
            "ru": ["Математика", "Биология"],
        },
    },
}
