"""Инференс YOLOv8 на видео с трекингом ByteTrack.

Читает видео, прогоняет ultralytics ``model.track``, маппит классы
на ``EquipmentClass`` и сохраняет детекции в JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from tqdm import tqdm
from ultralytics import YOLO

try:
    from backend.config import (
        CONFIDENCE_BY_CLASS,
        EquipmentClass,
        PROJECT_ROOT,
        settings,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from backend.config import (
        CONFIDENCE_BY_CLASS,
        EquipmentClass,
        PROJECT_ROOT,
        settings,
    )


# Маппинг class_id YOLO → код ``EquipmentClass`` (9 классов техники, без manlift).
# Порядок совпадает с ``data/train_all`` / ``scripts/ml/merge_train_all.FINAL_NAMES``.
# Person детектируется отдельно через ``yolov8n.pt`` (COCO) и сюда не входит.
CLASS_MAPPING: Dict[int, str] = {
    0: EquipmentClass.EXCAVATOR.value,
    1: EquipmentClass.BULLDOZER.value,
    2: EquipmentClass.LOADER.value,
    3: EquipmentClass.DUMP_TRUCK.value,
    4: EquipmentClass.CONCRETE_MIXER.value,
    5: EquipmentClass.CONCRETE_PUMP.value,
    6: EquipmentClass.TOWER_CRANE.value,
    7: EquipmentClass.AUTOCRANE.value,
    8: EquipmentClass.PILE_DRIVER.value,
}

DEFAULT_WEIGHTS: Path = (
    PROJECT_ROOT / "ml" / "runs" / "detect" / "train_mixed" / "weights" / "best.pt"
)
FALLBACK_WEIGHTS: str = "yolov8n.pt"
DEFAULT_OUTPUT: Path = PROJECT_ROOT / "data" / "output" / "detections.json"


def load_model(weights_path: str | Path = DEFAULT_WEIGHTS) -> YOLO:
    """Загружает модель YOLOv8 из файла ``.pt``.

    По умолчанию — дообученные веса ``ml/runs/detect/train_mixed/weights/best.pt``.
    Если файла нет — fallback на предобученные ``yolov8n.pt``.

    Args:
        weights_path: путь к файлу весов или имя предобученной модели.

    Returns:
        Загруженный объект ``YOLO``.
    """
    path = Path(weights_path)
    if path.exists():
        resolved = str(path.resolve())
        print(f"Model path: {resolved}")
        model = YOLO(resolved)
        print(f"Model classes: {model.names}")
        print(f"Model nc: {len(model.names)}")
        return model
    # Предобученные имена (yolov8n.pt / yolov8s.pt) ultralytics подтянет сам.
    pretrained = {FALLBACK_WEIGHTS, "yolov8s.pt", "yolov8n.pt", "yolov8m.pt"}
    if str(weights_path) in pretrained:
        print(f"Model path: {weights_path}")
        model = YOLO(str(weights_path))
        print(f"Model classes: {model.names}")
        print(f"Model nc: {len(model.names)}")
        return model
    print(
        f"Файл весов не найден: {weights_path}. "
        f"Загружаю предобученные {FALLBACK_WEIGHTS}.",
        file=sys.stderr,
    )
    print(f"Model path: {FALLBACK_WEIGHTS}")
    model = YOLO(FALLBACK_WEIGHTS)
    print(f"Model classes: {model.names}")
    print(f"Model nc: {len(model.names)}")
    return model


def _map_class(cls_id: int, raw_name: str | None = None) -> Optional[str]:
    """Преобразует class_id YOLO в код ``EquipmentClass`` или ``None``.

    Сначала смотрит ``CLASS_MAPPING`` по id; если id неизвестен — пробует
    имя из ``model.names`` (на случай несовпадения индексов).
    """
    mapped = CLASS_MAPPING.get(int(cls_id))
    if mapped is not None:
        return mapped
    if raw_name is None:
        return None
    key = raw_name.strip().lower().replace(" ", "_").replace("-", "_")
    by_name = {v: v for v in CLASS_MAPPING.values()}
    return by_name.get(key)


def _read_video_meta(video_path: Path) -> tuple[float, int]:
    """Открывает видео и возвращает ``(fps, frame_count)``.

    Raises:
        FileNotFoundError: файл не существует.
        RuntimeError: OpenCV не смог открыть видео.
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Видео не найдено: {video_path}")

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        capture.release()
        raise RuntimeError(
            f"Не удалось открыть видео: {video_path}. "
            "Проверьте формат файла и кодек."
        )

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    capture.release()

    if fps <= 0.0:
        fps = 25.0
    return fps, frame_count


