from aiogram import types
from aiogram.dispatcher import FSMContext

from loader import dp
from data.config import ADMIN_CHAT_ID

from states.adminStates import AdminPanel
from keyboards.inline.admin_inline import (
    admin_main_inline,
    admin_districts_inline,
    admin_schools_inline,
)

# ✅ Senda utils/send_req.py ichida tayyor deb aytding
from utils.send_req import (
    fetch_districts,
    fetch_district_by_id,
    fetch_schools,
    fetch_school_by_id,
)


def _parse_admin_ids(value) -> set:
    """
    ADMIN_CHAT_ID int bo‘lishi ham mumkin, string '1,2,3' bo‘lishi ham mumkin.
    """
    if value is None:
        return set()

    if isinstance(value, int):
        return {value}

    if isinstance(value, (list, tuple, set)):
        return {int(x) for x in value if str(x).isdigit()}

    s = str(value).strip()
    if not s:
        return set()

    # "123,456" yoki "123 456" holatlar
    parts = [p.strip() for p in s.replace(" ", ",").split(",") if p.strip()]
    out = set()
    for p in parts:
        if p.isdigit():
            out.add(int(p))
    return out


ADMIN_IDS = _parse_admin_ids(ADMIN_CHAT_ID)


def is_admin(user_id: int) -> bool:
    return int(user_id) in ADMIN_IDS


@dp.message_handler(commands=["admin"], state="*")
async def admin_cmd(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.finish()
    await message.answer("🛠 Admin panel:", reply_markup=admin_main_inline())
    await AdminPanel.menu.set()


@dp.message_handler(lambda m: (m.text or "").strip() == "🛠 Admin", state="*")
async def admin_btn(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.finish()
    await message.answer("🛠 Admin panel:", reply_markup=admin_main_inline())
    await AdminPanel.menu.set()


@dp.callback_query_handler(lambda c: c.data == "adm:close", state="*")
async def adm_close(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo‘q", show_alert=True)
        return

    await state.finish()
    await call.message.edit_text("✅ Yopildi", reply_markup=None)
    await call.answer()


@dp.callback_query_handler(lambda c: c.data == "adm:back_main", state="*")
async def adm_back_main(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo‘q", show_alert=True)
        return

    await call.message.edit_text("🛠 Admin panel:", reply_markup=admin_main_inline())
    await AdminPanel.menu.set()
    await call.answer()


@dp.callback_query_handler(lambda c: c.data == "adm:districts", state="*")
async def adm_show_districts(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo‘q", show_alert=True)
        return

    res = await fetch_districts()

    # res list yoki {"ok":False} bo‘lishi mumkin
    if isinstance(res, dict) and res.get("ok") is False:
        await call.message.edit_text(f"❌ API xato: {res.get('status')} \n{res.get('text')[:1000]}")
        await call.answer()
        return

    districts = res if isinstance(res, list) else []
    if not districts:
        await call.message.edit_text("❌ Tumanlar topilmadi.", reply_markup=admin_main_inline())
        await AdminPanel.menu.set()
        await call.answer()
        return

    await call.message.edit_text(
        "🏙 Tumanlardan birini tanlang:",
        reply_markup=admin_districts_inline(districts),
    )
    await AdminPanel.districts_list.set()
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("adm_dist:"), state=AdminPanel.districts_list)
async def adm_pick_district(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo‘q", show_alert=True)
        return

    did = int(call.data.split(":", 1)[1])
    res = await fetch_district_by_id(did)

    if isinstance(res, dict) and res.get("ok") is False:
        await call.message.edit_text(f"❌ API xato: {res.get('status')}\n{res.get('text')[:1000]}")
        await call.answer()
        return

    username = res.get("username", "-")
    password = res.get("password_hash", "-")
    region = res.get("region", "-")
    district = res.get("district", "-")
    full_name = res.get("full_name", "-")

    txt = (
        f"✅ <b>Tuman admin</b>\n\n"
        f"👤 <b>Nomi:</b> {full_name}\n"
        f"📍 <b>Hudud:</b> {region} | {district}\n\n"
        f"🔑 <b>Login:</b> <code>{username}</code>\n"
        f"🔒 <b>Parol:</b> <code>{password}</code>\n"
    )

    await call.message.edit_text(txt, parse_mode="HTML", reply_markup=admin_main_inline())
    await AdminPanel.menu.set()
    await call.answer()


@dp.callback_query_handler(lambda c: c.data == "adm:schools", state="*")
async def adm_show_schools(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo‘q", show_alert=True)
        return

    res = await fetch_schools()

    if isinstance(res, dict) and res.get("ok") is False:
        await call.message.edit_text(f"❌ API xato: {res.get('status')} \n{res.get('text')[:1000]}")
        await call.answer()
        return

    schools = res if isinstance(res, list) else []
    if not schools:
        await call.message.edit_text("❌ Maktablar topilmadi.", reply_markup=admin_main_inline())
        await AdminPanel.menu.set()
        await call.answer()
        return

    await call.message.edit_text(
        "🏫 Maktablardan birini tanlang:",
        reply_markup=admin_schools_inline(schools),
    )
    await AdminPanel.schools_list.set()
    await call.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("adm_sch:"), state=AdminPanel.schools_list)
async def adm_pick_school(call: types.CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo‘q", show_alert=True)
        return

    sid = int(call.data.split(":", 1)[1])
    res = await fetch_school_by_id(sid)

    if isinstance(res, dict) and res.get("ok") is False:
        await call.message.edit_text(f"❌ API xato: {res.get('status')}\n{res.get('text')[:1000]}")
        await call.answer()
        return

    username = res.get("username", "-")
    password = res.get("password_hash", "-")
    region = res.get("region", "-")
    district = res.get("district", "-")
    full_name = res.get("full_name", "-")

    txt = (
        f"✅ <b>Maktab admin</b>\n\n"
        f"🏫 <b>Maktab:</b> {full_name}\n"
        f"📍 <b>Hudud:</b> {region} | {district}\n\n"
        f"🔑 <b>Login:</b> <code>{username}</code>\n"
        f"🔒 <b>Parol:</b> <code>{password}</code>\n"
    )

    await call.message.edit_text(txt, parse_mode="HTML", reply_markup=admin_main_inline())
    await AdminPanel.menu.set()
    await call.answer()
