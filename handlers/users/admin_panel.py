# from aiogram import types
# from aiogram.dispatcher import FSMContext

# from loader import dp
# from data.config import ADMIN_CHAT_ID
# from aiogram.utils.exceptions import MessageNotModified
# from states.adminStates import AdminPanel
# from keyboards.inline.admin_inline import (
#     admin_main_inline,
#     admin_districts_inline,
#     admin_schools_inline,
#     admin_district_actions_inline,
#     admin_district_schools_inline,
# )

# from utils.send_req import (
#     fetch_districts,
#     fetch_district_by_id,
#     fetch_schools,
#     fetch_school_by_id,
# )

# async def safe_edit(call: types.CallbackQuery, text: str, reply_markup=None, parse_mode: str = "HTML"):
#     """
#     Telegram 'Message is not modified' xatosini yemaydi.
#     """
#     try:
#         await call.message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
#     except MessageNotModified:
#         # UI o‘zgarmagan bo‘lsa jim
#         pass
# def _parse_admin_ids(value) -> set:
#     if value is None:
#         return set()
#     if isinstance(value, int):
#         return {value}
#     if isinstance(value, (list, tuple, set)):
#         return {int(x) for x in value if str(x).isdigit()}
#     s = str(value).strip()
#     if not s:
#         return set()
#     parts = [p.strip() for p in s.replace(" ", ",").split(",") if p.strip()]
#     out = set()
#     for p in parts:
#         if p.isdigit():
#             out.add(int(p))
#     return out


# ADMIN_IDS = _parse_admin_ids(ADMIN_CHAT_ID)


# def is_admin(user_id: int) -> bool:
#     return int(user_id) in ADMIN_IDS


# def _ui_header(title: str, crumb: str = "") -> str:
#     if crumb:
#         return f"🛠 <b>{title}</b>\n<i>{crumb}</i>\n"
#     return f"🛠 <b>{title}</b>\n"


# def _api_err_text(res: dict) -> str:
#     status = res.get("status")
#     txt = str(res.get("text", ""))[:900]
#     return f"❌ API xato: {status}\n{txt}"


# @dp.callback_query_handler(lambda c: c.data == "noop", state="*")
# async def noop(call: types.CallbackQuery):
#     await call.answer()


# @dp.message_handler(commands=["admin"], state="*")
# async def admin_cmd(message: types.Message, state: FSMContext):
#     if not is_admin(message.from_user.id):
#         return
#     await state.finish()
#     await message.answer(_ui_header("Admin panel", "Bosh menyu"), parse_mode="HTML", reply_markup=admin_main_inline())
#     await AdminPanel.menu.set()


# @dp.message_handler(lambda m: (m.text or "").strip() == "🛠 Admin", state="*")
# async def admin_btn(message: types.Message, state: FSMContext):
#     if not is_admin(message.from_user.id):
#         return
#     await state.finish()
#     await message.answer(_ui_header("Admin panel", "Bosh menyu"), parse_mode="HTML", reply_markup=admin_main_inline())
#     await AdminPanel.menu.set()


# @dp.callback_query_handler(lambda c: c.data == "adm:close", state="*")
# async def adm_close(call: types.CallbackQuery, state: FSMContext):
#     if not is_admin(call.from_user.id):
#         await call.answer("Ruxsat yo‘q", show_alert=True)
#         return
#     await state.finish()
#     await call.message.edit_text("✅ Yopildi", reply_markup=None)
#     await call.answer()


# @dp.callback_query_handler(lambda c: c.data == "adm:back_main", state="*")
# async def adm_back_main(call: types.CallbackQuery, state: FSMContext):
#     if not is_admin(call.from_user.id):
#         await call.answer("Ruxsat yo‘q", show_alert=True)
#         return
#     await call.message.edit_text(_ui_header("Admin panel", "Bosh menyu"), parse_mode="HTML", reply_markup=admin_main_inline())
#     await AdminPanel.menu.set()
#     await call.answer()


# # ------------------------------
# # DISTRICTS LIST
# # cb: adm:districts:<page>
# # ------------------------------
# @dp.callback_query_handler(lambda c: c.data.startswith("adm:districts:"), state="*")
# async def adm_show_districts(call: types.CallbackQuery, state: FSMContext):
#     if not is_admin(call.from_user.id):
#         await call.answer("Ruxsat yo‘q", show_alert=True)
#         return