def _frame_timestamp(video_start: datetime, frame_id: int, fps: float) -> str:
    """Считает ISO-метку времени кадра от начала видео (по fps)."""
    offset_sec = frame_id / fps if fps > 0 else 0.0
    moment = video_start + timedelta(seconds=offset_sec)
    return moment.isoformat(timespec="seconds")


def _default_timestamps_path(video_path: Path) -> Path:
    """Путь к ``{stem}_timestamps.json`` рядом с видео."""
    return video_path.with_name(f"{video_path.stem}_timestamps.json")


def load_timestamps(
    timestamps_path: Path | None = None,
    *,
    video_path: Path | None = None,
) -> Optional[Dict[str, Any]]:
    """Загружает JSON с календарными метками кадров.

    Формат::
        {"start_date": "ISO", "interval_hours": 550, "frames_total": 25}

    Returns:
        Словарь метаданных или ``None``, если файла нет.
    """
    path: Optional[Path] = None
    if timestamps_path is not None:
        path = Path(timestamps_path)
    elif video_path is not None:
        path = _default_timestamps_path(Path(video_path))

    if path is None or not path.exists():
        return None

    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"Некорректный timestamps JSON: {path}")
    if "start_date" not in raw or "interval_hours" not in raw:
        raise ValueError(
            f"В timestamps нужны start_date и interval_hours: {path}"
        )
    return raw


def resolve_frame_timestamp(
    frame_index: int,
    *,
    fps: float,
    video_start: datetime,
    timestamps_meta: Optional[Dict[str, Any]] = None,
) -> str:
    """Возвращает ISO-timestamp кадра.

    ``frame_index`` — с нуля. Если есть timestamps_meta —
    ``start_date + frame_index * interval_hours``, иначе fps-смещение.
    """
    if timestamps_meta is not None:
        start_raw = str(timestamps_meta["start_date"])
        start = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
        if start.tzinfo is not None:
            start = start.replace(tzinfo=None)
        interval_h = float(timestamps_meta["interval_hours"])
        moment = start + timedelta(hours=interval_h * frame_index)
        return moment.isoformat(timespec="seconds")
    return _frame_timestamp(video_start, frame_index, fps)


YOLO_CONF_FLOOR: float = 0.05
"""Минимальный conf для ultralytics: все кандидаты выше пола, фильтр — по классу."""


def _class_confidence_threshold(equipment_class: str) -> float:
    """Возвращает порог уверенности для класса из ``CONFIDENCE_BY_CLASS``."""
    return CONFIDENCE_BY_CLASS.get(equipment_class, settings.confidence_threshold)


