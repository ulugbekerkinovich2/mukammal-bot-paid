from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any


def admin_main_inline():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🏙 Tuman parolini olish", callback_data="adm:districts"),
        InlineKeyboardButton("🏫 Maktab parolini olish", callback_data="adm:schools"),
    )
    kb.add(InlineKeyboardButton("❌ Yopish", callback_data="adm:close"))
    return kb


def admin_districts_inline(districts: List[Dict[str, Any]]):
    kb = InlineKeyboardMarkup(row_width=1)

    for d in districts[:90]:
        did = d.get("id")
        region = str(d.get("region", "")).strip()
        district = str(d.get("district", "")).strip()
        full_name = str(d.get("full_name", "")).strip()

        title = f"{region} | {district}"
        if full_name:
            title = f"{title} — {full_name}"

        if did is None:
            continue

        kb.add(InlineKeyboardButton(title[:60], callback_data=f"adm_dist:{did}"))

    kb.add(InlineKeyboardButton("⬅️ Orqaga", callback_data="adm:back_main"))
    return kb


def admin_schools_inline(schools: List[Dict[str, Any]]):
    kb = InlineKeyboardMarkup(row_width=1)

    for s in schools[:90]:
        sid = s.get("id")
        region = str(s.get("region", "")).strip()
        district = str(s.get("district", "")).strip()
        full_name = str(s.get("full_name", "")).strip()
        username = str(s.get("username", "")).strip()

        title = f"{region} | {district} | {full_name}"
        if username:
            title = f"{title} ({username})"

        if sid is None:
            continue

        kb.add(InlineKeyboardButton(title[:60], callback_data=f"adm_sch:{sid}"))

    kb.add(InlineKeyboardButton("⬅️ Orqaga", callback_data="adm:back_main"))
    return kb