#     try:
#         page = int(call.data.split(":")[-1])
#     except Exception:
#         page = 1

#     data = await state.get_data()
#     cached = data.get("cached_districts")

#     if not cached or call.data.endswith(":1") or True:
#         # UX: Yangilash uchun qayta chaqirsa bo‘ladi
#         res = await fetch_districts()
#         if isinstance(res, dict) and res.get("ok") is False:
#             await safe_edit(call, _api_err_text(res), reply_markup=admin_main_inline())
#             await AdminPanel.menu.set()
#             await call.answer()
#             return
#         districts = res if isinstance(res, list) else []
#         await state.update_data(cached_districts=districts)
#     else:
#         districts = cached

#     if not districts:
#         await call.message.edit_text("❌ Tumanlar topilmadi.", reply_markup=admin_main_inline())
#         await AdminPanel.menu.set()
#         await call.answer()
#         return

#     await call.message.edit_text(
#         _ui_header("Tumanlar", "Tumanlar → tanlang"),
#         parse_mode="HTML",
#         reply_markup=admin_districts_inline(districts, page=page),
#     )
#     await AdminPanel.districts_list.set()
#     await call.answer()


# # ------------------------------
# # PICK DISTRICT
# # cb: adm_dist:<did>:<back_page>
# # ------------------------------
# @dp.callback_query_handler(lambda c: c.data.startswith("adm_dist:"), state=AdminPanel.districts_list)
# async def adm_pick_district(call: types.CallbackQuery, state: FSMContext):
#     if not is_admin(call.from_user.id):
#         await call.answer("Ruxsat yo‘q", show_alert=True)
#         return

#     parts = call.data.split(":")
#     did = int(parts[1])
#     back_page = int(parts[2]) if len(parts) > 2 else 1

#     await state.update_data(selected_district_id=did, districts_back_page=back_page)

#     await call.message.edit_text(
#         _ui_header("Tuman tanlandi", "Tuman → Amallar") + "👇 Nima qilamiz?",
#         parse_mode="HTML",
#         reply_markup=admin_district_actions_inline(did, back_page=back_page),
#     )
#     await AdminPanel.district_selected.set()
#     await call.answer()


# # ------------------------------
# # BACK to district actions
# # cb: adm_dist_actions:<did>:<back_page>
# # ------------------------------
# @dp.callback_query_handler(lambda c: c.data.startswith("adm_dist_actions:"), state="*")
# async def adm_back_to_district_actions(call: types.CallbackQuery, state: FSMContext):
#     if not is_admin(call.from_user.id):
#         await call.answer("Ruxsat yo‘q", show_alert=True)
#         return

#     parts = call.data.split(":")
#     did = int(parts[1])
#     back_page = int(parts[2]) if len(parts) > 2 else 1

#     await state.update_data(selected_district_id=did, districts_back_page=back_page)

#     await call.message.edit_text(
#         _ui_header("Tuman tanlandi", "Tuman → Amallar") + "👇 Nima qilamiz?",
#         parse_mode="HTML",
#         reply_markup=admin_district_actions_inline(did, back_page=back_page),
#     )
#     await AdminPanel.district_selected.set()
#     await call.answer()


# # ------------------------------
# # SHOW DISTRICT CREDS
# # cb: adm_dist_show:<did>:<back_page>
# # ------------------------------
# @dp.callback_query_handler(lambda c: c.data.startswith("adm_dist_show:"), state=AdminPanel.district_selected)
# async def adm_show_district_creds(call: types.CallbackQuery, state: FSMContext):
#     if not is_admin(call.from_user.id):
#         await call.answer("Ruxsat yo‘q", show_alert=True)
#         return

#     parts = call.data.split(":")
#     did = int(parts[1])
#     back_page = int(parts[2]) if len(parts) > 2 else 1

#     res = await fetch_district_by_id(did)
#     if isinstance(res, dict) and res.get("ok") is False:
#         await call.message.edit_text(_api_err_text(res), reply_markup=admin_district_actions_inline(did, back_page=back_page))
#         await call.answer()
#         return

