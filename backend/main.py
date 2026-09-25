"""FastAPI: детекция техники + сопоставление с календарным планом (ТЗ ДГП)."""

from __future__ import annotations

import io
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from backend.domain.rules import analyze_day, build_timeline, aggregate_counts
from backend.domain.stages import STAGE_LABELS_RU, STAGE_PRIORITY, stages_catalog
from backend.domain.status import (
    STATUS_META,
    STATUS_PRIORITY,
    site_status_from_timeline,
    statuses_catalog,
)
from backend.plan_parse import parse_plan_bytes
from backend.nspd import NspdError, NspdNotFound, lookup_parcel
from backend import store
from ml.classes import CLASS_COLORS, CLASS_LABELS_RU, CLASS_MAPPING, CONFIDENCE_BY_CLASS
from ml.infer import (
    classes_catalog,
    detect_bytes,
    is_fallback_weights,
    load_model,
    model_class_coverage,
    resolve_weights,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_UPLOAD_MB = 25
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_PACK_DIR = PROJECT_ROOT / "Демо"
DEMO_SITE_ID = "demo"

app = FastAPI(
    title="Build Watch",
    description=(
        "Мониторинг стройплощадки: детекция техники, сопоставление "
        "с календарным планом СМР и выявление отклонений (ТЗ ДГП Москвы)."
    ),
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DetectionOut(BaseModel):
    class_code: str = Field(alias="class")
    label: str
    confidence: float
    bbox: List[float]
    color: str

    model_config = {"populate_by_name": True}


class DetectResponse(BaseModel):
    width: int
    height: int
    model: str
    detections: List[DetectionOut]
    counts: Dict[str, int]
    stats_before_filter: Dict[str, int]
    stats_after_filter: Dict[str, int]
    inference_ms: float


class HealthResponse(BaseModel):
    status: str
    model: str
    model_ready: bool
    classes: int
    weights_ok: bool
    covered_classes: int


class SiteIn(BaseModel):
    name: Optional[str] = None
    lat: float
    lng: float
    address: Optional[str] = None
    cadastral_number: str


def _detections_out(raw_dets: List[Dict[str, Any]]) -> List[DetectionOut]:
    out: List[DetectionOut] = []
    for det in raw_dets:
        code = det["class"]
        out.append(
            DetectionOut(
                class_code=code,
                label=CLASS_LABELS_RU.get(code, code),
                confidence=det["confidence"],
                bbox=det["bbox"],
                color=CLASS_COLORS.get(code, "#888888"),
            )
        )
    return out


def _run_detect(raw: bytes) -> Dict[str, Any]:
    started = time.perf_counter()
    result = detect_bytes(raw)
    result["inference_ms"] = round((time.perf_counter() - started) * 1000, 1)
    counts: Dict[str, int] = {}
    for det in result["detections"]:
        code = det["class"]
        counts[code] = counts.get(code, 0) + 1
    result["counts"] = counts
    return result


@app.on_event("startup")
def _warmup() -> None:
    store.ensure_dirs()
    path = resolve_weights()
    logger.info("ML weights: %s", path)
    try:
        model = load_model()
        logger.info("Model loaded, nc=%s names=%s", len(model.names), model.names)
    except Exception:
        logger.exception("Не удалось прогреть модель при старте")
    # seed минимальных сайтов, если пусто
    try:
        from backend.seed import ensure_seed

        ensure_seed()
        store.ensure_object_numbers()
    except Exception:
        logger.exception("Seed skipped")


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    path = resolve_weights()
    ready = False
    covered = 0
    try:
        model = load_model()
        ready = model is not None
        covered = model_class_coverage(model)
    except Exception:
        ready = False

    total = len(CLASS_MAPPING)
    weights_ok = ready and not is_fallback_weights(path)
    if not ready:
        status = "error"
    elif weights_ok and covered == total:
        status = "ok"
    else:
        status = "degraded"

    return HealthResponse(
        status=status,
        model=path,
        model_ready=ready,
        classes=total,
        weights_ok=weights_ok,
        covered_classes=covered,
    )


@app.get("/api/classes")
def get_classes() -> Dict[str, Any]:
    return {
        "classes": classes_catalog(),
        "confidence_by_class": CONFIDENCE_BY_CLASS,
    }


@app.get("/api/stages")
def get_stages() -> Dict[str, Any]:
    return {"stages": stages_catalog(), "labels": STAGE_LABELS_RU}


@app.get("/api/statuses")
def get_statuses() -> Dict[str, Any]:
    return {"statuses": statuses_catalog()}


@app.post("/api/detect", response_model=DetectResponse)
async def detect(file: UploadFile = File(...)) -> DetectResponse:
    filename = file.filename or "frame.jpg"
    suffix = Path(filename).suffix.lower() or ".jpg"
    if suffix not in ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемый формат {suffix}. Допустимо: {sorted(ALLOWED_EXT)}",
        )

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Пустой файл")
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"Файл больше {MAX_UPLOAD_MB} МБ",
        )

    try:
        result = _run_detect(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Ошибка инференса")
        raise HTTPException(status_code=503, detail=f"Ошибка модели: {exc}") from exc

    return DetectResponse(
        width=result["width"],
        height=result["height"],
        model=result["model"],
        detections=_detections_out(result["detections"]),
        counts=result["counts"],
        stats_before_filter=result["stats_before_filter"],
        stats_after_filter=result["stats_after_filter"],
        inference_ms=result["inference_ms"],
    )


# ── Sites ──────────────────────────────────────────────────────────

_COLOR_NOTE = re.compile(
    r"\s*\((?:красн\w*|жёлт\w*|желт\w*|зелён\w*|зелен\w*|син\w*|сер\w*)\)",
    re.IGNORECASE,
)


def _plain_text(text: Optional[str]) -> str:
    """Убирает пометки цвета вроде «(синий)» из текстов для интерфейса."""
    return _COLOR_NOTE.sub("", text or "")


_SEED_ORDER = [
    "jk-idle-1",
    "jk-idle-2",
    "jk-warn-1",
    "jk-warn-2",
    "jk-ok-1",
    "jk-ok-2",
    "jk-info-1",
    "jk-info-2",
    "jk-nodata-1",
    "jk-nodata-2",
]


def _site_status_payload(
    site: Dict[str, Any],
    timeline: List[Dict[str, Any]],
    photos: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Статус объекта; для сид-объектов без съёмки берём заданный сценарием."""
    if not photos and site.get("seed_status"):
        code = site["seed_status"]
        meta = STATUS_META[code]
        return {
            "status": code,
            "label": meta["label"],
            "color": meta["color"],
            "description": meta["description"],
            "last_date": None,
        }
    return site_status_from_timeline(timeline)


@app.get("/api/sites")
def api_list_sites() -> Dict[str, Any]:
    """Единый список ЖК для карты и таблицы (одни и те же объекты)."""
    sites = store.list_sites()
    enriched = []
    for s in sites:
        photos = store.list_photos(s["id"])
        timeline = build_timeline(plan_rows=s.get("plan") or [], photos=photos)
        status_payload = _site_status_payload(s, timeline, photos)

        comment = s.get("comment") or ""
        if not comment:
            for day in reversed(timeline):
                if day.get("deviations"):
                    comment = day["deviations"][0].get("message", "")
                    break

        thumb = None
        if photos:
            thumb = f"/api/photos/{photos[-1]['id']}/file"

        enriched.append(
            {
                **s,
                "photos_count": len(photos),
                "last_status": status_payload["status"],
                "last_status_label": status_payload["label"],
                "last_status_color": status_payload["color"],
                "last_status_description": status_payload.get("description"),
                "last_date": status_payload.get("last_date"),
                "project_status": status_payload,
                "comment": _plain_text(comment),
                "thumb_url": thumb,
            }
        )

    order = {sid: i for i, sid in enumerate(_SEED_ORDER)}
    enriched.sort(key=lambda x: order.get(x["id"], 999))
    return {"sites": enriched, "statuses": statuses_catalog()}


ATTENTION_STATUSES = ("idle", "warning")

DEVIATION_LABELS = {
    "missing_required": "Нет необходимой техники",
    "incomplete_link": "Неполное звено",
    "unexpected_equipment": "Техника не под этап",
}


@app.get("/api/dashboard")
def api_dashboard() -> Dict[str, Any]:
    """Сводка по всем объектам города: что требует внимания в первую очередь."""
    rows: List[Dict[str, Any]] = []
    status_counts: Dict[str, int] = {code: 0 for code in STATUS_PRIORITY}
    deviation_counts: Dict[str, int] = {}
    stage_counts: Dict[str, Dict[str, int]] = {}
    equipment_counts: Dict[str, int] = {}
    total_photos = 0

    for site in store.list_sites():
        if site.get("address") == "Демо" or site.get("id") == DEMO_SITE_ID or site.get("name") == "ДЕМО":
            continue
        photos = store.list_photos(site["id"])
        for photo in photos:
            for det in photo.get("detections") or []:
                code = det.get("class")
                if code:
                    equipment_counts[code] = equipment_counts.get(code, 0) + 1
        plan = site.get("plan") or []
        timeline = build_timeline(plan_rows=plan, photos=photos)
        payload = _site_status_payload(site, timeline, photos)
        total_photos += len(photos)

        days_with_photos = [d for d in timeline if d.get("photo_ids")]
        last_day = days_with_photos[-1] if days_with_photos else None

        site_deviations: List[Dict[str, Any]] = []
        for day in timeline:
            for dev in day.get("deviations") or []:
                site_deviations.append({**dev, "date": day["date"]})
                deviation_counts[dev["type"]] = deviation_counts.get(dev["type"], 0) + 1

        status = payload["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

        reference_day = last_day or (timeline[-1] if timeline else None)
        planned_now = [
            p["stage_code"] for p in (reference_day or {}).get("planned_stages") or []
        ]
        for code in planned_now:
            bucket = stage_counts.setdefault(code, {"planned": 0, "confirmed": 0})
            bucket["planned"] += 1
            if last_day and last_day.get("primary_stage") == code:
                bucket["confirmed"] += 1

        rows.append(
            {
                "id": site["id"],
                "object_no": site.get("object_no"),
                "name": site["name"],
                "address": site.get("address"),
                "cadastral_number": site.get("cadastral_number"),
                "lat": site.get("lat"),
                "lng": site.get("lng"),
                "status": status,
                "status_label": payload["label"],
                "status_color": payload["color"],
                "status_description": payload.get("description"),
                "last_date": payload.get("last_date"),
                "photos_count": len(photos),
                "last_photo_id": photos[-1]["id"] if photos else None,
                "thumb_url": (
                    f"/api/photos/{photos[-1]['id']}/file" if photos else None
                ),
                "comment": _plain_text(site.get("comment") or ""),
                "planned_stages": [
                    {"code": c, "label": STAGE_LABELS_RU.get(c, c)} for c in planned_now
                ],
                "fact_stage": (last_day or {}).get("primary_stage"),
                "fact_stage_label": (last_day or {}).get("primary_stage_label"),
                "deviations_count": len(site_deviations),
                "top_deviation": site_deviations[-1] if site_deviations else None,
            }
        )

    rows.sort(key=lambda r: r.get("object_no") or 10**6)

    def severity_rank(row: Dict[str, Any]) -> int:
        code = row["status"]
        return STATUS_PRIORITY.index(code) if code in STATUS_PRIORITY else 99

    attention = sorted(
        (r for r in rows if r["status"] in ATTENTION_STATUSES),
        key=lambda r: (severity_rank(r), -r["deviations_count"], r["name"]),
    )

    stage_order = {code: i for i, code in enumerate(STAGE_PRIORITY)}

    return {
        "totals": {
            "sites": len(rows),
            "attention": len(attention),
            "with_data": sum(1 for r in rows if r["photos_count"]),
            "without_data": sum(1 for r in rows if not r["photos_count"]),
            "photos": total_photos,
            "deviations": sum(deviation_counts.values()),
            "ok": status_counts.get("ok", 0),
            "equipment": sum(equipment_counts.values()),
        },
        "by_status": [
            {"code": code, **STATUS_META[code], "count": status_counts.get(code, 0)}
            for code in STATUS_PRIORITY
        ],
        "by_deviation": [
            {"type": t, "label": DEVIATION_LABELS.get(t, t), "count": n}
            for t, n in sorted(deviation_counts.items(), key=lambda kv: -kv[1])
        ],
        "by_equipment": [
            {
                "code": code,
                "label": CLASS_LABELS_RU.get(code, code),
                "color": CLASS_COLORS.get(code, "#6C757D"),
                "count": n,
            }
            for code, n in sorted(equipment_counts.items(), key=lambda kv: -kv[1])
        ],
        "by_stage": [
            {
                "code": code,
                "label": STAGE_LABELS_RU.get(code, code),
                "planned": data["planned"],
                "confirmed": data["confirmed"],
            }
            for code, data in sorted(
                stage_counts.items(), key=lambda kv: stage_order.get(kv[0], 99)
            )
        ],
        "attention": attention,
        "sites": rows,
    }


def _same_cadastral(left: str, right: str) -> bool:
    def compact(value: str) -> str:
        return "".join(ch for ch in value.lower() if ch.isalnum())

    a, b = compact(left), compact(right)
    return bool(a) and a == b


@app.get("/api/sites/export")
def api_export_sites() -> Response:
    """Все стройки портфеля в Excel, независимо от фильтра на экране."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    rows = api_dashboard()["sites"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Объекты"
    headers = [
        "ИД",
        "Название",
        "Адрес",
        "Кадастровый номер",
        "Статус",
        "План",
        "Факт",
        "Дата съёмки",
        "Снимков",
        "Отклонений",
        "Широта",
        "Долгота",
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E79")
        cell.alignment = Alignment(vertical="center")
    for site in rows:
        plan = ", ".join(p["label"] for p in (site.get("planned_stages") or [])) or "—"
        ws.append(
            [
                site.get("object_no") or "",
                site.get("name") or "",
                site.get("address") or "",
                site.get("cadastral_number") or "",
                site.get("status_label") or "",
                plan,
                site.get("fact_stage_label") or "—",
                site.get("last_date") or "",
                site.get("photos_count") or 0,
                site.get("deviations_count") or 0,
                site.get("lat"),
                site.get("lng"),
            ]
        )
    for column, width in {
        "A": 8,
        "B": 28,
        "C": 28,
        "D": 24,
        "E": 24,
        "F": 36,
        "G": 36,
        "H": 14,
        "I": 12,
        "J": 14,
        "K": 12,
        "L": 12,
    }.items():
        ws.column_dimensions[column].width = width
    ws.auto_filter.ref = ws.dimensions
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=sites.xlsx",
            "Cache-Control": "no-store",
        },
    )


@app.get("/api/nspd/parcel")
def api_nspd_parcel(cadastral: str) -> Dict[str, Any]:
    """Адрес и центр участка из НСПД по кадастровому номеру."""
    try:
        return lookup_parcel(cadastral)
    except NspdNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except NspdError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/sites")
def api_create_site(body: SiteIn) -> Dict[str, Any]:
    cadastral = (body.cadastral_number or "").strip()
    if not cadastral:
        raise HTTPException(400, "Укажите кадастровый номер земельного участка")
    address = (body.address or "").strip() or None
    for existing in store.list_sites():
        current = (existing.get("cadastral_number") or "").strip()
        if current and _same_cadastral(current, cadastral):
            raise HTTPException(
                409,
                f"Участок {cadastral} уже есть у «{existing.get('name')}»",
            )
    return store.insert_site(
        {
            "name": (body.name or "").strip(),
            "lat": body.lat,
            "lng": body.lng,
            "address": address,
            "cadastral_number": cadastral,
            "plan": [],
        }
    )


@app.get("/api/sites/{site_id}")
def api_get_site(site_id: str) -> Dict[str, Any]:
    site = store.get_site(site_id)
    if not site:
        raise HTTPException(404, "Объект не найден")
    photos = store.list_photos(site_id)
    timeline = build_timeline(plan_rows=site.get("plan") or [], photos=photos)
    status_payload = _site_status_payload(site, timeline, photos)
    return {
        **site,
        "photos_count": len(photos),
        "photos": [
            {
                "id": p["id"],
                "captured_at": p["captured_at"],
                "filename": p["filename"],
                "file_url": f"/api/photos/{p['id']}/file",
                "comment": _plain_text(p.get("comment")),
            }
            for p in photos
        ],
        "project_status": status_payload,
        "comment": _plain_text(site.get("comment")),
    }

@app.post("/api/sites/{site_id}/plan")
async def api_upload_plan(
    site_id: str, file: UploadFile = File(...)
) -> Dict[str, Any]:
    site = store.get_site(site_id)
    if not site:
        raise HTTPException(404, "Объект не найден")
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Пустой файл плана")
    try:
        plan = parse_plan_bytes(raw, file.filename or "plan.csv")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    updated = store.set_site_plan(site_id, plan)
    return {"site_id": site_id, "plan": updated["plan"]}


@app.post("/api/sites/{site_id}/photos")
async def api_upload_photo(
    site_id: str,
    file: UploadFile = File(...),
    captured_at: str = Form(...),
) -> Dict[str, Any]:
    site = store.get_site(site_id)
    if not site:
        raise HTTPException(404, "Объект не найден")

    filename = file.filename or "frame.jpg"
    suffix = Path(filename).suffix.lower() or ".jpg"
    if suffix not in ALLOWED_EXT:
        raise HTTPException(400, f"Неподдерживаемый формат {suffix}")

    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Пустой файл")
    if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, f"Файл больше {MAX_UPLOAD_MB} МБ")

    try:
        result = _run_detect(raw)
    except Exception as exc:
        logger.exception("detect failed")
        raise HTTPException(503, f"Ошибка модели: {exc}") from exc

    try:
        photo = store.save_photo_bytes(
            site_id,
            raw,
            filename=filename,
            captured_at=captured_at,
            detections=result["detections"],
            width=result["width"],
            height=result["height"],
            model=result["model"],
        )
    except KeyError:
        raise HTTPException(404, "Объект не найден") from None

    day = analyze_day(
        day=captured_at[:10],
        counts=result["counts"],
        plan_rows=site.get("plan") or [],
        photo_ids=[photo["id"]],
    )
    return {
        "photo": {
            **photo,
            "detections": [
                {
                    "class": d["class"],
                    "label": CLASS_LABELS_RU.get(d["class"], d["class"]),
                    "confidence": d["confidence"],
                    "bbox": d["bbox"],
                    "color": CLASS_COLORS.get(d["class"], "#888"),
                }
                for d in photo["detections"]
            ],
        },
        "day_report": day,
    }


