"""Синтетические ЖК + тестовые фото + комментарии бизнес-логики.

Карта и список ЖК читают один и тот же /api/sites (SEED_SITES).
"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from backend import store
from backend.domain.status import STATUS_META
from ml.classes import CLASS_COLORS

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = PROJECT_ROOT / "Демо"
TEST_PHOTOS_DIR = SAMPLES_DIR / "test_photos"
SEED_VERSION = 9

EXAMPLE_CSV = """stage,date_from,date_to
clearing,2025-02-01,2025-02-20
excavation,2025-03-01,2025-03-20
foundations,2025-03-18,2025-04-05
frame,2025-04-01,2025-04-25
landscaping,2025-04-20,2025-05-15
"""

# Единый реестр объектов: карта = список
SEED_SITES = [
    {
        "id": "jk-idle-1",
        "name": "ЖК «Речной»",
        "address": "Москва, САО",
        "cadastral_number": "77:09:0004012:1145",
        "lat": 55.8510,
        "lng": 37.4820,
        "map_status": "idle",
        "scenario": "Экскаватор без самосвалов",
        "comment": (
            "ПРОСТОЙ. По плану этап «Откопка котлована». "
            "На снимке есть экскаватор (маркер этапа), но нет самосвала/грузовика — "
            "звено вывоза грунта неполное. Техника простаивает: копать можно, "
            "убирать грунт некому. Тип отклонения: incomplete_link."
        ),
    },
    {
        "id": "jk-idle-2",
        "name": "ЖК «Береговая»",
        "address": "Москва, СЗАО",
        "cadastral_number": "77:08:0002018:2201",
        "lat": 55.8300,
        "lng": 37.4000,
        "map_status": "idle",
        "scenario": "Бетононасос без миксеров",
        "comment": (
            "ПРОСТОЙ. По плану «Монтаж каркаса, стены и перекрытия». "
            "Виден бетононасос, но нет бетономешалки — бетонное звено неполное. "
            "Насос без подачи смеси простаивает. Тип отклонения: incomplete_link."
        ),
    },
    {
        "id": "jk-warn-1",
        "name": "ЖК «Южный парк»",
        "address": "Москва, ЮАО",
        "cadastral_number": "77:05:0006014:3310",
        "lat": 55.6120,
        "lng": 37.6050,
        "map_status": "warning",
        "scenario": "Котлован по плану — техники нет",
        "comment": (
            "ВОЗМОЖНОЕ НАРУШЕНИЕ. По календарю идёт «Откопка котлована», "
            "на кадре экскаватор не обнаружен. "
            "Риск срыва графика: работы по плану должны идти, факт не подтверждён. "
            "Тип отклонения: missing_required."
        ),
    },
    {
        "id": "jk-warn-2",
        "name": "ЖК «Чертаново»",
        "address": "Москва, ЮЗАО",
        "cadastral_number": "77:06:0003011:4408",
        "lat": 55.6400,
        "lng": 37.5950,
        "map_status": "warning",
        "scenario": "Сваи по плану — сваебоя нет",
        "comment": (
            "ВОЗМОЖНОЕ НАРУШЕНИЕ. Плановый этап — «Устройство фундаментов», "
            "сваебой на снимке отсутствует. Возможное нарушение графика СМР "
            "или неявка подрядной техники. Тип отклонения: missing_required."
        ),
    },
    {
        "id": "jk-ok-1",
        "name": "ЖК «Северный»",
        "address": "Москва, САО",
        "cadastral_number": "77:09:0005016:1552",
        "lat": 55.8350,
        "lng": 37.5250,
        "map_status": "ok",
        "scenario": "Котлован: экскаватор + самосвалы",
        "comment": (
            "В НОРМЕ. План: откопка котлована. На снимке экскаватор "
            "и самосвалы — маркер этапа и полное звено вывоза. "
            "План и факт согласованы, отклонений нет."
        ),
    },
    {
        "id": "jk-ok-2",
        "name": "ЖК «Измайлово»",
        "address": "Москва, ВАО",
        "cadastral_number": "77:03:0007019:2664",
        "lat": 55.7880,
        "lng": 37.7700,
        "map_status": "ok",
        "scenario": "Каркас: миксер и бетононасос на месте",
        "comment": (
            "В НОРМЕ. План: монтаж каркаса, стены и перекрытия. "
            "На снимке бетономешалка и бетононасос — маркер этапа и полное бетонное звено. "
            "План и факт согласованы."
        ),
    },
    {
        "id": "jk-info-1",
        "name": "ЖК «Хамовники»",
        "address": "Москва, ЦАО",
        "cadastral_number": "77:01:0001012:1780",
        "lat": 55.7250,
        "lng": 37.5600,
        "map_status": "info",
        "scenario": "План — котлован, факт — башенный кран",
        "comment": (
            "ОПЕРЕЖЕНИЕ ГРАФИКА. По плану ещё откопка котлована, а на кадре — "
            "башенный кран (монтаж каркаса, стены и перекрытия). "
            "Работы идут раньше графика. "
            "Тип отклонения: unexpected_equipment (смена этапа)."
        ),
    },
    {
        "id": "jk-info-2",
        "name": "ЖК «Лефортово»",
        "address": "Москва, ЮВАО",
        "cadastral_number": "77:04:0008015:2891",
        "lat": 55.7550,
        "lng": 37.7050,
        "map_status": "info",
        "scenario": "План — котлован, факт — бетонное звено каркаса",
        "comment": (
            "ОПЕРЕЖЕНИЕ ГРАФИКА. В календаре ещё «Откопка котлована», на снимке уже "
            "миксер и бетононасос (каркас, стены и перекрытия). "
            "Фиксируем опережение графика, это не простой. "
            "Тип: unexpected_equipment / other_stage."
        ),
    },
    {
        "id": "jk-nodata-1",
        "name": "ЖК «Митино»",
        "address": "Москва, СЗАО",
        "cadastral_number": "77:08:0009017:3120",
        "lat": 55.8450,
        "lng": 37.3600,
        "map_status": "no_data",
        "scenario": "План есть, снимков нет",
        "comment": (
            "НЕТ ДАННЫХ. Календарный план загружен, но с камер "
            "не поступало ни одного кадра за контрольный период. "
            "Сопоставление план/факт невозможно до появления снимков."
        ),
    },
    {
        "id": "jk-nodata-2",
        "name": "ЖК «Некрасовка»",
        "address": "Москва, ЮВАО",
        "cadastral_number": "77:04:0010013:4033",
        "lat": 55.6850,
        "lng": 37.9250,
        "map_status": "no_data",
        "scenario": "Ожидание первой выгрузки",
        "comment": (
            "НЕТ ДАННЫХ. Объект в портфеле, камеры ещё не отдали кадры "
            "(или выгрузка не настроена). Статус «нет данных» — не нарушение, "
            "а отсутствие факта для алгоритма."
        ),
    },
]

SCENARIO_FACTS = {
    "jk-idle-1": {"excavator": 1},
    "jk-idle-2": {"concrete_pump": 1},
    "jk-warn-1": {},
    "jk-warn-2": {},
    "jk-ok-1": {"excavator": 1, "dump_truck": 2},
    "jk-ok-2": {"concrete_mixer": 1, "concrete_pump": 1},
    "jk-info-1": {"tower_crane": 1},
    "jk-info-2": {"concrete_mixer": 1, "concrete_pump": 1},
}


def write_sample_files() -> Path:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = SAMPLES_DIR / "schedule_example.csv"
    csv_path.write_text(EXAMPLE_CSV, encoding="utf-8")
    return csv_path


def _plan_for(site_id: str) -> list:
    if site_id in ("jk-idle-2", "jk-ok-2"):
        return [
            {
                "stage_code": "frame",
                "date_from": "2025-03-01",
                "date_to": "2025-03-31",
                "zone": "Каркас",
            }
        ]
    if site_id == "jk-warn-2":
        return [
            {
                "stage_code": "foundations",
                "date_from": "2025-03-01",
                "date_to": "2025-03-31",
                "zone": "Сваи",
            }
        ]
    return [
        {
            "stage_code": "excavation",
            "date_from": "2025-03-01",
            "date_to": "2025-03-31",
            "zone": "Котлован А",
        }
    ]


LEGACY_STAGE = {
    "earthworks": "excavation",
    "piling": "foundations",
    "monolith": "frame",
    "superstructure": "frame",
}


def _remap_plan(plan: list) -> list:
    remapped = []
    for row in plan or []:
        item = dict(row)
        code = item.get("stage_code")
        if code in LEGACY_STAGE:
            item["stage_code"] = LEGACY_STAGE[code]
        remapped.append(item)
    return remapped


def _font(size: int = 18):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def render_test_photo(
    site_name: str,
    status: str,
    counts: dict,
    comment: str,
    out_path: Path,
) -> tuple[int, int, list]:
    """Fallback: схематичный кадр, если реального фото ещё нет."""
    w, h = 960, 540
    img = Image.new("RGB", (w, h), (45, 52, 58))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, w, h // 2], fill=(110, 145, 175))
    draw.rectangle([0, h // 2, w, h], fill=(92, 78, 55))
    meta = STATUS_META[status]
    draw.text((12, 10), f"{site_name} · {meta['label']}", fill=(230, 235, 240), font=_font(20))
    detections: list = []
    slots = [(80, 300, 280, 460), (340, 290, 540, 450), (600, 310, 820, 470)]
    idx = 0
    for cls, n in counts.items():
        for _ in range(n):
            if idx >= len(slots):
                break
            x1, y1, x2, y2 = slots[idx]
            color = CLASS_COLORS.get(cls, "#888888")
            rgb = tuple(int(color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
            draw.rectangle([x1, y1, x2, y2], outline=rgb, width=4)
            detections.append(
                {
                    "class": cls,
                    "confidence": 0.9,
                    "bbox": [float(x1), float(y1), float(x2), float(y2)],
                }
            )
            idx += 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="JPEG", quality=88)
    return w, h, detections


def _load_or_make_photo(spec: dict) -> tuple[Path, int, int, list, dict]:
    """Реальное фото из Демо/test_photos (+ json разметки), иначе fallback."""
    import json

    site_id = spec["id"]
    jpg = TEST_PHOTOS_DIR / f"{site_id}.jpg"
    meta = TEST_PHOTOS_DIR / f"{site_id}.json"
    if jpg.exists() and meta.exists():
        data = json.loads(meta.read_text(encoding="utf-8"))
        return (
            jpg,
            int(data["width"]),
            int(data["height"]),
            list(data.get("detections") or []),
            dict(data.get("counts") or {}),
        )
    if jpg.exists():
        with Image.open(jpg) as im:
            w, h = im.size
        counts = SCENARIO_FACTS.get(site_id, {})
        # боксы-заглушки по факту сценария (фото реальное)
        dets = []
        for i, (cls, n) in enumerate(counts.items()):
            for j in range(n):
                x1 = 40 + (i * 120) + j * 10
                y1 = 80 + j * 20
                dets.append(
                    {
                        "class": cls,
                        "confidence": 0.85,
                        "bbox": [float(x1), float(y1), float(x1 + 180), float(y1 + 140)],
                    }
                )
        return jpg, w, h, dets, counts

    counts = SCENARIO_FACTS.get(site_id, {})
    w, h, dets = render_test_photo(
        spec["name"],
        spec["map_status"],
        counts,
        spec["comment"],
        jpg,
    )
    return jpg, w, h, dets, counts


def _seed_photo_with_file(spec: dict, plan: list) -> None:
    from backend.domain.rules import analyze_day

    site_id = spec["id"]
    status = spec["map_status"]
    if status == "no_data":
        return

    day = "2025-03-10"
    photo_id = f"seed-{site_id}"
    filename = f"{site_id}.jpg"

    sample_path, w, h, detections, counts = _load_or_make_photo(spec)

    rel = f"{site_id}/{photo_id}.jpg"
    abs_path = store.PHOTOS_DIR / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(sample_path.read_bytes())

    with store._lock:
        data = store.load_store()
        data["photos"][photo_id] = {
            "id": photo_id,
            "site_id": site_id,
            "captured_at": day,
            "filename": filename,
            "path": rel,
            "width": w,
            "height": h,
            "model": "dataset-train_12",
            "detections": detections,
            "created_at": store._now_iso(),
            "virtual": False,
            "is_seed": True,
            "comment": spec["comment"],
        }
        store.save_store(data)

    report = analyze_day(
        day=day,
        counts=counts,
        plan_rows=plan,
        photo_ids=[photo_id],
    )
    logger.info(
        "Seed photo %s → status=%s (expected %s)",
        site_id,
        report.get("project_status"),
        status,
    )


def ensure_seed() -> None:
    write_sample_files()
    TEST_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

    with store._lock:
        data = store.load_store()
        current = data.get("seed_version")
        if current == SEED_VERSION and len(data.get("sites") or {}) >= 10:
            logger.info("Seed: already at version %s", SEED_VERSION)
            return
        # Уже развёрнутый контур: обновляем тексты, не стирая снимки.
        if data.get("sites") and len(data["sites"]) >= 10:
            comments = {spec["id"]: spec["comment"] for spec in SEED_SITES}
            cadastral = {spec["id"]: spec["cadastral_number"] for spec in SEED_SITES}
            for site_id, site in data["sites"].items():
                if site_id in comments:
                    site["comment"] = comments[site_id]
                    site["cadastral_number"] = cadastral[site_id]
                    site["plan"] = _plan_for(site_id)
                    site["scenario"] = next(
                        spec["scenario"] for spec in SEED_SITES if spec["id"] == site_id
                    )
                else:
                    site["plan"] = _remap_plan(site.get("plan") or [])
            for photo in (data.get("photos") or {}).values():
                site_id = photo.get("site_id")
                if photo.get("is_seed") and site_id in comments:
                    photo["comment"] = comments[site_id]
            data["seed_version"] = SEED_VERSION
            store.save_store(data)
            logger.info("Seed v%s: plans and comments refreshed", SEED_VERSION)
            return
        data["sites"] = {}
        data["photos"] = {}
        data["demo_sessions"] = {}
        data["seed_version"] = SEED_VERSION
        store.save_store(data)

    for spec in SEED_SITES:
        plan = _plan_for(spec["id"])
        meta = STATUS_META[spec["map_status"]]
        store.upsert_site(
            {
                "id": spec["id"],
                "name": spec["name"],
                "lat": spec["lat"],
                "lng": spec["lng"],
                "address": spec["address"],
                "cadastral_number": spec["cadastral_number"],
                "plan": plan,
                "is_demo": True,
                "seed_status": spec["map_status"],
                "scenario": spec["scenario"],
                "comment": spec["comment"],
                "status_label": meta["label"],
            }
        )
        _seed_photo_with_file(spec, plan)

    logger.info("Seed v%s: %s ЖК + тестовые фото", SEED_VERSION, len(SEED_SITES))
