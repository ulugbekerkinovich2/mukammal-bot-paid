from environs import Env

# environs kutubxonasidan foydalanish
env = Env()
env.read_env()

# .env fayl ichidan quyidagilarni o'qiymiz
BOT_TOKEN = env.str("BOT_TOKEN")  # Bot toekn
ADMINS = env.list("ADMINS")  # adminlar ro'yxati
IP = env.str("ip")  # Xosting ip manzili
main_url = env.str("base_url")
CHANNEL_ID = env.str('CHANNEL_ID')
TEST_MODE = env.bool("TEST_MODE", False)
TEST_CHAT_ID = env.int("TEST_CHAT_ID", 0)