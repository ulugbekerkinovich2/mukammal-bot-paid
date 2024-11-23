from aiogram import types
from aiogram.dispatcher.filters.builtin import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from loader import dp, bot
class Form(StatesGroup):
    name = State()  # Ism va familiya holati
    phone = State()
# Variables to store user responses across handlers
user_data = {}

categories = {
    1: "Ёлғиз кекса деб эътироф этиш (ёки бекор қилиш)",
    2: "Чуқурлаштирилган тиббий кўрикдан ўтказиш",
    3: "Ҳужжатларини расмийлаштириш ва қайта тиклашда ёрдам бериш",
    4: "Яқин инсонлари билан муносабатларни тиклаш",
    5: "Маданий тадбирларни ташкил этишда кўнгиллиларни рўйхатга олиш",
    6: "Бепул дори-дармон билан таъминлашни ташкил этиш",
    7: "Ижтимоий қўллаб-қувватлаш маркази интернат уйларига кундузги қатнов учун ариза қабул қилиш",
    8: "Ўзгалар парваришига муҳтож шахсларга пуллик хизмат кўрсатиш",
    9: "Ижтимоий ҳимоя миллий агентлиги тизимидаги санаторийларга йўлланмалар ажратиш",
    10: "Психологик хизмат кўрсатиш",
    11: "Ҳуқуқий масалаларда ёрдам хизмати",
    12: "Ногиронликни белгилаш ва гуруҳини ўзгартириш",
    13: "Ногиронлиги бўлган шахсларни бандлигини таъминлаш ва касбга тайёрлаш",
    14: "Ногиронлик нафақасини тайинлаш",
    15: "Ногиронлиги бўлган шахсларга ер участкаларини онлайн-аукционда сотиб олиш харажатларининг бир қисмини қоплаб бериш",
    16: "Тиббий реабилитация қилиш бўлимларида стационар шароитда реабилитация тадбирларини ўташ учун йўналтириш",
    17: "Ногиронлик белгилаш ва функционалликни баҳолаш",
    18: "Ногиронлик тўғрисидаги маълумотнома олиш",
    19: "Болаликдан ногиронлиги бўлган фарзандлари бор оналарга ёшга доир нафақа",
    20: "Аёлларни реабилитация марказида ёрдам кўрсатилган ва ҳимоя ордери берилганларни мониторинг қилиш",
    21: "Йўқотилган ҳужжатларни тиклаш бўйича ёрдам",
    22: "Тазйиқ ва зўравонликдан жабрланганлар бўйича судларга ариза ва даъволар киритиш",
    23: "Банк картасини тиклаш учун мурожаат қилиш юзасидан ишончнома тасдиқлаш",
    24: "“Аёллар дафтари”га киритилган хотин-қизлар ва уларнинг фарзандлари учун дори-дармон ёки мураккаб жарроҳлик амалиётлари учун сектор раҳбарига сўровнома киритиш",
    25: "Тазйиқ ва зўравонликдан жабрланган хотин-қизларга ҳимоя ордерини бериш учун сўровнома киритиш",
    26: "Кам таъминланган оилаларга болалар нафақаси ва моддий ёрдам тайинлашга ариза бериш",
    27: "“Ижтимоий ҳимоя ягона реестри” га кириш учун ариза бериш",
    28: "Кам таъминланган деб эътироф этилганлик тўғрисида маълумотнома бериш",
    29: "Тутинган ота-оналарни тайёрлаш курсларида ўқиш бўйича ариза қабул қилиш",
    30: "Болани васийликка ва ҳомийликка олиш учун ариза қабул қилиш",
    31: "Боқувчисини йўқотганлик нафақасини расмийлаштириш",
    32: "Болани фарзандликка олиш учун ариза қабул қилиш",
    33: "Жисмоний, ақлий, сенсор ёки руҳий нуқсонлари бўлган, шунингдек, узоқ вақт даволанишга муҳтож бўлган, мактаблар, мактаб-интернатларга қатнай олмайдиган болалар учун уйда якка тартибда таълим бериш хизматини кўрсатиш",
    34: "Ота-оналик ҳуқуқларини тиклаш бўйича хулоса бериш",
    35: "18 ёшгача бўлган ҳомиладор оналарга фарзандидан воз кечишнинг оқибатлари юзасидан тушунтириш бериш",
    36: "Суд қарорига асосан бедарак йўқолган фуқароларга нафақа тайинлаш",
    37: "Болани давлат мактабгача таълим муассасасига жойлаштириш",
    38: "Нафақаларни қайта ҳисоблаш бўйича ариза"
}

