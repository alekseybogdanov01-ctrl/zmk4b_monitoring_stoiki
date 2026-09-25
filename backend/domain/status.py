"""Статусы объекта для карты и сводок (бизнес-логика MVP).

Красный  idle     — простой (неполное звено: техника есть, звена нет)
Жёлтый   warning  — сигнал о возможном нарушении (нет нужной техники по плану)
Зелёный  ok       — по плану, отклонений нет
Салатовый info   — опережение графика (другой этап раньше плана)
Серый    no_data  — нет данных (нет снимков за период)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Чем меньше индекс — тем выше приоритет (хуже) при агрегации
STATUS_PRIORITY: List[str] = ["idle", "warning", "info", "ok", "no_data"]

STATUS_META: Dict[str, Dict[str, str]] = {
    "idle": {
        "label": "Простой",
        "color": "#E63946",
        "description": "Техника на площадке, но звено неполное — риск простоя",
    },
    "warning": {
        "label": "Возможное нарушение",
        "color": "#F4A261",
        "description": "По плану нужна техника, на снимках её нет",
    },
    "ok": {
        "label": "В норме",
        "color": "#2D6A4F",
        "description": "План и факт согласованы",
    },
    "info": {
        "label": "Опережение графика",
        "color": "#8ED44A",
        "description": "Работы идут раньше календарного плана",
    },
    "no_data": {
        "label": "Нет данных",
        "color": "#6C757D",
        "description": "Нет снимков для сопоставления с планом",
    },
}


def status_from_day(day: Dict[str, Any]) -> str:
    """Статус за один день по отчёту правил."""
    deviations = day.get("deviations") or []
    types = {d.get("type") for d in deviations}
    plan_status = day.get("plan_status")
    has_photos = bool(day.get("photo_ids"))
    has_counts = bool(day.get("counts"))

    if plan_status == "no_data" or (not has_photos and not has_counts):
        return "no_data"

    # Красный: простой (неполное звено)
    if "incomplete_link" in types:
        return "idle"

    # Синий: смена / другой этап (важнее «нет маркера плана»)
    if "unexpected_equipment" in types or plan_status == "other_stage":
        return "info"

    # Жёлтый: возможное нарушение (нужной техники нет)
    if "missing_required" in types or plan_status == "lag":
        return "warning"

    if plan_status == "on_track":
        return "ok"

    if plan_status == "no_plan":
        return "info" if has_counts else "no_data"

    return "no_data"


def worse_status(a: str, b: str) -> str:
    ia = STATUS_PRIORITY.index(a) if a in STATUS_PRIORITY else 99
    ib = STATUS_PRIORITY.index(b) if b in STATUS_PRIORITY else 99
    return a if ia <= ib else b


def site_status_from_timeline(timeline: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Худший статус среди дней со снимками; если снимков нет — no_data."""
    with_photos = [d for d in timeline if d.get("photo_ids")]
    if not with_photos:
        meta = STATUS_META["no_data"]
        last = timeline[-1]["date"] if timeline else None
        return {
            "status": "no_data",
            "label": meta["label"],
            "color": meta["color"],
            "description": meta["description"],
            "last_date": last,
        }

    code = "ok"
    last_date: Optional[str] = None
    for day in with_photos:
        st = day.get("project_status") or status_from_day(day)
        code = worse_status(code, st)
        last_date = day.get("date")

    meta = STATUS_META[code]
    return {
        "status": code,
        "label": meta["label"],
        "color": meta["color"],
        "description": meta["description"],
        "last_date": last_date,
    }


def statuses_catalog() -> List[Dict[str, str]]:
    return [{"code": code, **STATUS_META[code]} for code in STATUS_PRIORITY]
