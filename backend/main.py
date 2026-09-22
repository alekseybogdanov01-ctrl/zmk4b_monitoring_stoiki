"""FastAPI: детекция техники + сопоставление с календарным планом (ТЗ ДГП)."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.domain.rules import analyze_day, build_timeline, aggregate_counts
from backend.domain.stages import STAGE_LABELS_RU, stages_catalog
from backend.domain.status import site_status_from_timeline, statuses_catalog
from backend.plan_parse import parse_plan_bytes
from backend import store
from ml.classes import CLASS_COLORS, CLASS_LABELS_RU, CLASS_MAPPING, CONFIDENCE_BY_CLASS
from ml.infer import classes_catalog, detect_bytes, load_model, resolve_weights

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_UPLOAD_MB = 25

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


class HealthResponse(BaseModel):
    status: str
    model: str
    model_ready: bool
    classes: int


class SiteIn(BaseModel):
    name: str
    lat: float = 55.7558
    lng: float = 37.6173
    address: Optional[str] = None


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
    result = detect_bytes(raw)
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
    except Exception:
        logger.exception("Seed skipped")


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    path = resolve_weights()
    ready = False
    try:
        model = load_model()
        ready = model is not None
    except Exception:
        ready = False
    return HealthResponse(
        status="ok" if ready else "degraded",
        model=path,
        model_ready=ready,
        classes=len(CLASS_MAPPING),
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
    )


# ── Sites ──────────────────────────────────────────────────────────

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


@app.get("/api/sites")
def api_list_sites() -> Dict[str, Any]:
    """Единый список ЖК для карты и таблицы (одни и те же объекты)."""
    sites = store.list_sites()
    enriched = []
    for s in sites:
        photos = store.list_photos(s["id"])
        timeline = build_timeline(plan_rows=s.get("plan") or [], photos=photos)
        status_payload = site_status_from_timeline(timeline)
        if not photos and s.get("seed_status"):
            from backend.domain.status import STATUS_META

            code = s["seed_status"]
            meta = STATUS_META[code]
            status_payload = {
                "status": code,
                "label": meta["label"],
                "color": meta["color"],
                "description": meta["description"],
                "last_date": None,
            }

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
                "comment": comment,
                "thumb_url": thumb,
            }
        )

    order = {sid: i for i, sid in enumerate(_SEED_ORDER)}
    enriched.sort(key=lambda x: order.get(x["id"], 999))
    return {"sites": enriched, "statuses": statuses_catalog()}


@app.post("/api/sites")
def api_create_site(body: SiteIn) -> Dict[str, Any]:
    site = store.upsert_site(
        {
            "id": str(uuid.uuid4()),
            "name": body.name,
            "lat": body.lat,
            "lng": body.lng,
            "address": body.address,
            "plan": [],
        }
    )
    return site


@app.get("/api/sites/{site_id}")
def api_get_site(site_id: str) -> Dict[str, Any]:
    site = store.get_site(site_id)
    if not site:
        raise HTTPException(404, "Объект не найден")
    photos = store.list_photos(site_id)
    timeline = build_timeline(plan_rows=site.get("plan") or [], photos=photos)
    status_payload = site_status_from_timeline(timeline)
    if not photos and site.get("seed_status"):
        from backend.domain.status import STATUS_META

        code = site["seed_status"]
        meta = STATUS_META[code]
        status_payload = {
            "status": code,
            "label": meta["label"],
            "color": meta["color"],
            "description": meta["description"],
            "last_date": None,
        }
    return {
        **site,
        "photos_count": len(photos),
        "photos": [
            {
                "id": p["id"],
                "captured_at": p["captured_at"],
                "filename": p["filename"],
                "file_url": f"/api/photos/{p['id']}/file",
                "comment": p.get("comment"),
            }
            for p in photos
        ],
        "project_status": status_payload,
        "comment": site.get("comment"),
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
            "id": str(uuid.uuid4()),
            "name": site_name,
            "lat": lat,
            "lng": lng,
            "address": "Демо",
            "plan": plan,
            "is_demo": True,
        }
    )
    store.set_site_plan(site["id"], plan)

    uploaded: List[Dict[str, Any]] = []
    errors: List[str] = []

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
            uploaded.append(
                {
                    "id": photo["id"],
                    "captured_at": photo["captured_at"],
                    "filename": filename,
                    "counts": result["counts"],
                    "detections_count": len(result["detections"]),
                }
            )
        except Exception as exc:
            logger.exception("demo photo failed")
            errors.append(f"{filename}: {exc}")

    all_photos = store.list_photos(site["id"])
    timeline = build_timeline(plan_rows=plan, photos=all_photos)

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
    }