async def get_main_keyboard(page=1, items_per_page=5):
    """Inline klaviatura yaratish, pagination bilan."""
    markup = InlineKeyboardMarkup(row_width=1)
    sorted_keys = sorted(categories.keys())
    start = (page - 1) * items_per_page
    end = start + items_per_page
    total_pages = len(categories) // items_per_page + (1 if len(categories) % items_per_page > 0 else 0)

    for index, key in enumerate(sorted_keys[start:end], start=start+1):
        button_text = f"{index}. {categories[key]}"
        markup.add(InlineKeyboardButton(button_text, callback_data=f"category_{key}"))

    if page > 1:
        markup.add(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"page_{page - 1}"))
    if page < total_pages:
        markup.add(InlineKeyboardButton("Keyingi ➡️", callback_data=f"page_{page + 1}"))

    return markup


@dp.message_handler(CommandStart())
async def bot_start(message: types.Message, state: FSMContext):
    await Form.name.set()  # Foydalanuvchini ism holatiga o'tkazing
    await message.answer("Assalomu alaykum! Muzrabot tumani ijtimoiy yordam botiga xush kelibsiz. Ism va Familiyangizni kiriting.\nNamuna: Alisherov Farhod Toxirovich.", parse_mode='HTML', reply_markup=ReplyKeyboardRemove())

@dp.message_handler(state=Form.name)
async def ask_for_full_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await Form.next()  # Keyingi holatga o'ting - telefon raqami
    contact_keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    contact_button = KeyboardButton("Telefon raqamni yuborish 📞", request_contact=True)
    contact_keyboard.add(contact_button)
    await message.answer("Iltimos, telefon raqamingizni yuboring:", reply_markup=contact_keyboard)

@dp.message_handler(content_types=types.ContentType.CONTACT, state=Form.phone)
async def ask_for_assistance_type(message: types.Message, state: FSMContext):
    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
    
    await state.update_data(phone_number=message.contact.phone_number)
    await state.reset_state(with_data=False)  # FSM holatini tugating
    await message.answer("Sizga qanday ijtimoiy yordam kerak? Kategoriyalarni tanlash uchun quyidagi ro'yxatdan foydalaning.", reply_markup=await get_main_keyboard())

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('page_'))
async def handle_page_change(callback_query: types.CallbackQuery, state: FSMContext):
    page = int(callback_query.data.split('_')[1])
    await callback_query.message.edit_reply_markup(reply_markup=await get_main_keyboard(page=page))

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('category_'))
async def handle_category_selection(callback_query: types.CallbackQuery, state: FSMContext):
    # await bot.delete_message(chat_id=callback_query.chat.id, message_id=callback_query.message_id)

    category_key = int(callback_query.data.split('_')[1])
    category_name = categories.get(category_key, "Noma'lum kategoriya")
    await state.update_data(chosen_category=category_name)
    response_text = f"Siz tanlagan yordam turi: {category_name}\nSizga qanday yordam kerak?"
    await callback_query.message.answer(response_text, reply_markup=ReplyKeyboardRemove())
    await callback_query.answer()
    await bot.delete_message(chat_id=callback_query.message.chat.id, message_id=callback_query.message.message_id)

@dp.message_handler(state='*')
async def receive_user_message(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    full_name = user_data.get('full_name')
    phone_number = user_data.get('phone_number')
    chosen_category = user_data.get('chosen_category')
    
    # Guruhga yuboriladigan xabar
    text_to_send = (
    f"<b>FIO:</b> {full_name}\n"
    f"<b>Raqam:</b> {phone_number}\n"
    f"<b>Kategoriya:</b> {chosen_category}\n"

    f"<b>Foydalanuvchi matni:</b> {message.text}"
)
    
    # Guruhga yuborish (misol uchun, guruh ID -1002482460312)
    await dp.bot.send_message(chat_id='-1002482460312', text=text_to_send)
    
    # Foydalanuvchiga tasdiq yuborish
    await message.answer("Botdan foydalanganingiz uchun tashakkur.")