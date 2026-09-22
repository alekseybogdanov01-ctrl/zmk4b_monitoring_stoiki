"""Инференс одного кадра: YOLOv8 → детекции строительной техники."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from ultralytics import YOLO

from ml.classes import (
    CLASS_MAPPING,
    CLASS_NAME_ALIASES,
    CONFIDENCE_BY_CLASS,
    DEFAULT_CONFIDENCE,
    YOLO_CONF_FLOOR,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Приоритет весов: train_all (9 классов) → train_mixed → fallback
_WEIGHT_CANDIDATES = [
    PROJECT_ROOT / "ml" / "runs" / "detect" / "train_all_v1" / "weights" / "best.pt",
    PROJECT_ROOT / "ml" / "runs" / "detect" / "train_mixed" / "weights" / "best.pt",
    PROJECT_ROOT / "ml" / "weights" / "best.pt",
]
FALLBACK_WEIGHTS = "yolov8n.pt"

_model: Optional[YOLO] = None
_model_path: Optional[str] = None


def resolve_weights(explicit: str | Path | None = None) -> str:
    """Возвращает путь к весам или имя предобученной модели."""
    if explicit is not None:
        p = Path(explicit)
        if p.exists():
            return str(p.resolve())
        return str(explicit)
    for candidate in _WEIGHT_CANDIDATES:
        if candidate.is_file():
            return str(candidate.resolve())
    return FALLBACK_WEIGHTS


def load_model(weights_path: str | Path | None = None) -> YOLO:
    """Загружает (или отдаёт кэш) модель YOLOv8."""
    global _model, _model_path
    resolved = resolve_weights(weights_path)
    if _model is not None and _model_path == resolved:
        return _model
    model = YOLO(resolved)
    _model = model
    _model_path = resolved
    return model


def _map_class(cls_id: int, raw_name: str | None = None) -> Optional[str]:
    """Сначала по имени модели (устойчиво к смене порядка id), затем по CLASS_MAPPING."""
    known = set(CLASS_MAPPING.values())
    if raw_name is not None:
        key = raw_name.strip().lower().replace(" ", "_").replace("-", "_")
        key = CLASS_NAME_ALIASES.get(key, key)
        if key in known:
            return key
    return CLASS_MAPPING.get(int(cls_id))


def _class_threshold(equipment_class: str) -> float:
    return CONFIDENCE_BY_CLASS.get(equipment_class, DEFAULT_CONFIDENCE)


def _imread(path: Path) -> Optional[np.ndarray]:
    """Читает изображение с поддержкой кириллицы в пути (Windows)."""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _decode_bytes(raw: bytes) -> Optional[np.ndarray]:
    data = np.frombuffer(raw, dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def detect_image(
    image: np.ndarray,
    *,
    model: YOLO | None = None,
    imgsz: int = 960,
    conf_floor: float = YOLO_CONF_FLOOR,
) -> Dict[str, Any]:
    """Детекция на BGR-кадре. Возвращает словарь с detections и meta."""
    if model is None:
        model = load_model()

    h, w = image.shape[:2]
    name_map = {int(i): str(n) for i, n in model.names.items()}

    results = model.predict(
        source=image,
        conf=conf_floor,
        imgsz=imgsz,
        verbose=False,
    )

    detections: List[Dict[str, Any]] = []
    raw_by_class: Dict[str, int] = {}
    kept_by_class: Dict[str, int] = {}

    if not results:
        return _pack(detections, raw_by_class, kept_by_class, w, h, model)

    boxes = results[0].boxes
    if boxes is None or len(boxes) == 0:
        return _pack(detections, raw_by_class, kept_by_class, w, h, model)

    for i in range(len(boxes)):
        cls_id = int(boxes.cls[i].item())
        raw_name = name_map.get(cls_id, str(cls_id))
        mapped = _map_class(cls_id, raw_name)
        if mapped is None:
            continue

        conf = float(boxes.conf[i].item())
        raw_by_class[mapped] = raw_by_class.get(mapped, 0) + 1
        if conf < _class_threshold(mapped):
            continue

        kept_by_class[mapped] = kept_by_class.get(mapped, 0) + 1
        xyxy = boxes.xyxy[i].tolist()
        detections.append(
            {
                "class": mapped,
                "confidence": round(conf, 4),
                "bbox": [
                    float(xyxy[0]),
                    float(xyxy[1]),
                    float(xyxy[2]),
                    float(xyxy[3]),
                ],
            }
        )

    return _pack(detections, raw_by_class, kept_by_class, w, h, model)


def _pack(
    detections: List[Dict[str, Any]],
    raw_by_class: Dict[str, int],
    kept_by_class: Dict[str, int],
    width: int,
    height: int,
    model: YOLO,
) -> Dict[str, Any]:
    return {
        "width": width,
        "height": height,
        "model": _model_path or resolve_weights(),
        "model_classes": dict(model.names),
        "detections": detections,
        "stats_before_filter": raw_by_class,
        "stats_after_filter": kept_by_class,
        "confidence_by_class": dict(CONFIDENCE_BY_CLASS),
    }


def detect_file(path: Path | str, **kwargs: Any) -> Dict[str, Any]:
    """Детекция по пути к файлу."""
    path = Path(path)
    img = _imread(path)
    if img is None:
        raise FileNotFoundError(f"Не удалось прочитать изображение: {path}")
    return detect_image(img, **kwargs)


def detect_bytes(raw: bytes, **kwargs: Any) -> Dict[str, Any]:
    """Детекция по байтам изображения (upload)."""
    img = _decode_bytes(raw)
    if img is None:
        raise ValueError("Не удалось декодировать изображение")
    return detect_image(img, **kwargs)


def classes_catalog() -> List[Dict[str, str]]:
    """Список классов для UI."""
    from ml.classes import CLASS_COLORS, CLASS_LABELS_RU, CLASS_MAPPING

    return [
        {
            "id": cid,
            "code": code,
            "label": CLASS_LABELS_RU.get(code, code),
            "color": CLASS_COLORS.get(code, "#888888"),
        }
        for cid, code in sorted(CLASS_MAPPING.items())
    ]


# CLI для быстрой проверки
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: py -m ml.infer <image.jpg>")
        sys.exit(1)
    out = detect_file(sys.argv[1])
    print(f"model={out['model']}")
    print(f"size={out['width']}x{out['height']}")
    print(f"detections={len(out['detections'])}")
    for d in out["detections"]:
        print(f"  {d['class']}: {d['confidence']:.3f} bbox={d['bbox']}")
