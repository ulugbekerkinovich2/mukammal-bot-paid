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
    "Matematika": {
        "id": 20,
        "ru": "Математика",
        "relative": {
            "uz": ["Fizika", "Geografiya", "Ingliz tili", "Ona tili va adabiyot"],
            "ru": ["Физика", "География", "Английский язык", "Родной язык и литература"],
        },
    },
    "Fizika": {
        "id": 24,
        "ru": "Физика",
        "relative": {
            "uz": ["Matematika", "Ingliz tili"],
            "ru": ["Математика", "Английский язык"],
        },
    },
    "Geografiya": {
        "id": 25,
        "ru": "География",
        "relative": {
            "uz": ["Matematika"],
            "ru": ["Математика"],
        },
    },
    "Ingliz tili": {
        "id": 23,
        "ru": "Английский язык",
        "relative": {
            "uz": ["Matematika", "Ona tili va adabiyot"],
            "ru": ["Математика", "Родной язык и литература"],
        },
    },
    "Ona tili va adabiyot": {
        "id": 27,
        "ru": "Родной язык и литература",
        "relative": {
            "uz": ["Matematika", "Ingliz tili", "Biologiya"],
            "ru": ["Математика", "Английский язык", "Биология"],
        },
    },
    "Tarix": {
        "id": 26,
        "ru": "История",
        "relative": {
            "uz": ["Matematika", "Geografiya", "Ingliz tili", "Ona tili va adabiyot"],
            "ru": ["Математика", "География", "Английский язык", "Родной язык и литература"],
        },
    },
    "Biologiya": {
        "id": 6,
        "ru": "Биология",
        "relative": {
            "uz": ["Kimyo", "Ona tili va adabiyot"],
            "ru": ["Химия", "Родной язык и литература"],
        },
    },
    "Kimyo": {
        "id": 7,
        "ru": "Химия",
        "relative": {
            "uz": ["Biologiya", "Matematika"],
            "ru": ["Биология", "Математика"],
        },
    },
}
