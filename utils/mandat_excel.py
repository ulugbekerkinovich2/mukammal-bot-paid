import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

from openpyxl import Workbook, load_workbook

EXCEL_PATH = os.getenv("MANDAT_RESULTS_XLSX", "mandat_results.xlsx")

_HEADERS = [
    "entrant_id", "full_name", "lang",
    "subjects_json", "scores_json", "extra_scores_json", "total_ball",
    "updated_at",
]

_LOCK = asyncio.Lock()


def _ensure_workbook() -> None:
    if os.path.exists(EXCEL_PATH):
        return
    wb = Workbook()
    ws = wb.active
    ws.title = "results"
    ws.append(_HEADERS)
    wb.save(EXCEL_PATH)


def _row_from_data(data: Dict[str, Any]) -> list:
    return [
        str(data.get("entrant_id") or ""),
        data.get("full_name") or "",
        data.get("lang") or "",
        json.dumps(data.get("subjects") or [], ensure_ascii=False),
        json.dumps(data.get("scores") or [], ensure_ascii=False),
        json.dumps(data.get("extra_scores") or [], ensure_ascii=False),
        data.get("total_ball") or "",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ]


def _data_from_row(row) -> Dict[str, Any]:
    return {
        "entrant_id": str(row[0]),
        "full_name": row[1],
        "lang": row[2],
        "subjects": json.loads(row[3]) if row[3] else [],
        "scores": json.loads(row[4]) if row[4] else [],
        "extra_scores": [tuple(x) for x in (json.loads(row[5]) if row[5] else [])],
        "total_ball": row[6],
    }


def _sync_lookup(entrant_id: str) -> Optional[Dict[str, Any]]:
    _ensure_workbook()
    wb = load_workbook(EXCEL_PATH, read_only=True)
    try:
        ws = wb["results"]
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row and str(row[0]) == str(entrant_id):
                return _data_from_row(row)
    finally:
        wb.close()
    return None


def _sync_save(data: Dict[str, Any]) -> None:
    _ensure_workbook()
    wb = load_workbook(EXCEL_PATH)
    ws = wb["results"]

    entrant_id = str(data.get("entrant_id") or "")
    target_row_idx = None
    for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if row and str(row[0]) == entrant_id:
            target_row_idx = idx
            break

    new_row = _row_from_data(data)
    if target_row_idx:
        for col, value in enumerate(new_row, start=1):
            ws.cell(row=target_row_idx, column=col, value=value)
    else:
        ws.append(new_row)

    wb.save(EXCEL_PATH)


async def lookup_cached_result(entrant_id: str) -> Optional[Dict[str, Any]]:
    loop = asyncio.get_event_loop()
    async with _LOCK:
        return await loop.run_in_executor(None, _sync_lookup, entrant_id)


async def save_result_to_cache(data: Dict[str, Any]) -> None:
    loop = asyncio.get_event_loop()
    async with _LOCK:
        await loop.run_in_executor(None, _sync_save, data)


def excel_file_exists() -> bool:
    return os.path.exists(EXCEL_PATH)
