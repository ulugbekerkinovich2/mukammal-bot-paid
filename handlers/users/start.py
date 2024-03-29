from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import CommandStart

from loader import dp
from states.personalData import PersonalData

@dp.message_handler(CommandStart(), state='*')
async def bot_start(message: types.Message, state: FSMContext):
    # Reset state
    await state.finish()
    
    # Your welcome message
    remove_keyboard = types.ReplyKeyboardRemove()
    await message.answer(
        f"<b>Hayrli kun {message.from_user.full_name}, kuningiz barakali o'tsin</b>",
        parse_mode='HTML',
        reply_markup=remove_keyboard
    )