#     username = res.get("username", "-")
#     password = res.get("password_hash", "-")
#     region = res.get("region", "-")
#     district = res.get("district", "-")
#     full_name = res.get("full_name", "-")
#     role = res.get("role", "district")

#     txt = (
#         _ui_header("Tuman admin", f"{region} → {district}")
#         + f"\n👤 <b>Nomi:</b> {full_name}\n"
#         + f"🧩 <b>Role:</b> {role}\n"
#         + f"📍 <b>Hudud:</b> {region} | {district}\n\n"
#         + f"🔑 <b>Login:</b> <code>{username}</code>\n"
#         + f"🔒 <b>Parol:</b> <code>{password}</code>\n"
#         + "\n💡 <i>Nusxalash uchun code ustiga bosib ushlab turing.</i>"
#     )

#     await call.message.edit_text(txt, parse_mode="HTML", reply_markup=admin_district_actions_inline(did, back_page=back_page))
#     await AdminPanel.district_selected.set()
#     await call.answer()


# # ------------------------------
# # SHOW SCHOOLS IN DISTRICT (filtered) + pagination
# # cb: adm_dist_schools:<did>:<page>:<back_page>
# # ------------------------------
# @dp.callback_query_handler(lambda c: c.data.startswith("adm_dist_schools:"), state="*")
# async def adm_show_schools_in_district(call: types.CallbackQuery, state: FSMContext):
#     if not is_admin(call.from_user.id):
#         await call.answer("Ruxsat yo‘q", show_alert=True)
#         return

#     parts = call.data.split(":")
#     did = int(parts[1])
#     page = int(parts[2]) if len(parts) > 2 else 1
#     back_page = int(parts[3]) if len(parts) > 3 else 1

#     dres = await fetch_district_by_id(did)
#     if isinstance(dres, dict) and dres.get("ok") is False:
#         await call.message.edit_text(_api_err_text(dres), reply_markup=admin_district_actions_inline(did, back_page=back_page))
#         await call.answer()
#         return

#     region = (dres.get("region") or "").strip()
#     district = (dres.get("district") or "").strip()

#     # Cache filtered schools for this district
#     data = await state.get_data()
#     cache_key = "cached_schools_district_%s" % did
#     cached = data.get(cache_key)

#     if not cached:
#         sres = await fetch_schools()
#         if isinstance(sres, dict) and sres.get("ok") is False:
#             await call.message.edit_text(_api_err_text(sres), reply_markup=admin_district_actions_inline(did, back_page=back_page))
#             await call.answer()
#             return

#         schools = sres if isinstance(sres, list) else []
#         filtered = [s for s in schools if str(s.get("district", "")).strip() == district and str(s.get("region", "")).strip() == region]
#         await state.update_data(**{cache_key: filtered})
#     else:
#         filtered = cached

#     if not filtered:
#         txt = _ui_header("Maktablar", f"{region} → {district}") + "\n❌ Bu tumanda maktab topilmadi."
#         await call.message.edit_text(txt, parse_mode="HTML", reply_markup=admin_district_actions_inline(did, back_page=back_page))
#         await AdminPanel.district_selected.set()
#         await call.answer()
#         return

#     await state.update_data(selected_district_id=did, selected_region=region, selected_district=district)

#     txt = _ui_header("Maktablar", f"{region} → {district}") + "\n👇 Maktab tanlang:"
#     await call.message.edit_text(
#         txt,
#         parse_mode="HTML",
#         reply_markup=admin_district_schools_inline(filtered, district_id=did, page=page, back_page=back_page),
#     )
#     await AdminPanel.district_schools_list.set()
#     await call.answer()


# # ------------------------------
# # GLOBAL SCHOOLS LIST
# # cb: adm:schools:<page>
# # ------------------------------
# @dp.callback_query_handler(lambda c: c.data.startswith("adm:schools:"), state="*")
# async def adm_show_schools(call: types.CallbackQuery, state: FSMContext):
#     if not is_admin(call.from_user.id):
#         await call.answer("Ruxsat yo‘q", show_alert=True)
#         return

#     try:
#         page = int(call.data.split(":")[-1])
#     except Exception:
#         page = 1