@app.get("/api/sites/{site_id}/photos")
def api_list_photos(site_id: str) -> Dict[str, Any]:
    if not store.get_site(site_id):
        raise HTTPException(404, "Объект не найден")
    photos = store.list_photos(site_id)
    slim = [
        {
            "id": p["id"],
            "captured_at": p["captured_at"],
            "filename": p["filename"],
            "counts": aggregate_counts(p.get("detections") or []),
            "detections_count": len(p.get("detections") or []),
        }
        for p in photos
    ]
    return {"photos": slim}


@app.get("/api/sites/{site_id}/timeline")
def api_timeline(site_id: str) -> Dict[str, Any]:
    site = store.get_site(site_id)
    if not site:
        raise HTTPException(404, "Объект не найден")
    photos = store.list_photos(site_id)
    timeline = build_timeline(plan_rows=site.get("plan") or [], photos=photos)
    return {
        "site_id": site_id,
        "plan": site.get("plan") or [],
        "timeline": timeline,
    }


@app.get("/api/photos/{photo_id}")
def api_get_photo(photo_id: str) -> Dict[str, Any]:
    photo = store.get_photo(photo_id)
    if not photo:
        raise HTTPException(404, "Фото не найдено")
    site = store.get_site(photo["site_id"])
    plan = (site or {}).get("plan") or []
    counts = aggregate_counts(photo.get("detections") or [])
    day = analyze_day(
        day=photo["captured_at"],
        counts=counts,
        plan_rows=plan,
        photo_ids=[photo_id],
    )
    dets = [
        {
            "class": d["class"],
            "label": CLASS_LABELS_RU.get(d["class"], d["class"]),
            "confidence": d["confidence"],
            "bbox": d["bbox"],
            "color": CLASS_COLORS.get(d["class"], "#888"),
        }
        for d in photo.get("detections") or []
    ]
    return {
        "photo": {**photo, "detections": dets, "file_url": f"/api/photos/{photo_id}/file"},
        "day_report": day,
        "site": {"id": site["id"], "name": site["name"]} if site else None,
    }


