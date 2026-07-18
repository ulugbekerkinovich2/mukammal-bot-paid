import html
import re
import logging
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)

MANDAT_URL = "https://mandat.uzbmb.uz/Bakalavr/MainSearch"
MANDAT_TIMEOUT_SEC = 20

_ENTRANT_ID_RE = re.compile(r"^\d{5,10}$")

_NAME_RE = re.compile(r'm3-det-hero__name">([^<]*)<')
_ID_RE = re.compile(r"Abituriyent ID raqami:\s*<b>([^<]*)</b>")
_LANG_RE = re.compile(r"Ta'lim tili:\s*<b>([^<]*)</b>")
_SUBJECT_RE = re.compile(
    r'm3-det-subj__lbl">[^<]*<i[^>]*></i>\s*([^<]*)</div>\s*'
    r'<div class="m3-det-subj__val">([^<]*)</div>'
)
_SCORE_CARD_RE = re.compile(
    r"javoblar soni:\s*<b>\s*(\d+)\s*</b>.*?Ball:\s*<b>([^<]*)</b>",
    re.S,
)
_EXTRA_CARD_RE = re.compile(
    r'card-div text-center">\s*([^<:]+):\s*<br\s*/?>\s*<b>([^<]*)</b>',
)


def is_valid_entrant_id(raw: str) -> bool:
    return bool(_ENTRANT_ID_RE.match((raw or "").strip()))


async def fetch_mandat_result(entrant_id: str) -> Dict[str, Any]:
    """
    mandat.uzbmb.uz'dan rasmiy DTM natijasini oladi.
    Topilsa /Bakalavr/Details?hashId=... ga redirect qiladi va HTML natija
    bilan qaytadi. Topilmasa MainSearch sahifasida qoladi.
    """
    params = {"entrantid": entrant_id, "lang": "uz"}
    headers = {"User-Agent": "Mozilla/5.0 (compatible; DTM-Bot/1.0)"}
    timeout = aiohttp.ClientTimeout(total=MANDAT_TIMEOUT_SEC)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(MANDAT_URL, params=params, headers=headers, allow_redirects=True) as r:
                text = await r.text()
                if r.status >= 400:
                    return {"ok": False, "reason": "http_error", "status": r.status}
                if "/Bakalavr/Details" not in str(r.url):
                    return {"ok": False, "reason": "not_found"}
                data = _parse_mandat_html(text)
                if not data:
                    return {"ok": False, "reason": "parse_error"}
                return {"ok": True, "data": data}
    except Exception as e:
        logger.error("[mandat] fetch error: %s", repr(e))
        return {"ok": False, "reason": "network_error", "error": str(e)}


def _parse_mandat_html(html_text: str) -> Optional[Dict[str, Any]]:
    name_m = _NAME_RE.search(html_text)
    id_m = _ID_RE.search(html_text)
    if not name_m or not id_m:
        return None

    lang_m = _LANG_RE.search(html_text)

    subjects = [
        {"label": html.unescape(lbl).strip(), "value": html.unescape(val).strip()}
        for lbl, val in _SUBJECT_RE.findall(html_text)
    ]

    scores = [
        {"correct": int(correct), "ball": html.unescape(ball).strip()}
        for correct, ball in _SCORE_CARD_RE.findall(html_text)
    ]

    extras = [
        (html.unescape(lbl).strip(), html.unescape(val).strip())
        for lbl, val in _EXTRA_CARD_RE.findall(html_text)
    ]

    if not subjects or not scores:
        return None

    total_ball = extras[-1][1] if extras else None
    extra_scores = extras[:-1] if extras else []

    return {
        "full_name": html.unescape(name_m.group(1)).strip(),
        "entrant_id": html.unescape(id_m.group(1)).strip(),
        "lang": html.unescape(lang_m.group(1)).strip() if lang_m else "",
        "subjects": subjects,
        "scores": scores,
        "extra_scores": extra_scores,
        "total_ball": total_ball,
    }


def _fmt_pct(value: float, decimals: int = 1) -> str:
    s = f"{value:.{decimals}f}"
    return s.replace(".", ",")


def format_mandat_result(data: Dict[str, Any], bot_username: str = "") -> str:
    subjects = data.get("subjects") or []
    scores = data.get("scores") or []

    section_titles = ["Majburiy fanlar", "1-mutaxassislik fani", "2-mutaxassislik fani"]

    lines = [
        "🎓 <b>IMTIHON NATIJASI</b>",
        "",
        f"👤 {html.escape(data.get('full_name') or '', quote=False)}",
        f"🆔 ID: {html.escape(data.get('entrant_id') or '', quote=False)}",
        f"📝 Ta'lim tili: {html.escape(data.get('lang') or '', quote=False)}",
        "",
        "📚 Fanlar bo'yicha javoblar:",
        "",
    ]

    total_correct = 0
    total_questions = 0
    for i, sc in enumerate(scores):
        title = section_titles[i] if i < len(section_titles) else f"{i + 1}-fan"
        subj = subjects[i] if i < len(subjects) else {}
        correct = sc.get("correct", 0)
        pct = _fmt_pct((correct / 30) * 100)
        total_correct += correct
        total_questions += 30

        lines.append(f"{i + 1}. {title}")
        lines.append(f"• {html.escape(subj.get('value') or '', quote=False)}")
        lines.append(f"• To'g'ri: {correct}/30 ({pct}%)")
        lines.append(f"• Ball: {html.escape(sc.get('ball') or '', quote=False)}")
        lines.append("")

    overall_pct = round((total_correct / total_questions) * 100) if total_questions else 0
    lines.append(f"✅ To'g'ri javoblar: {total_correct}/{total_questions} ({overall_pct}%)")
    lines.append("")

    extra_scores = data.get("extra_scores") or []
    if extra_scores:
        lines.append("🟢 Qo'shimcha ballar:")
        for label, val in extra_scores:
            lines.append(f"• {html.escape(label, quote=False)}: {html.escape(val, quote=False)}")
        lines.append("")

    if data.get("total_ball"):
        lines.append(f"🏆 UMUMIY BALL: {html.escape(data['total_ball'], quote=False)}")
        lines.append("")

    if bot_username:
        uname = bot_username.lstrip("@")
        lines.append(f"👨‍💻 Natijalar @{uname} orqali tekshirildi")
        lines.append(f"👉 @{uname}")
        lines.append(f"👉 @{uname}")

    return "\n".join(lines).rstrip()