#     data = await state.get_data()
#     cached = data.get("cached_schools")

#     if not cached:
#         res = await fetch_schools()
#         if isinstance(res, dict) and res.get("ok") is False:
#             await call.message.edit_text(_api_err_text(res), reply_markup=admin_main_inline())
#             await AdminPanel.menu.set()
#             await call.answer()
#             return
#         schools = res if isinstance(res, list) else []
#         await state.update_data(cached_schools=schools)
#     else:
#         schools = cached

#     if not schools:
#         await call.message.edit_text("❌ Maktablar topilmadi.", reply_markup=admin_main_inline())
#         await AdminPanel.menu.set()
#         await call.answer()
#         return

#     await call.message.edit_text(
#         _ui_header("Maktablar", "Maktablar → tanlang"),
#         parse_mode="HTML",
#         reply_markup=admin_schools_inline(schools, page=page, back_cb="adm:back_main"),
#     )
#     await AdminPanel.schools_list.set()
#     await call.answer()


# # ------------------------------
# # PICK SCHOOL from global list
# # cb: adm_sch:<sid>:<back_page>
# # ------------------------------
# @dp.callback_query_handler(lambda c: c.data.startswith("adm_sch:"), state=AdminPanel.schools_list)
# async def adm_pick_school(call: types.CallbackQuery, state: FSMContext):
#     if not is_admin(call.from_user.id):
#         await call.answer("Ruxsat yo‘q", show_alert=True)
#         return

#     parts = call.data.split(":")
#     sid = int(parts[1])
#     back_page = int(parts[2]) if len(parts) > 2 else 1

#     res = await fetch_school_by_id(sid)
#     if isinstance(res, dict) and res.get("ok") is False:
#         await call.message.edit_text(_api_err_text(res), reply_markup=admin_main_inline())
#         await AdminPanel.menu.set()
#         await call.answer()
#         return

#     username = res.get("username", "-")
#     password = res.get("password_hash", "-")
#     region = res.get("region", "-")
#     district = res.get("district", "-")
#     full_name = res.get("full_name", "-")
#     role = res.get("role", "school")

#     txt = (
#         _ui_header("Maktab admin", f"{region} → {district}")
#         + f"\n🏫 <b>Maktab:</b> {full_name}\n"
#         + f"🧩 <b>Role:</b> {role}\n"
#         + f"📍 <b>Hudud:</b> {region} | {district}\n\n"
#         + f"🔑 <b>Login:</b> <code>{username}</code>\n"
#         + f"🔒 <b>Parol:</b> <code>{password}</code>\n"
#         + "\n💡 <i>Nusxalash uchun code ustiga bosib ushlab turing.</i>"
#     )

#     await call.message.edit_text(txt, parse_mode="HTML", reply_markup=admin_main_inline())
#     await AdminPanel.menu.set()
#     await call.answer()


# # ------------------------------
# # PICK SCHOOL from district list
# # cb: adm_sch_in_dist:<sid>:<did>:<page>:<back_page>
# # ------------------------------
# @dp.callback_query_handler(lambda c: c.data.startswith("adm_sch_in_dist:"), state=AdminPanel.district_schools_list)
# async def adm_pick_school_from_district(call: types.CallbackQuery, state: FSMContext):
#     if not is_admin(call.from_user.id):
#         await call.answer("Ruxsat yo‘q", show_alert=True)
#         return

#     parts = call.data.split(":")
#     sid = int(parts[1])
#     did = int(parts[2])
#     page = int(parts[3]) if len(parts) > 3 else 1
#     back_page = int(parts[4]) if len(parts) > 4 else 1

#     res = await fetch_school_by_id(sid)
#     if isinstance(res, dict) and res.get("ok") is False:
#         await call.answer("API xato", show_alert=True)
#         return

#     username = res.get("username", "-")
#     password = res.get("password_hash", "-")
#     region = res.get("region", "-")
#     district = res.get("district", "-")
#     full_name = res.get("full_name", "-")
#     role = res.get("role", "school")