@app.get("/api/photos/{photo_id}/file")
def api_photo_file(photo_id: str) -> FileResponse:
    photo = store.get_photo(photo_id)
    if not photo:
        raise HTTPException(404, "Фото не найдено")
    path = store.photo_file_path(photo)
    if not path.exists():
        raise HTTPException(404, "Файл отсутствует на диске")
    return FileResponse(path)


# ── Шаблон календарного плана ──


@app.get("/api/plan/template")
def api_plan_template() -> Response:
    """Excel-шаблон плана: этап, начало, конец."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "План"
    ws.append(["stage", "date_from", "date_to"])
    ws.append(["расчистка участка", "2025-02-01", "2025-02-20"])
    ws.append(["откопка котлована", "2025-03-01", "2025-03-20"])
    ws.append(["устройство фундаментов", "2025-03-18", "2025-04-05"])
    ws.append(["монтаж каркаса", "2025-04-01", "2025-04-25"])
    ws.append(["благоустройство", "2025-04-20", "2025-05-15"])
    for column, width in {"A": 28, "B": 14, "C": 14}.items():
        ws.column_dimensions[column].width = width
    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="plan_template.xlsx"'},
    )


# ── Готовый пакет из папки Демо: график + фото/разбор ──


def _demo_plan_path() -> Path:
    for name in ("календарный_план.xlsx", "календарный_план.csv"):
        path = DEMO_PACK_DIR / "график" / name
        if path.is_file():
            return path
    raise HTTPException(
        404,
        "Демо-пакет не найден: в папке Демо/график нет календарного плана.",
    )


def _demo_shot_paths() -> List[Path]:
    folder = DEMO_PACK_DIR / "фото" / "разбор"
    if not folder.is_dir():
        raise HTTPException(404, "В демо-пакете нет папки «снимки»")
    shots = sorted(
        p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED_EXT
    )
    if not shots:
        raise HTTPException(404, "В демо-пакете нет снимков")
    return shots


@app.get("/api/demo/pack")
def api_demo_pack() -> Dict[str, Any]:
    """Описание готового пакета: фронт подставляет файлы в форму вкладки «Демо»."""
    plan = _demo_plan_path()
    shots = _demo_shot_paths()
    return {
        "site_name": "ДЕМО",
        "base_date": "2025-01-10",
        "step_days": 10,
        "plan": {"name": plan.name, "url": "/api/demo/pack/plan"},
        "photos": [
            {"name": p.name, "url": f"/api/demo/pack/photo/{i}"}
            for i, p in enumerate(shots)
        ],
    }


@app.get("/api/demo/pack/plan")
def api_demo_pack_plan() -> FileResponse:
    path = _demo_plan_path()
    media = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if path.suffix.lower() == ".xlsx"
        else "text/csv"
    )
    return FileResponse(path, media_type=media, filename=path.name)


@app.get("/api/demo/pack/photo/{index}")
def api_demo_pack_photo(index: int) -> FileResponse:
    shots = _demo_shot_paths()
    if index < 0 or index >= len(shots):
        raise HTTPException(404, "Снимок не найден")
    path = shots[index]
    return FileResponse(path, media_type="image/jpeg", filename=path.name)


# ── Demo one-shot (ТЗ: загрузка плана + снимков → вся логика) ──


@app.post("/api/demo/analyze")
async def api_demo_analyze(
    plan_file: UploadFile = File(...),
    photos: List[UploadFile] = File(...),
    dates: str = Form(...),
    site_name: str = Form("Демо-площадка"),
    lat: float = Form(55.7558),
    lng: float = Form(37.6173),
) -> Dict[str, Any]:
    """
    Полный сценарий ТЗ:
    календарный план + пачка снимков с датами → детекции → отклонения.
    dates — JSON-массив дат ISO (YYYY-MM-DD), длина = числу photos.
    """
    import json as _json

    request_started = time.perf_counter()
    plan_raw = await plan_file.read()
    if not plan_raw:
        raise HTTPException(400, "Пустой файл плана")
    try:
        plan = parse_plan_bytes(plan_raw, plan_file.filename or "plan.csv")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    try:
        date_list = _json.loads(dates)
    except _json.JSONDecodeError as exc:
        raise HTTPException(400, "dates должен быть JSON-массивом строк") from exc

    if not isinstance(date_list, list) or len(date_list) != len(photos):
        raise HTTPException(
            400,
            f"Число дат ({len(date_list) if isinstance(date_list, list) else '?'}) "
            f"должно совпадать с числом фото ({len(photos)})",
        )

    site = store.upsert_site(
        {
            "id": DEMO_SITE_ID,
            "name": site_name or "ДЕМО",
            "lat": lat,
            "lng": lng,
            "address": "Демо",
            "plan": plan,
            "is_demo": True,
        }
    )
    store.set_site_plan(site["id"], plan)
    store.clear_site_photos(site["id"])

    uploaded: List[Dict[str, Any]] = []
    errors: List[str] = []
    inference_times: List[float] = []

    for file, captured_at in zip(photos, date_list):
        filename = file.filename or "frame.jpg"
        suffix = Path(filename).suffix.lower() or ".jpg"
        raw = await file.read()
        if not raw:
            errors.append(f"{filename}: пустой файл")
            continue
        if suffix not in ALLOWED_EXT:
            errors.append(f"{filename}: формат {suffix}")
            continue
        try:
            result = _run_detect(raw)
            photo = store.save_photo_bytes(
                site["id"],
                raw,
                filename=filename,
                captured_at=str(captured_at)[:10],
                detections=result["detections"],
                width=result["width"],
                height=result["height"],
                model=result["model"],
            )
            inference_times.append(result["inference_ms"])
            uploaded.append(
                {
                    "id": photo["id"],
                    "captured_at": photo["captured_at"],
                    "filename": filename,
                    "counts": result["counts"],
                    "detections_count": len(result["detections"]),
                    "inference_ms": result["inference_ms"],
                }
            )
        except Exception as exc:
            logger.exception("demo photo failed")
            errors.append(f"{filename}: {exc}")

    all_photos = store.list_photos(site["id"])
    matching_started = time.perf_counter()
    timeline = build_timeline(plan_rows=plan, photos=all_photos)
    matching_ms = round((time.perf_counter() - matching_started) * 1000, 1)

    # сводка отклонений
    deviations_flat: List[Dict[str, Any]] = []
    for day in timeline:
        for d in day.get("deviations") or []:
            deviations_flat.append({**d, "date": day["date"]})

    session = store.save_demo_session(
        {
            "id": str(uuid.uuid4()),
            "site_id": site["id"],
            "created_at": site.get("created_at"),
        }
    )

    return {
        "session_id": session["id"],
        "site": site,
        "plan": plan,
        "photos": uploaded,
        "timeline": timeline,
        "deviations": deviations_flat,
        "errors": errors,
        "methodology": stages_catalog(),
        "performance": {
            "photos": len(inference_times),
            "detect_total_ms": round(sum(inference_times), 1),
            "detect_avg_ms": (
                round(sum(inference_times) / len(inference_times), 1)
                if inference_times
                else None
            ),
            "detect_max_ms": round(max(inference_times), 1) if inference_times else None,
            "matching_ms": matching_ms,
            "total_ms": round((time.perf_counter() - request_started) * 1000, 1),
        },
    }
