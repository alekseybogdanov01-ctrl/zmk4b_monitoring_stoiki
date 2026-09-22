"""Сопоставление факта техники с календарным планом + отклонения (ТЗ ДГП)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set

from backend.domain.stages import (
    STAGE_LABELS_RU,
    STAGE_LINKS,
    STAGE_MARKERS,
    STAGE_OPTIONAL,
    STAGE_PRIORITY,
    SUPPORT_ONLY,
)
from backend.domain.status import status_from_day


def _as_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def aggregate_counts(detections: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for det in detections:
        code = det.get("class") or det.get("class_code")
        if code:
            counts[str(code)] += 1
    return dict(counts)


def present_classes(counts: Dict[str, int]) -> Set[str]:
    return {c for c, n in counts.items() if n > 0}


def infer_stages(present: Set[str]) -> List[str]:
    found: List[str] = []
    for stage in STAGE_PRIORITY:
        markers = STAGE_MARKERS[stage]
        if not (present & markers):
            continue
        if stage == "superstructure":
            if present & STAGE_MARKERS["piling"]:
                continue
            if present & STAGE_MARKERS["monolith"]:
                continue
        found.append(stage)
    return found


def primary_stage(inferred: List[str]) -> Optional[str]:
    return inferred[0] if inferred else None


def planned_stages_for_day(
    plan_rows: List[Dict[str, Any]], day: date
) -> List[Dict[str, Any]]:
    active: List[Dict[str, Any]] = []
    for row in plan_rows:
        start = _as_date(row["date_from"])
        end = _as_date(row["date_to"])
        if start <= day <= end:
            active.append(row)
    return active


def _link_satisfied(present: Set[str], groups: List[Set[str]]) -> bool:
    if not groups:
        return True
    return all(bool(present & g) for g in groups)


def _missing_link_groups(
    present: Set[str], groups: List[Set[str]]
) -> List[List[str]]:
    return [sorted(g) for g in groups if not (present & g)]


def _zone_of(planned: List[Dict[str, Any]], stage_code: str) -> Optional[str]:
    for p in planned:
        if p["stage_code"] == stage_code and p.get("zone"):
            return p.get("zone")
    return planned[0].get("zone") if planned else None


def analyze_day(
    *,
    day: date | str,
    counts: Dict[str, int],
    plan_rows: List[Dict[str, Any]],
    photo_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Отчёт за день: этап, план/факт, отклонения по методике ТЗ."""
    day_d = _as_date(day)
    present = present_classes(counts)
    inferred = infer_stages(present)
    primary = primary_stage(inferred)
    planned = planned_stages_for_day(plan_rows, day_d)
    planned_codes = [p["stage_code"] for p in planned]
    photo_ids = list(photo_ids or [])

    deviations: List[Dict[str, Any]] = []

    if not photo_ids and not counts:
        plan_status = "no_data"
    elif not planned:
        plan_status = "no_plan"
    else:
        main_plan = planned_codes[0]
        markers = STAGE_MARKERS.get(main_plan, set())
        has_marker = bool(present & markers)
        zone = _zone_of(planned, main_plan)
        label = STAGE_LABELS_RU.get(main_plan, main_plan)

        if has_marker:
            plan_status = "on_track"
            links = STAGE_LINKS.get(main_plan, [])
            if links and not _link_satisfied(present, links):
                missing = _missing_link_groups(present, links)
                deviations.append(
                    {
                        "type": "incomplete_link",
                        "severity": "warning",
                        "stage_code": main_plan,
                        "stage_label": label,
                        "message": (
                            f"На этапе «{label}» есть маркерная техника, "
                            f"но неполное звено (нет: "
                            f"{', '.join('/'.join(g) for g in missing)}). "
                            f"Возможно снижение темпа работ."
                        ),
                        "missing_groups": missing,
                        "photo_ids": photo_ids,
                        "zone": zone,
                    }
                )
        else:
            plan_status = "lag"
            deviations.append(
                {
                    "type": "missing_required",
                    "severity": "critical",
                    "stage_code": main_plan,
                    "stage_label": label,
                    "message": (
                        f"По плану этап «{label}», но необходимая техника "
                        f"не обнаружена (ожидалось: {', '.join(sorted(markers))})."
                    ),
                    "expected_markers": sorted(markers),
                    "photo_ids": photo_ids,
                    "zone": zone,
                }
            )

        # Техника другого этапа (не соответствует текущему плану)
        if primary and primary not in planned_codes:
            plan_status = "other_stage"
            deviations.append(
                {
                    "type": "unexpected_equipment",
                    "severity": "warning",
                    "stage_code": primary,
                    "stage_label": STAGE_LABELS_RU.get(primary, primary),
                    "message": (
                        f"Наблюдается техника этапа "
                        f"«{STAGE_LABELS_RU.get(primary, primary)}», "
                        f"тогда как по плану: "
                        f"{', '.join(STAGE_LABELS_RU.get(c, c) for c in planned_codes)}."
                    ),
                    "photo_ids": photo_ids,
                    "zone": zone,
                }
            )

        # Доп. классы-маркеры чужих этапов при on_track
        if has_marker and primary and primary == main_plan:
            foreign_markers: Set[str] = set()
            for code in STAGE_PRIORITY:
                if code in planned_codes:
                    continue
                foreign_markers |= STAGE_MARKERS[code]
            # support не считаем чужими
            foreign_hit = (present & foreign_markers) - SUPPORT_ONLY
            # маркеры текущего этапа вычитаем
            foreign_hit -= markers
            if foreign_hit and primary == main_plan:
                # уже покрыто, если primary сменился; иначе мягкое предупреждение не дублируем
                pass

    report = {
        "date": day_d.isoformat(),
        "counts": counts,
        "present_classes": sorted(present),
        "inferred_stages": inferred,
        "primary_stage": primary,
        "primary_stage_label": (
            STAGE_LABELS_RU.get(primary, primary) if primary else None
        ),
        "planned_stages": [
            {
                "stage_code": p["stage_code"],
                "stage_label": STAGE_LABELS_RU.get(p["stage_code"], p["stage_code"]),
                "date_from": str(p["date_from"])[:10],
                "date_to": str(p["date_to"])[:10],
                "zone": p.get("zone"),
            }
            for p in planned
        ],
        "plan_status": plan_status,
        "deviations": deviations,
        "photo_ids": photo_ids,
    }
    report["project_status"] = status_from_day(report)
    return report


def build_timeline(
    *,
    plan_rows: List[Dict[str, Any]],
    photos: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_day: Dict[str, Dict[str, Any]] = {}

    for photo in photos:
        day = str(photo.get("captured_at", ""))[:10]
        if not day:
            continue
        bucket = by_day.setdefault(day, {"photo_ids": [], "detections": []})
        bucket["photo_ids"].append(photo["id"])
        bucket["detections"].extend(photo.get("detections") or [])

    for row in plan_rows:
        start = _as_date(row["date_from"])
        end = _as_date(row["date_to"])
        cur = start
        # ограничиваем разворот плана (защита от огромных CSV)
        guard = 0
        while cur <= end and guard < 400:
            by_day.setdefault(cur.isoformat(), {"photo_ids": [], "detections": []})
            cur = cur + timedelta(days=1)
            guard += 1

    reports: List[Dict[str, Any]] = []
    for day in sorted(by_day.keys()):
        bucket = by_day[day]
        counts = aggregate_counts(bucket["detections"])
        reports.append(
            analyze_day(
                day=day,
                counts=counts,
                plan_rows=plan_rows,
                photo_ids=bucket["photo_ids"],
            )
        )
    return reports
