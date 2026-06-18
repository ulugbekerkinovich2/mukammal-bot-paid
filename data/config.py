from environs import Env

# environs kutubxonasidan foydalanish
env = Env()
env.read_env()

BOT_TOKEN = env.str("BOT_TOKEN")
ADMINS = env.list("ADMINS")
IP = env.str("ip")
CHANNEL_ID = env.str("CHANNEL_ID")
ADMIN_CHAT_ID = env.str("ADMIN_CHAT_ID")
ADMIN_CHAT_IDs = env.list("ADMIN_CHAT_IDs")
CHANNEL_USERNAME = env.str("CHANNEL_USERNAME")
CHANNEL_LINK = env.str("CHANNEL_LINK")
BASE_URL = env.str("BASE_URL")
BASE_URL_2 = env.str("BASE_URL_2", "")
REDIS_URL = env.str("REDIS_URL")
SECRET_KEY = env.str("SECRET_KEY")
RESULTS_FILE_PATH = env.str("RESULTS_FILE_PATH", "data/natijalar.xlsx")
WEBAPP_URL = env.str("WEBAPP_URL", "https://dtm.your-domain.uz/online-test/")
# v2 (reklama) WebApp — fan tanlash + test WebApp ichida. Bo'sh bo'lsa,
# WEBAPP_URL'ga ?v2=1 qo'shib quriladi (handlers/users/start.py: v2_webapp_url).
V2_WEBAPP_URL = env.str("V2_WEBAPP_URL", "")
# true bo'lsa HAR QANDAY /start v2 oqimiga ketadi (deep-link shart emas).
# false (default) — faqat /start v2 deep-link'da v2, oddiy /start eski v1.
V2_FOR_ALL = env.bool("V2_FOR_ALL", False)
# v2 endpoint'lari uchun alohida API host (bo'sh bo'lsa BASE_URL ishlatiladi).
V2_API_BASE = env.str("V2_API_BASE", "")

# mentalaba offline-test-results API (sertifikat). Natija chiqqach POST qilinadi.
# Bo'sh API_KEY/BEARER bo'lsa — so'rov yuborilmaydi (xato bermaydi, skip).
MENTALABA_API_BASE = env.str("MENTALABA_API_BASE", "https://api.mentalaba.uz")
MENTALABA_API_KEY = env.str("MENTALABA_API_KEY", "")
MENTALABA_BEARER = env.str("MENTALABA_BEARER", "")
ADMISSION_YEAR = env.str("ADMISSION_YEAR", "2026")
# SUBJECTS_MAP = {
#     "Matematika": {
#         "id": 20,
#         "ru": "Математика",
#         "relative": {
#             "uz": ["Fizika", "Geografiya", "Ingliz tili", "Ona tili va adabiyot"],
#             "ru": ["Физика", "География", "Английский язык", "Родной язык и литература"],
#         },
#     },
#     "Fizika": {
#         "id": 24,
#         "ru": "Физика",
#         "relative": {
#             "uz": ["Matematika", "Ingliz tili"],
#             "ru": ["Математика", "Английский язык"],
#         },
#     },
#     "Geografiya": {
#         "id": 25,
#         "ru": "География",
#         "relative": {
#             "uz": ["Matematika"],
#             "ru": ["Математика"],
#         },
#     },
#     "Ingliz tili": {
#         "id": 23,
#         "ru": "Английский язык",
#         "relative": {
#             "uz": ["Matematika", "Ona tili va adabiyot"],
#             "ru": ["Математика", "Родной язык и литература"],
#         },
#     },
#     "Ona tili va adabiyot": {
#         "id": 27,
#         "ru": "Родной язык и литература",
#         "relative": {
#             "uz": ["Matematika", "Ingliz tili", "Biologiya"],
#             "ru": ["Математика", "Английский язык", "Биология"],
#         },
#     },
#     "Tarix": {
#         "id": 26,
#         "ru": "История",
#         "relative": {
#             "uz": ["Matematika", "Geografiya", "Ingliz tili", "Ona tili va adabiyot"],
#             "ru": ["Математика", "География", "Английский язык", "Родной язык и литература"],
#         },
#     },
#     "Biologiya": {
#         "id": 6,
#         "ru": "Биология",
#         "relative": {
#             "uz": ["Kimyo", "Ona tili va adabiyot"],
#             "ru": ["Химия", "Родной язык и литература"],
#         },
#     },
#     "Kimyo": {
#         "id": 7,
#         "ru": "Химия",
#         "relative": {
#             "uz": ["Biologiya", "Matematika"],
#             "ru": ["Биология", "Математика"],
#         },
#     },
# }

SUBJECTS_MAP = {
    "Matematika": {
        "id": 20,  # 30 talik
        "ru": "Математика",
        "relative": {
            "uz": ["Fizika", "Geografiya", "Ingliz tili", "Kimyo", "Ona tili va adabiyot", "Tarix"],
            "ru": ["Физика", "География", "Английский язык", "Химия", "Русский язык и литература", "История"],
        },
    },
    "Matematika (majburiy)": {
        "id": 5,
        "ru": "Математика (обязательно)",
        "relative": {
            "uz": [],
            "ru": [],
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
            "uz": ["Matematika", "Tarix"],
            "ru": ["Математика", "История"],
        },
    },
    "Ingliz tili": {
        "id": 23,
        "ru": "Английский язык",
        "relative": {
            "uz": ["Ona tili va adabiyot"],
            "ru": ["Русский язык и литература"],
        },
    },
    "Ona tili": {
        "id": 17,  # majburiy
        "ru": "Родной язык",
        "relative": {
            "uz": [],
            "ru": [],
        },
    },
    "Ona tili va adabiyot": {
        "id": 27,  # 30 talik
        "ru": "Русский язык и литература",
        "relative": {
            "uz": ["Biologiya", "Ingliz tili", "Matematika", "Tarix"],
            "ru": ["Биология", "Английский язык", "Математика", "История"],
        },
    },
    "Tarix": {
        "id": 26,  # 30 talik
        "ru": "История",
        "relative": {
            "uz": ["Geografiya", "Ingliz tili", "Matematika", "Ona tili va adabiyot"],
            "ru": ["География", "Английский язык", "Математика", "Русский язык и литература"],
        },
    },
    "O'zbekiston tarixi": {
        "id": 8,  # majburiy
        "ru": "История Узбекистана",
        "relative": {
            "uz": [],
            "ru": [],
        },
    },
    "Biologiya": {
        "id": 6,
        "ru": "Биология",
        "relative": {
            "uz": ["Kimyo", "Ona tili va adabiyot"],
            "ru": ["Химия", "Русский язык и литература"],
        },
    },
    "Kimyo": {
        "id": 7,
        "ru": "Химия",
        "relative": {
            "uz": ["Biologiya", "Ingliz tili", "Matematika"],
            "ru": ["Биология", "Английский язык", "Математика"],
        },
    },
    "Davlat va huquq asoslari": {
        "id": 35,
        "ru": "Основы государства и права",
        "relative": {
            "uz": ["Ingliz tili"],
            "ru": ["Английский язык"],
        },
    },
}