#     txt = (
#         _ui_header("Maktab admin", f"{region} → {district}")
#         + f"\n🏫 <b>Maktab:</b> {full_name}\n"
#         + f"🧩 <b>Role:</b> {role}\n"
#         + f"📍 <b>Hudud:</b> {region} | {district}\n\n"
#         + f"🔑 <b>Login:</b> <code>{username}</code>\n"
#         + f"🔒 <b>Parol:</b> <code>{password}</code>\n"
#     )

#     back_markup = types.InlineKeyboardMarkup(row_width=1)
#     back_markup.add(
#         types.InlineKeyboardButton("⬅️ Maktablar ro'yxati", callback_data=f"adm_dist_schools:{did}:{page}:{back_page}"),
#         types.InlineKeyboardButton("⬅️ Tuman menyusi", callback_data=f"adm_dist_actions:{did}:{back_page}"),
#         types.InlineKeyboardButton("🏠 Bosh menyu", callback_data="adm:back_main"),
#     )

#     await call.message.edit_text(txt, parse_mode="HTML", reply_markup=back_markup)
#     await AdminPanel.district_schools_list.set()
#     await call.answer()

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.utils.exceptions import MessageNotModified

from loader import dp
from data.config import ADMIN_CHAT_ID

from states.adminStates import AdminPanel
from keyboards.inline.admin_inline import (
    admin_main_inline,
    admin_districts_inline,
    admin_district_actions_inline,
    admin_district_schools_inline,
)

from utils.send_req import (
    fetch_districts,
    fetch_district_by_id,
    fetch_schools,
    fetch_school_by_id,
)


def _parse_admin_ids(value) -> set:
    if value is None:
        return set()

    if isinstance(value, int):
        return {value}

    if isinstance(value, (list, tuple, set)):
        return {int(x) for x in value if str(x).isdigit()}

    s = str(value).strip()
    if not s:
        return set()

    parts = [p.strip() for p in s.replace(" ", ",").split(",") if p.strip()]
    out = set()
    for p in parts:
        if p.isdigit():
            out.add(int(p))
    return out


ADMIN_IDS = _parse_admin_ids(ADMIN_CHAT_ID)


def is_admin(user_id: int) -> bool:
    return int(user_id) in ADMIN_IDS


async def safe_edit(call: types.CallbackQuery, text: str, reply_markup=None, parse_mode: str = "HTML"):
    try:
        await call.message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except MessageNotModified:
        # Text + markup o‘zgarmagan bo‘lsa jim o‘tamiz
        pass


def _ui_header(title: str, crumb: str = "") -> str:
    if crumb:
        return f"🛠 <b>{title}</b>\n<i>{crumb}</i>\n"
    return f"🛠 <b>{title}</b>\n"


def _unwrap_list(res):
    """
    Sizning _request_json format:
      - success: {'ok': True, 'status': 200, 'data': [...]}
      - error:   {'ok': False, 'status': xxx, 'text': '...'}
    """
    if isinstance(res, dict) and res.get("ok") is True:
        data = res.get("data")
        return data if isinstance(data, list) else []
    if isinstance(res, list):
        return res
    return []


def _unwrap_obj(res):
    if isinstance(res, dict) and res.get("ok") is True:
        data = res.get("data")
        return data if isinstance(data, dict) else res
    if isinstance(res, dict):
        return res
    return {}


def _api_err_text(res: dict) -> str:
    status = res.get("status")
    txt = str(res.get("text", ""))[:900]
    return f"❌ API xato: {status}\n{txt}"


async def _get_cached_schools(state: FSMContext):
    """
    fetch_schools() katta list bo‘lgani uchun 1 marta olib, state’da cache qilamiz.
    Keyingi bosishlarda juda tez ishlaydi.
    """
    data = await state.get_data()
    cached = data.get("cached_schools_all")
    if isinstance(cached, list) and cached:
        return cached

    sres = await fetch_schools()
    if isinstance(sres, dict) and sres.get("ok") is False:
        return sres  # error dict

    schools = _unwrap_list(sres)
    await state.update_data(cached_schools_all=schools)
    return schools


@dp.callback_query_handler(lambda c: c.data == "noop", state="*")
async def noop(call: types.CallbackQuery):
    await call.answer()


