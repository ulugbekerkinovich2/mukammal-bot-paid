from aiogram import types


async def set_default_commands(dp):
    await dp.bot.set_my_commands(
        [
            types.BotCommand("start", "Botni ishga tushirish"),
            types.BotCommand("natija", "📊 Mening natijam"),
            types.BotCommand("sertifikat_qollanma", "🎥 Sertifikatni olish uchun video qo‘llanma"),
        ]
    )

    await dp.bot.set_chat_menu_button(menu_button=types.MenuButtonCommands())
