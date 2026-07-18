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


_DIVIDER = "▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️"
_SECTION_NUMS = ["1️⃣", "2️⃣", "3️⃣"]


def _bar(pct: float, width: int = 10) -> str:
    filled = max(0, min(width, round(pct / 100 * width)))
    return "🟩" * filled + "⬜️" * (width - filled)


def _rate_label(pct: float) -> str:
    if pct >= 80:
        return "🔥 Ajoyib"
    if pct >= 60:
        return "👍 Yaxshi"
    if pct >= 40:
        return "🙂 O'rtacha"
    if pct >= 20:
        return "😐 Past"
    return "⚠️ Juda past"


def _motivation(pct: float) -> str:
    if pct >= 70:
        return "🚀 Zo'r natija! Shu tezlikda davom eting."
    if pct >= 50:
        return "💪 Yaxshi natija — yana biroz harakat qiling."
    if pct >= 30:
        return "📚 O'rtacha natija — mashq qilishni davom ettiring."
    return "🧠 Ko'proq tayyorgarlik ko'rish tavsiya etiladi."


def format_mandat_result(data: Dict[str, Any], bot_username: str = "") -> str:
    subjects = data.get("subjects") or []
    scores = data.get("scores") or []

    section_titles = ["Majburiy fanlar", "1-mutaxassislik fani", "2-mutaxassislik fani"]

    esc = lambda s: html.escape(s or "", quote=False)

    lines = [
        "🎓 <b>DTM IMTIHON NATIJASI</b>",
        _DIVIDER,
        "",
        f"👤 <b>{esc(data.get('full_name'))}</b>",
        f"🆔 ID: <code>{esc(data.get('entrant_id'))}</code>   📝 {esc(data.get('lang'))}",
        "",
    ]

    total_correct = 0
    total_questions = 0
    section_blocks = []
    subject_stats = []
    for i, sc in enumerate(scores):
        title = section_titles[i] if i < len(section_titles) else f"{i + 1}-fan"
        num = _SECTION_NUMS[i] if i < len(_SECTION_NUMS) else f"{i + 1}."
        subj = subjects[i] if i < len(subjects) else {}
        correct = sc.get("correct", 0)
        pct_num = (correct / 30) * 100
        pct = _fmt_pct(pct_num)
        total_correct += correct
        total_questions += 30
        subject_stats.append((title, pct_num))

        section_blocks.append(
            f"{num} <b>{title}</b>\n"
            f"<i>{esc(subj.get('value'))}</i>\n"
            f"✅ {correct}/30 ({pct}%)   🏅 {esc(sc.get('ball'))} ball\n"
            f"{_bar(pct_num)}"
        )

    lines.append("<blockquote>" + "\n\n".join(section_blocks) + "</blockquote>")
    lines.append("")

    overall_pct = round((total_correct / total_questions) * 100) if total_questions else 0
    lines.append(_DIVIDER)
    lines.append(f"📊 Jami to'g'ri: <b>{total_correct}/{total_questions}</b> ({overall_pct}%)")
    lines.append(_bar(overall_pct))
    lines.append("")

    if len(subject_stats) >= 2:
        best = max(subject_stats, key=lambda x: x[1])
        worst = min(subject_stats, key=lambda x: x[1])
        lines.append("🔎 <b>Tahlil:</b>")
        lines.append(f"🥇 Eng kuchli: {esc(best[0])} ({_fmt_pct(best[1])}%)")
        if worst[0] != best[0]:
            lines.append(f"🎯 E'tibor bering: {esc(worst[0])} ({_fmt_pct(worst[1])}%)")
        lines.append(f"{_rate_label(overall_pct)} — {_motivation(overall_pct)}")
        lines.append("")

    extra_scores = data.get("extra_scores") or []
    if extra_scores:
        extras_str = "   ".join(f"{esc(label)}: {esc(val)}" for label, val in extra_scores)
        lines.append(f"🟢 {extras_str}")

    if data.get("total_ball"):
        lines.append("")
        lines.append(f"🏆 <b>UMUMIY BALL: {esc(data['total_ball'])}</b>")

    lines.append(_DIVIDER)

    if bot_username:
        uname = bot_username.lstrip("@")
        lines.append("")
        lines.append(f"👨‍💻 Natijalar @{uname} orqali tekshirildi")

    return "\n".join(lines).rstrip()
