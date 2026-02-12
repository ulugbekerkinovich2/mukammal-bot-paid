from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def regions_kb(ui_lang: str):
    regions = [
        ("toshkent", "Toshkent"),
        ("samarqand", "Samarqand"),
        ("andijon", "Andijon"),
        ("buxoro", "Buxoro"),
        ("fargona", "Farg‘ona"),
        ("namangan", "Namangan"),
        ("navoiy", "Navoiy"),
        ("qashqadaryo", "Qashqadaryo"),
        ("surxondaryo", "Surxondaryo"),
        ("xorazm", "Xorazm"),
        ("jizzax", "Jizzax"),
        ("sirdaryo", "Sirdaryo"),
        ("qoraqalpogiston", "Qoraqalpog‘iston"),
    ]

    kb = InlineKeyboardMarkup(row_width=2)
    for key, label in regions:
        kb.insert(InlineKeyboardButton(label, callback_data=f"reg_region:{key}"))
    kb.add(InlineKeyboardButton("❌ Cancel" if ui_lang == "ru" else "❌ Bekor qilish", callback_data="reg_cancel"))
    return kb


def districts_kb(ui_lang: str, districts: list[str]):
    kb = InlineKeyboardMarkup(row_width=1)
    for d in districts:
        kb.add(InlineKeyboardButton(d, callback_data=f"reg_district:{d}"))

    kb.add(InlineKeyboardButton("⬅️ Orqaga" if ui_lang == "uz" else "⬅️ Назад", callback_data="reg_back:region"))
    kb.add(InlineKeyboardButton("❌ Cancel" if ui_lang == "ru" else "❌ Bekor qilish", callback_data="reg_cancel"))
    return kb


def schools_kb(ui_lang: str, schools: list[dict]):
    """
    schools item: {"id":1,"code":"SHAY10","name":"10 maktab"}
    callback: reg_school:<code>  (string ketadi)
    """
    kb = InlineKeyboardMarkup(row_width=1)

    for s in schools[:80]:
        code = str(s.get("code") or "")
        name = s.get("name") or code
        if not code:
            continue
        kb.add(InlineKeyboardButton(name, callback_data=f"reg_school:{code}"))

    kb.add(InlineKeyboardButton("⬅️ Orqaga" if ui_lang == "uz" else "⬅️ Назад", callback_data="reg_back:district"))
    kb.add(InlineKeyboardButton("❌ Cancel" if ui_lang == "ru" else "❌ Bekor qilish", callback_data="reg_cancel"))
    return kb