@dp.message_handler(commands=["admin"], state="*")
async def admin_cmd(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.finish()
    await message.answer(_ui_header("Admin panel", "Bosh menyu"), parse_mode="HTML", reply_markup=admin_main_inline())
    await AdminPanel.menu.set()


@dp.callback_query_handler(lambda c: c.data == "adm:close", state="*")
async def adm_close(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo‘q", show_alert=True)
        return

    await state.finish()
    await safe_edit(call, "✅ Yopildi", reply_markup=None)
    await call.answer()


@dp.callback_query_handler(lambda c: c.data == "adm:back_main", state="*")
async def adm_back_main(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo‘q", show_alert=True)
        return

    await safe_edit(call, _ui_header("Admin panel", "Bosh menyu"), reply_markup=admin_main_inline())
    await AdminPanel.menu.set()
    await call.answer()


# ------------------------------
# DISTRICTS LIST (paginated)
# cb: adm:districts:<page>
# ------------------------------
@dp.callback_query_handler(lambda c: c.data.startswith("adm:districts:"), state="*")
async def adm_show_districts(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo‘q", show_alert=True)
        return

    try:
        page = int(call.data.split(":")[-1])
    except Exception:
        page = 1

    res = await fetch_districts()
    if isinstance(res, dict) and res.get("ok") is False:
        await safe_edit(call, _api_err_text(res), reply_markup=admin_main_inline())
        await AdminPanel.menu.set()
        await call.answer()
        return

    districts = _unwrap_list(res)
    if not districts:
        await safe_edit(call, "❌ Tumanlar topilmadi.", reply_markup=admin_main_inline())
        await AdminPanel.menu.set()
        await call.answer()
        return

    await safe_edit(
        call,
        _ui_header("Tumanlar", "Tumanlar → tanlang"),
        reply_markup=admin_districts_inline(districts, page=page),
    )
    await AdminPanel.districts_list.set()
    await call.answer()


# ------------------------------
# PICK DISTRICT
# cb: adm_dist:<did>:<back_page>
# ------------------------------
@dp.callback_query_handler(lambda c: c.data.startswith("adm_dist:"), state=AdminPanel.districts_list)
async def adm_pick_district(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo‘q", show_alert=True)
        return

    parts = call.data.split(":")
    did = int(parts[1])
    back_page = int(parts[2]) if len(parts) > 2 else 1

    await state.update_data(selected_district_id=did, districts_back_page=back_page)

    await safe_edit(
        call,
        _ui_header("Tuman tanlandi", "Tuman → Amallar") + "👇 Nima qilamiz?",
        reply_markup=admin_district_actions_inline(did, back_page=back_page),
    )
    await AdminPanel.district_selected.set()
    await call.answer()


# ------------------------------
# SHOW DISTRICT CREDS
# cb: adm_dist_show:<did>:<back_page>
# Login/parol alohida message (forward qulay)
# ------------------------------
@dp.callback_query_handler(lambda c: c.data.startswith("adm_dist_show:"), state=AdminPanel.district_selected)
async def adm_show_district_creds(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo‘q", show_alert=True)
        return

    parts = call.data.split(":")
    did = int(parts[1])
    back_page = int(parts[2]) if len(parts) > 2 else 1

    res = await fetch_district_by_id(did)
    if isinstance(res, dict) and res.get("ok") is False:
        await safe_edit(call, _api_err_text(res), reply_markup=admin_district_actions_inline(did, back_page=back_page))
        await call.answer()
        return

    obj = _unwrap_obj(res)
    username = obj.get("username", "-")
    password = obj.get("password_hash", "-")
    region = obj.get("region", "-")
    district = obj.get("district", "-")
    full_name = obj.get("full_name", "-")
    role = obj.get("role", "district")

    panel_txt = (
        _ui_header("Tuman admin", f"{region} → {district}")
        + f"\n👤 <b>Nomi:</b> {full_name}\n"
        + f"🧩 <b>Role:</b> {role}\n\n"
        + "✅ Login/parol alohida xabar bilan yuborildi (forward uchun qulay)."
    )

    await safe_edit(call, panel_txt, reply_markup=admin_district_actions_inline(did, back_page=back_page))
    await AdminPanel.district_selected.set()
    await call.answer()

    # Separate messages for forward
    await call.message.answer(f"🔑 <b>Login</b>\n<code>{username}</code>", parse_mode="HTML")
    await call.message.answer(f"🔒 <b>Parol</b>\n<code>{password}</code>", parse_mode="HTML")


# ------------------------------
# SHOW SCHOOLS IN DISTRICT (paginated) - FAST via CACHE
# cb: adm_dist_schools:<did>:<page>:<back_page>
# ------------------------------
@dp.callback_query_handler(lambda c: c.data.startswith("adm_dist_schools:"), state="*")
async def adm_show_schools_in_district(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo‘q", show_alert=True)
        return

    parts = call.data.split(":")
    did = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 1
    back_page = int(parts[3]) if len(parts) > 3 else 1

    dres = await fetch_district_by_id(did)
    if isinstance(dres, dict) and dres.get("ok") is False:
        await safe_edit(call, _api_err_text(dres), reply_markup=admin_district_actions_inline(did, back_page=back_page))
        await call.answer()
        return

    dobj = _unwrap_obj(dres)
    region = str(dobj.get("region", "")).strip()
    district = str(dobj.get("district", "")).strip()

    schools_or_err = await _get_cached_schools(state)
    if isinstance(schools_or_err, dict) and schools_or_err.get("ok") is False:
        await safe_edit(call, _api_err_text(schools_or_err), reply_markup=admin_district_actions_inline(did, back_page=back_page))
        await call.answer()
        return

    schools = schools_or_err
    filtered = [
        s for s in schools
        if str(s.get("region", "")).strip() == region and str(s.get("district", "")).strip() == district
    ]

    if not filtered:
        await safe_edit(
            call,
            _ui_header("Maktablar", f"{region} → {district}") + "\n❌ Bu tumanda maktab topilmadi.",
            reply_markup=admin_district_actions_inline(did, back_page=back_page),
        )
        await AdminPanel.district_selected.set()
        await call.answer()
        return

    await safe_edit(
        call,
        _ui_header("Maktablar", f"{region} → {district}") + "\n👇 Maktab tanlang:",
        reply_markup=admin_district_schools_inline(filtered, district_id=did, page=page, back_page=back_page),
    )
    await AdminPanel.district_schools_list.set()
    await call.answer()


# ------------------------------
# PICK SCHOOL from district list
# cb: adm_sch_in_dist:<sid>:<did>:<page>:<back_page>
# Login/parol alohida message (forward qulay)
# ------------------------------
@dp.callback_query_handler(lambda c: c.data.startswith("adm_sch_in_dist:"), state=AdminPanel.district_schools_list)
async def adm_pick_school_from_district(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo‘q", show_alert=True)
        return

    parts = call.data.split(":")
    sid = int(parts[1])
    did = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 1
    back_page = int(parts[4]) if len(parts) > 4 else 1

    res = await fetch_school_by_id(sid)
    if isinstance(res, dict) and res.get("ok") is False:
        await call.answer("❌ API xato", show_alert=True)
        return

    obj = _unwrap_obj(res)
    username = obj.get("username", "-")
    password = obj.get("password_hash", "-")
    region = obj.get("region", "-")
    district = obj.get("district", "-")
    full_name = obj.get("full_name", "-")
    role = obj.get("role", "school")

    panel_txt = (
        _ui_header("Maktab admin", f"{region} → {district}")
        + f"\n🏫 <b>Maktab:</b> {full_name}\n"
        + f"🧩 <b>Role:</b> {role}\n\n"
        + "✅ Login/parol alohida xabar bilan yuborildi (forward uchun qulay)."
    )

    back_markup = types.InlineKeyboardMarkup(row_width=1)
    back_markup.add(
        types.InlineKeyboardButton("⬅️ Maktablar ro'yxati", callback_data=f"adm_dist_schools:{did}:{page}:{back_page}"),
        types.InlineKeyboardButton("🏠 Bosh menyu", callback_data="adm:back_main"),
    )

    await safe_edit(call, panel_txt, reply_markup=back_markup)
    await AdminPanel.district_schools_list.set()
    await call.answer()

    # Separate messages for forward
    await call.message.answer(f"🔑 <b>Login</b>\n<code>{username}</code>", parse_mode="HTML")
    await call.message.answer(f"🔒 <b>Parol</b>\n<code>{password}</code>", parse_mode="HTML")