def process_video(
    video_path: Path,
    model: YOLO,
    conf_threshold: float | None = None,
    output_json: Path | None = None,
    imgsz: int = 960,
    timestamps_path: Path | str | None = None,
) -> List[Dict[str, Any]]:
    """Прогоняет видео через YOLO с трекингом ByteTrack и сохраняет JSON.

    YOLO вызывается с низким ``conf`` (``YOLO_CONF_FLOOR`` = 0.05),
    затем каждая детекция проверяется по ``CONFIDENCE_BY_CLASS``.

    Если рядом с видео есть ``{stem}_timestamps.json`` (или передан
    ``timestamps_path``) — метки кадров берутся из него.

    Args:
        video_path: путь к входному видео.
        model: загруженная модель YOLOv8.
        conf_threshold: устаревший общий порог; если задан, используется как
            пол для YOLO (не выше ``YOLO_CONF_FLOOR`` по смыслу минимума).
            Итоговая фильтрация всегда по ``CONFIDENCE_BY_CLASS``.
        output_json: путь к выходному JSON; по умолчанию ``DEFAULT_OUTPUT``.
        imgsz: размер входа модели (больше — лучше мелкие объекты).
        timestamps_path: явный путь к JSON меток; иначе ищем рядом с видео.

    Returns:
        Список словарей детекций (тот же, что в поле ``detections`` JSON).

    Raises:
        FileNotFoundError: видео отсутствует.
        RuntimeError: видео не открывается.
    """
    if output_json is None:
        output_json = DEFAULT_OUTPUT

    video_path = Path(video_path)
    output_json = Path(output_json)
    fps, frame_count = _read_video_meta(video_path)
    video_start = datetime.now().replace(microsecond=0)

    ts_path = Path(timestamps_path) if timestamps_path else None
    timestamps_meta = load_timestamps(ts_path, video_path=video_path)

    name_map: Dict[int, str] = {
        int(idx): str(name) for idx, name in model.names.items()
    }

    # Все кандидаты выше минимального пола; отсев — после инференса по классу.
    yolo_conf = YOLO_CONF_FLOOR
    if conf_threshold is not None:
        yolo_conf = min(float(conf_threshold), YOLO_CONF_FLOOR)

    detections: List[Dict[str, Any]] = []
    frames_processed = 0
    raw_by_class: Dict[str, int] = {}
    kept_by_class: Dict[str, int] = {}

    results_iter = model.track(
        source=str(video_path),
        conf=yolo_conf,
        imgsz=imgsz,
        tracker="bytetrack.yaml",
        stream=True,
        verbose=False,
        persist=True,
    )

    progress = tqdm(
        results_iter,
        total=frame_count if frame_count > 0 else None,
        desc="Инференс",
        unit="кадр",
    )

    for result in progress:
        frames_processed += 1
        # ultralytics нумерует кадры с 0; в JSON — с 1.
        frame_id = frames_processed
        timestamp = resolve_frame_timestamp(
            frame_id - 1,
            fps=fps,
            video_start=video_start,
            timestamps_meta=timestamps_meta,
        )

        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            continue

        has_id = boxes.id is not None
        for i in range(len(boxes)):
            cls_id = int(boxes.cls[i].item())
            raw_name = name_map.get(cls_id, str(cls_id))
            mapped = _map_class(cls_id, raw_name)
            if mapped is None:
                continue

            conf = float(boxes.conf[i].item())
            raw_by_class[mapped] = raw_by_class.get(mapped, 0) + 1

            # Пост-фильтр: порог из CONFIDENCE_BY_CLASS для данного класса.
            if conf < _class_confidence_threshold(mapped):
                continue

            kept_by_class[mapped] = kept_by_class.get(mapped, 0) + 1
            xyxy = boxes.xyxy[i].tolist()
            bbox = [float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])]
            track_id: Optional[int] = None
            if has_id:
                track_id = int(boxes.id[i].item())

            detections.append(
                {
                    "frame_id": frame_id,
                    "timestamp": timestamp,
                    "class": mapped,
                    "confidence": round(conf, 4),
                    "bbox": bbox,
                    "track_id": track_id,
                }
            )

    payload: Dict[str, Any] = {
        "video": str(video_path),
        "fps": fps,
        "frames_processed": frames_processed,
        "detections": detections,
        "stats_before_filter": raw_by_class,
        "stats_after_filter": kept_by_class,
        "yolo_conf": yolo_conf,
        "confidence_by_class": dict(CONFIDENCE_BY_CLASS),
        "timestamps_file": (
            str(ts_path or _default_timestamps_path(video_path))
            if timestamps_meta is not None
            else None
        ),
        "timestamps_meta": timestamps_meta,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    with output_json.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    return detections


def _build_frame_timestamps(
    n_frames: int,
    timestamps_meta: Optional[Dict[str, Any]] = None,
    *,
    analysis_date: Optional[datetime] = None,
    interval_hours: float = 0.5,
) -> List[str]:
    """Строит ISO-метки для N кадров.

    Приоритет:
    1. ``timestamps_meta["timestamps"]`` — явный список ISO.
    2. ``start_date`` + ``interval_hours`` из meta.
    3. Равномерно: ``analysis_date - (n-1)*interval … analysis_date``.
    """
    if n_frames <= 0:
        return []

    if timestamps_meta:
        explicit = timestamps_meta.get("timestamps")
        if isinstance(explicit, list) and explicit:
            out: List[str] = []
            for i in range(n_frames):
                if i < len(explicit):
                    raw = explicit[i]
                    if isinstance(raw, datetime):
                        out.append(raw.replace(microsecond=0).isoformat(timespec="seconds"))
                    else:
                        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                        if ts.tzinfo is not None:
                            ts = ts.replace(tzinfo=None)
                        out.append(ts.replace(microsecond=0).isoformat(timespec="seconds"))
                else:
                    # Добиваем интервалом от последней известной метки.
                    prev = datetime.fromisoformat(out[-1])
                    step = float(timestamps_meta.get("interval_hours", interval_hours))
                    out.append((prev + timedelta(hours=step)).isoformat(timespec="seconds"))
            return out

        if "start_date" in timestamps_meta:
            return [
                resolve_frame_timestamp(
                    i,
                    fps=1.0,
                    video_start=datetime.now(),
                    timestamps_meta=timestamps_meta,
                )
                for i in range(n_frames)
            ]

    center = (analysis_date or datetime.now()).replace(microsecond=0)
    if center.tzinfo is not None:
        center = center.replace(tzinfo=None)
    start = center - timedelta(hours=interval_hours * max(n_frames - 1, 0))
    return [
        (start + timedelta(hours=interval_hours * i)).isoformat(timespec="seconds")
        for i in range(n_frames)
    ]


def _imread_unicode(path: Path) -> Optional[np.ndarray]:
    """Читает изображение даже если путь содержит кириллицу/пробелы/скобки.

    ``cv2.imread`` и ultralytics ``predict(source=path)`` на Windows часто
    возвращают ``None`` / ``does not exist`` для таких путей.
    """
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def process_frames(
    frame_paths: List[Path],
    model: YOLO,
    conf_threshold: float | None = None,
    output_json: Path | None = None,
    imgsz: int = 960,
    timestamps_meta: Optional[Dict[str, Any]] = None,
    analysis_date: Optional[datetime] = None,
    interval_hours: float = 0.5,
) -> List[Dict[str, Any]]:
    """Прогоняет набор кадров (изображений) через YOLO predict.

    Без ByteTrack: каждый файл — отдельный кадр с ``frame_id`` 1..N.
    Метки времени — из ``timestamps_meta`` или равномерно вокруг ``analysis_date``.

    Args:
        frame_paths: пути к изображениям (порядок = порядок кадров).
        model: загруженная модель YOLOv8.
        conf_threshold: опциональный пол для YOLO (см. ``process_video``).
        output_json: путь к выходному JSON.
        imgsz: размер входа модели.
        timestamps_meta: dict с ``timestamps`` / ``start_date``+``interval_hours``.
        analysis_date: опорная дата при отсутствии meta.
        interval_hours: шаг между кадрами (по умолчанию 0.5 ч = 30 мин).

    Returns:
        Список словарей детекций (как у ``process_video``).
    """
    if output_json is None:
        output_json = DEFAULT_OUTPUT

    paths = [Path(p) for p in frame_paths]
    missing = [str(p) for p in paths if not p.exists() or p.stat().st_size <= 0]
    if missing:
        raise FileNotFoundError(f"Кадры не найдены или пустые: {', '.join(missing[:5])}")

    stamps = _build_frame_timestamps(
        len(paths),
        timestamps_meta,
        analysis_date=analysis_date,
        interval_hours=interval_hours,
    )

    name_map: Dict[int, str] = {
        int(idx): str(name) for idx, name in model.names.items()
    }
    yolo_conf = YOLO_CONF_FLOOR
    if conf_threshold is not None:
        yolo_conf = min(float(conf_threshold), YOLO_CONF_FLOOR)

    detections: List[Dict[str, Any]] = []
    raw_by_class: Dict[str, int] = {}
    kept_by_class: Dict[str, int] = {}

    for index, path in enumerate(tqdm(paths, desc="Инференс кадров", unit="кадр")):
        frame_id = index + 1
        timestamp = stamps[index]
        # Windows + кириллица/скобки в пути: cv2/ultralytics часто не открывают файл.
        img = _imread_unicode(path)
        if img is None:
            raise FileNotFoundError(
                f"Не удалось прочитать кадр (путь/кодировка): {path}"
            )
        results = model.predict(
            source=img,
            conf=yolo_conf,
            imgsz=imgsz,
            verbose=False,
        )
        if not results:
            continue
        result = results[0]
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            continue

        for i in range(len(boxes)):
            cls_id = int(boxes.cls[i].item())
            raw_name = name_map.get(cls_id, str(cls_id))
            mapped = _map_class(cls_id, raw_name)
            if mapped is None:
                continue

            conf = float(boxes.conf[i].item())
            raw_by_class[mapped] = raw_by_class.get(mapped, 0) + 1
            if conf < _class_confidence_threshold(mapped):
                continue

            kept_by_class[mapped] = kept_by_class.get(mapped, 0) + 1
            xyxy = boxes.xyxy[i].tolist()
            bbox = [float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])]
            detections.append(
                {
                    "frame_id": frame_id,
                    "timestamp": timestamp,
                    "class": mapped,
                    "confidence": round(conf, 4),
                    "bbox": bbox,
                    "track_id": None,
                }
            )

    payload: Dict[str, Any] = {
        "frames": [str(p) for p in paths],
        "frames_processed": len(paths),
        "detections": detections,
        "stats_before_filter": raw_by_class,
        "stats_after_filter": kept_by_class,
        "yolo_conf": yolo_conf,
        "confidence_by_class": dict(CONFIDENCE_BY_CLASS),
        "timestamps_meta": timestamps_meta,
        "frame_timestamps": stamps,
    }
    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with output_json.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    return detections


