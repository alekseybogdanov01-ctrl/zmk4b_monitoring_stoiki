"""Дообучение YOLOv8n на объединённом датасете ``data/merged``.

Запуск из корня репозитория::

    py ml/train.py
    py ml/train.py --epochs 30   # рекомендуется на CPU
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Optional

from ultralytics import YOLO

try:
    from backend.config import PROJECT_ROOT
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from backend.config import PROJECT_ROOT

DEFAULT_WEIGHTS = "yolov8n.pt"
DEFAULT_DATA = PROJECT_ROOT / "data" / "merged" / "data.yaml"
DEFAULT_PROJECT = PROJECT_ROOT / "ml" / "runs" / "detect"
DEFAULT_RUN_NAME = "train_mixed"
DEFAULT_EPOCHS = 100
DEFAULT_BATCH = 16
DEFAULT_IMGSZ = 640
DEFAULT_PATIENCE = 20


def detect_device() -> str:
    """Возвращает ``cuda`` при наличии GPU, иначе ``cpu``."""
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Дообучение YOLOv8n на data/merged (исторический пайплайн; актуальный train — 9 классов через train_all)."
    )
    parser.add_argument(
        "--weights",
        default=DEFAULT_WEIGHTS,
        help=f"Стартовые веса (по умолчанию {DEFAULT_WEIGHTS})",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=DEFAULT_DATA,
        help="Путь к data.yaml объединённого датасета",
    )
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    parser.add_argument("--imgsz", type=int, default=DEFAULT_IMGSZ)
    parser.add_argument("--patience", type=int, default=DEFAULT_PATIENCE)
    parser.add_argument(
        "--device",
        default=None,
        help="cuda / cpu / 0; по умолчанию — автоопределение",
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=DEFAULT_PROJECT,
        help="Каталог ultralytics project",
    )
    parser.add_argument("--name", default=DEFAULT_RUN_NAME, help="Имя прогона")
    return parser.parse_args()


def _metric_rows(results: Any) -> list[dict[str, Any]]:
    """Извлекает per-class precision/recall/mAP из результатов валидации."""
    names: dict[int, str] = getattr(results, "names", None) or {}
    if isinstance(names, list):
        names = {i: n for i, n in enumerate(names)}

    rows: list[dict[str, Any]] = []
    box = getattr(results, "box", None)
    if box is None:
        return rows

    # maps: class_id -> metric
    def _as_map(attr: str) -> dict[int, float]:
        raw = getattr(box, attr, None)
        if raw is None:
            return {}
        try:
            import numpy as np

            arr = np.asarray(raw).reshape(-1)
            # ap_class_index aligns class metrics
            idxs = getattr(box, "ap_class_index", None)
            if idxs is not None:
                idxs = np.asarray(idxs).reshape(-1).astype(int)
                return {int(i): float(v) for i, v in zip(idxs, arr)}
            return {i: float(v) for i, v in enumerate(arr)}
        except Exception:
            return {}

    p_map = _as_map("p")
    r_map = _as_map("r")
    ap50_map = _as_map("ap50")
    # ap — обычно mAP50-95 per class
    ap_map = _as_map("ap")

    class_ids = sorted(set(p_map) | set(r_map) | set(ap50_map) | set(ap_map) | set(names))
    for cid in class_ids:
        rows.append(
            {
                "id": cid,
                "name": names.get(cid, str(cid)),
                "precision": p_map.get(cid),
                "recall": r_map.get(cid),
                "mAP50": ap50_map.get(cid),
                "mAP50-95": ap_map.get(cid),
            }
        )
    return rows


def _fmt(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"


def print_metrics(results: Any) -> None:
    """Печатает overall и per-class метрики."""
    box = getattr(results, "box", None)
    print("\n=== Validation metrics ===")
    if box is not None:
        print(
            f"overall  precision={_fmt(getattr(box, 'mp', None))}  "
            f"recall={_fmt(getattr(box, 'mr', None))}  "
            f"mAP50={_fmt(getattr(box, 'map50', None))}  "
            f"mAP50-95={_fmt(getattr(box, 'map', None))}"
        )

    rows = _metric_rows(results)
    if not rows:
        print("(per-class metrics unavailable)")
        return

    print("\nper-class:")
    print(f"{'id':>3}  {'class':<16}  {'P':>8}  {'R':>8}  {'mAP50':>8}  {'mAP50-95':>8}")
    for row in rows:
        print(
            f"{row['id']:>3}  {row['name']:<16}  "
            f"{_fmt(row['precision']):>8}  {_fmt(row['recall']):>8}  "
            f"{_fmt(row['mAP50']):>8}  {_fmt(row['mAP50-95']):>8}"
        )


def train(
    weights: str = DEFAULT_WEIGHTS,
    data: Path = DEFAULT_DATA,
    epochs: int = DEFAULT_EPOCHS,
    batch: int = DEFAULT_BATCH,
    imgsz: int = DEFAULT_IMGSZ,
    patience: int = DEFAULT_PATIENCE,
    device: Optional[str] = None,
    project: Path = DEFAULT_PROJECT,
    name: str = DEFAULT_RUN_NAME,
) -> Path:
    """Запускает обучение и возвращает путь к ``best.pt``."""
    data = Path(data)
    if not data.is_file():
        raise FileNotFoundError(f"Не найден data.yaml: {data}")

    resolved_device = device or detect_device()
    if resolved_device == "cpu" and epochs > 30:
        print(
            "WARNING: обучение на CPU. 100 эпох могут занять много часов.\n"
            "         Рекомендуется: py ml/train.py --epochs 30",
            file=sys.stderr,
        )

    project.mkdir(parents=True, exist_ok=True)
    model = YOLO(weights)

    # Аугментации: mosaic, flip (fliplr), scale.
    results = model.train(
        data=str(data.resolve()),
        epochs=epochs,
        batch=batch,
        imgsz=imgsz,
        patience=patience,
        device=resolved_device,
        project=str(project),
        name=name,
        exist_ok=True,
        mosaic=1.0,
        fliplr=0.5,
        scale=0.5,
        plots=True,
    )

    best_pt = Path(project) / name / "weights" / "best.pt"
    if not best_pt.is_file():
        # fallback: путь из trainer
        save_dir = Path(getattr(getattr(model, "trainer", None), "save_dir", best_pt.parent.parent))
        candidate = save_dir / "weights" / "best.pt"
        if candidate.is_file():
            best_pt = candidate

    print(f"\nbest weights: {best_pt}")
    if best_pt.is_file():
        print(f"exists: yes ({best_pt.stat().st_size} bytes)")
    else:
        print("exists: NO — проверьте каталог прогона", file=sys.stderr)

    # Финальная валидация на best для per-class метрик.
    if best_pt.is_file():
        val_model = YOLO(str(best_pt))
        val_results = val_model.val(
            data=str(data.resolve()),
            imgsz=imgsz,
            batch=batch,
            device=resolved_device,
            split="val",
        )
        print_metrics(val_results)
    elif results is not None:
        print_metrics(results)

    return best_pt


def main() -> None:
    args = parse_args()
    # data.yaml содержит path: data/merged — нужен cwd = корень репозитория.
    import os

    os.chdir(PROJECT_ROOT)
    train(
        weights=args.weights,
        data=args.data,
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        patience=args.patience,
        device=args.device,
        project=args.project,
        name=args.name,
    )


if __name__ == "__main__":
    main()
