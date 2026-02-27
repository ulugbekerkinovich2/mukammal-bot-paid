from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any

PAGE_SIZE = 10


def _max_page(total: int) -> int:
    return max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)


def _slice(items: List[Dict[str, Any]], page: int):
    if page < 1:
        page = 1
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    return items[start:end]


def _nav_row(prefix: str, page: int, max_page: int):
    row = []
    if page > 1:
        row.append(InlineKeyboardButton("⬅️", callback_data=f"{prefix}:{page-1}"))
    row.append(InlineKeyboardButton(f"{page}/{max_page}", callback_data="noop"))
    if page < max_page:
        row.append(InlineKeyboardButton("➡️", callback_data=f"{prefix}:{page+1}"))
    return row


def admin_main_inline():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🏙 Tumanlar", callback_data="adm:districts:1"),
        # InlineKeyboardButton("🏫 Maktablar", callback_data="adm:schools:1"),
    )
    kb.add(InlineKeyboardButton("❌ Yopish", callback_data="adm:close"))
    return kb


def admin_districts_inline(districts: List[Dict[str, Any]], page: int = 1):
    kb = InlineKeyboardMarkup(row_width=1)
    total = len(districts)
    max_page = _max_page(total)
    page = min(max(1, page), max_page)

    for d in _slice(districts, page):
        did = d.get("id")
        if did is None:
            continue

        district = str(d.get("district", "")).strip()
        region = str(d.get("region", "")).strip()
        answered = int(d.get("answered_count") or 0)
        registered = int(d.get("registered_count") or 0)
        school_count = int(d.get("school_count") or 0)

        title = f"{district} • {school_count}🏫 • {answered}/{registered}"
        if region:
            title = f"{district} • {region} • {school_count}🏫 • {answered}/{registered}"

        kb.add(InlineKeyboardButton(title[:60], callback_data=f"adm_dist:{did}:{page}"))

    kb.row(*_nav_row("adm:districts", page, max_page))

    kb.add(
        InlineKeyboardButton("🔄 Yangilash", callback_data=f"adm:districts:{page}"),
        InlineKeyboardButton("🏠 Bosh menyu", callback_data="adm:back_main"),
    )
    return kb


def admin_district_actions_inline(district_id: int, back_page: int = 1):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🔑 Tuman login/parol", callback_data=f"adm_dist_show:{district_id}:{back_page}"),
        InlineKeyboardButton("🏫 Shu tumandagi maktablar", callback_data=f"adm_dist_schools:{district_id}:1:{back_page}"),
    )
    kb.add(
        InlineKeyboardButton("⬅️ Tumanlar", callback_data=f"adm:districts:{back_page}"),
        InlineKeyboardButton("🏠 Bosh menyu", callback_data="adm:back_main"),
    )
    return kb


def admin_schools_inline(schools: List[Dict[str, Any]], page: int = 1, back_cb: str = "adm:back_main"):
    kb = InlineKeyboardMarkup(row_width=1)
    total = len(schools)
    max_page = _max_page(total)
    page = min(max(1, page), max_page)

    for s in _slice(schools, page):
        sid = s.get("id")
        if sid is None:
            continue
        full_name = str(s.get("full_name", "")).strip()
        region = str(s.get("region", "")).strip()
        district = str(s.get("district", "")).strip()

        title = full_name or f"School #{sid}"
        if district:
            title = f"{title} • {district}"
        if region:
            title = f"{title} • {region}"

        kb.add(InlineKeyboardButton(title[:60], callback_data=f"adm_sch:{sid}:{page}"))

    kb.row(*_nav_row("adm:schools", page, max_page))
    kb.add(
        InlineKeyboardButton("🔄 Yangilash", callback_data=f"adm:schools:{page}"),
        InlineKeyboardButton("⬅️ Orqaga", callback_data=back_cb),
    )
    return kb


def admin_district_schools_inline(
    schools: List[Dict[str, Any]],
    district_id: int,
    page: int = 1,
    back_page: int = 1,
):
    kb = InlineKeyboardMarkup(row_width=1)
    total = len(schools)
    max_page = _max_page(total)
    page = min(max(1, page), max_page)

    for s in _slice(schools, page):
        sid = s.get("id")
        if sid is None:
            continue
        full_name = str(s.get("full_name", "")).strip()
        title = full_name or f"School #{sid}"
        kb.add(InlineKeyboardButton(title[:60], callback_data=f"adm_sch_in_dist:{sid}:{district_id}:{page}:{back_page}"))

    kb.row(*_nav_row(f"adm_dist_schools:{district_id}", page, max_page))

    kb.add(
        InlineKeyboardButton("🔄 Yangilash", callback_data=f"adm_dist_schools:{district_id}:{page}:{back_page}"),
        InlineKeyboardButton("⬅️ Tuman menyusi", callback_data=f"adm_dist_actions:{district_id}:{back_page}"),
    )
    return kb