def main() -> None:
    """CLI: инференс YOLO на видео и сохранение детекций в JSON."""
    parser = argparse.ArgumentParser(
        description="Инференс YOLOv8 + ByteTrack: видео → JSON детекций."
    )
    parser.add_argument(
        "--video",
        type=Path,
        required=True,
        help="Путь к входному видеофайлу.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Путь к JSON (по умолчанию {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--weights",
        type=str,
        default=str(DEFAULT_WEIGHTS),
        help=(
            "Путь к .pt модели "
            f"(по умолчанию {DEFAULT_WEIGHTS}, fallback {FALLBACK_WEIGHTS})."
        ),
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=settings.confidence_threshold,
        help="Порог уверенности YOLO (из settings).",
    )
    parser.add_argument(
        "--timestamps",
        type=Path,
        default=None,
        help="Путь к JSON меток кадров ({stem}_timestamps.json рядом с видео).",
    )
    args = parser.parse_args()

    try:
        model = load_model(args.weights)
        detections = process_video(
            video_path=args.video,
            model=model,
            conf_threshold=args.conf,
            output_json=args.output,
            timestamps_path=args.timestamps,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        sys.exit(1)

    # Сводка: число детекций и средняя уверенность по классу.
    counts: Dict[str, int] = {}
    conf_sums: Dict[str, float] = {}
    for det in detections:
        cls = str(det["class"])
        counts[cls] = counts.get(cls, 0) + 1
        conf_sums[cls] = conf_sums.get(cls, 0.0) + float(det["confidence"])

    print(f"Готово: детекций {len(detections)}, JSON → {args.output}")
    if counts:
        print("По классам:")
        for cls in sorted(counts.keys()):
            avg_conf = conf_sums[cls] / counts[cls]
            print(f"  {cls}: n={counts[cls]}, mean_conf={avg_conf:.4f}")
    else:
        print("По классам: детекций нет.")


if __name__ == "__main__":
    main()
