from environs import Env

# environs kutubxonasidan foydalanish
env = Env()
env.read_env()

BOT_TOKEN = env.str("BOT_TOKEN")
ADMINS = env.list("ADMINS")
IP = env.str("ip")
CHANNEL_ID = env.str("CHANNEL_ID")
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
