"""Обучение YOLOv8m на 12 классах ``data/train_12``.

Запуск из корня репозитория::

    py ml/train_12.py
    py ml/train_12.py --epochs 50 --device 0 --batch 8
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Optional

from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_WEIGHTS = "yolov8m.pt"
# Дообучение от текущих 9-классовых весов, если есть
FINETUNE_CANDIDATES = [
    PROJECT_ROOT / "ml" / "runs" / "detect" / "train_mixed" / "weights" / "best.pt",
    PROJECT_ROOT / "ml" / "weights" / "best.pt",
]
DEFAULT_DATA = PROJECT_ROOT / "data" / "train_12" / "data.yaml"
DEFAULT_PROJECT = PROJECT_ROOT / "ml" / "runs" / "detect"
DEFAULT_RUN_NAME = "train_12_v1"
DEFAULT_EPOCHS = 100
DEFAULT_BATCH = 16
DEFAULT_IMGSZ = 640
DEFAULT_PATIENCE = 25
DEFAULT_LR0 = 0.001
DEFAULT_WARMUP = 3.0
DEFAULT_SAVE_PERIOD = 10


def detect_device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


def default_weights() -> str:
    for p in FINETUNE_CANDIDATES:
        if p.is_file():
            return str(p.resolve())
    return DEFAULT_WEIGHTS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Обучение YOLOv8m на data/train_12 (12 классов, +roller/manipulator/truck, усиление tower_crane)."
    )
    parser.add_argument("--weights", default=None, help="Стартовые веса (по умолчанию best.pt 9cls или yolov8m)")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    parser.add_argument("--imgsz", type=int, default=DEFAULT_IMGSZ)
    parser.add_argument("--patience", type=int, default=DEFAULT_PATIENCE)
    parser.add_argument("--lr0", type=float, default=DEFAULT_LR0)
    parser.add_argument("--warmup-epochs", type=float, default=DEFAULT_WARMUP)
    parser.add_argument("--save-period", type=int, default=DEFAULT_SAVE_PERIOD)
    parser.add_argument("--device", default=None)
    parser.add_argument("--project", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument("--name", default=DEFAULT_RUN_NAME)
    parser.add_argument("--outputs-dir", type=Path, default=None)
    return parser.parse_args()


def _fmt(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"


def print_metrics(results: Any) -> None:
    box = getattr(results, "box", None)
    print("\n=== Validation metrics ===")
    if box is not None:
        print(
            f"overall  precision={_fmt(getattr(box, 'mp', None))}  "
            f"recall={_fmt(getattr(box, 'mr', None))}  "
            f"mAP50={_fmt(getattr(box, 'map50', None))}  "
            f"mAP50-95={_fmt(getattr(box, 'map', None))}"
        )
    names = getattr(results, "names", None) or {}
    if isinstance(names, list):
        names = {i: n for i, n in enumerate(names)}
    if box is None:
        return

    def _as_map(attr: str) -> dict[int, float]:
        raw = getattr(box, attr, None)
        if raw is None:
            return {}
        try:
            import numpy as np

            arr = np.asarray(raw).reshape(-1)
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
    ap_map = _as_map("ap")
    class_ids = sorted(set(p_map) | set(r_map) | set(ap50_map) | set(ap_map) | set(names))
    print("\nper-class:")
    print(f"{'id':>3}  {'class':<18}  {'P':>8}  {'R':>8}  {'mAP50':>8}  {'mAP50-95':>8}")
    for cid in class_ids:
        print(
            f"{cid:>3}  {str(names.get(cid, cid)):<18}  "
            f"{_fmt(p_map.get(cid)):>8}  {_fmt(r_map.get(cid)):>8}  "
            f"{_fmt(ap50_map.get(cid)):>8}  {_fmt(ap_map.get(cid)):>8}"
        )


def export_metrics_csv(results_csv: Path, out_csv: Path) -> None:
    if not results_csv.is_file():
        return
    with results_csv.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    def pick(*candidates: str) -> Optional[str]:
        for c in candidates:
            if c in fieldnames:
                return c
            for fn in fieldnames:
                if fn.strip() == c or fn.strip().endswith(c):
                    return fn
        return None

    epoch_col = pick("epoch")
    loss_cols = [pick("train/box_loss"), pick("train/cls_loss"), pick("train/dfl_loss")]
    map50_col = pick("metrics/mAP50(B)", "metrics/mAP50")
    map_col = pick("metrics/mAP50-95(B)", "metrics/mAP50-95")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["epoch", "loss", "mAP50", "mAP50-95"])
        writer.writeheader()
        for row in rows:
            loss_vals = []
            for col in loss_cols:
                if col and row.get(col) not in (None, ""):
                    try:
                        loss_vals.append(float(row[col]))
                    except ValueError:
                        pass
            loss = sum(loss_vals) if loss_vals else ""
            writer.writerow(
                {
                    "epoch": row.get(epoch_col, "") if epoch_col else "",
                    "loss": f"{loss:.6f}" if isinstance(loss, float) else "",
                    "mAP50": row.get(map50_col, "") if map50_col else "",
                    "mAP50-95": row.get(map_col, "") if map_col else "",
                }
            )


def train(
    weights: Optional[str] = None,
    data: Path = DEFAULT_DATA,
    epochs: int = DEFAULT_EPOCHS,
    batch: int = DEFAULT_BATCH,
    imgsz: int = DEFAULT_IMGSZ,
    patience: int = DEFAULT_PATIENCE,
    lr0: float = DEFAULT_LR0,
    warmup_epochs: float = DEFAULT_WARMUP,
    save_period: int = DEFAULT_SAVE_PERIOD,
    device: Optional[str] = None,
    project: Path = DEFAULT_PROJECT,
    name: str = DEFAULT_RUN_NAME,
    outputs_dir: Optional[Path] = None,
) -> Path:
    data = Path(data)
    if not data.is_file():
        raise FileNotFoundError(
            f"Не найден {data}. Сначала: py scripts/merge_train_12.py"
        )

    resolved_weights = weights or default_weights()
    resolved_device = device or detect_device()
    print(f"weights={resolved_weights}")
    print(f"data={data}")
    print(f"device={resolved_device}")

    if resolved_device == "cpu" and epochs > 30:
        print(
            "WARNING: 12-классное обучение на CPU будет очень долгим.\n"
            "         GPU / DataSphere или: py ml/train_12.py --epochs 30",
            file=sys.stderr,
            flush=True,
        )

    project = Path(project)
    project.mkdir(parents=True, exist_ok=True)
    model = YOLO(resolved_weights)

    model.train(
        data=str(data.resolve()),
        epochs=epochs,
        batch=batch,
        imgsz=imgsz,
        patience=patience,
        device=resolved_device,
        project=str(project),
        name=name,
        exist_ok=True,
        cos_lr=True,
        warmup_epochs=warmup_epochs,
        optimizer="AdamW",
        lr0=lr0,
        save=True,
        save_period=save_period,
        plots=True,
        mosaic=1.0,
        fliplr=0.5,
        scale=0.5,
    )

    run_dir = Path(project) / name
    best_pt = run_dir / "weights" / "best.pt"
    last_pt = run_dir / "weights" / "last.pt"
    if not best_pt.is_file():
        save_dir = Path(getattr(getattr(model, "trainer", None), "save_dir", run_dir))
        candidate = save_dir / "weights" / "best.pt"
        if candidate.is_file():
            best_pt = candidate
            last_pt = save_dir / "weights" / "last.pt"
            run_dir = save_dir

    export_metrics_csv(run_dir / "results.csv", run_dir / "metrics_summary.csv")
    print(f"\nbest weights: {best_pt}", flush=True)

    if outputs_dir is not None:
        outputs_dir = Path(outputs_dir)
        outputs_dir.mkdir(parents=True, exist_ok=True)
        for src, dst_name in ((best_pt, "best.pt"), (last_pt, "last.pt")):
            if src.is_file():
                shutil.copy2(src, outputs_dir / dst_name)
                print(f"copied -> {outputs_dir / dst_name}", flush=True)

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

    return best_pt


def main() -> None:
    args = parse_args()
    os.chdir(PROJECT_ROOT)
    train(
        weights=args.weights,
        data=args.data,
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        patience=args.patience,
        lr0=args.lr0,
        warmup_epochs=args.warmup_epochs,
        save_period=args.save_period,
        device=args.device,
        project=args.project,
        name=args.name,
        outputs_dir=args.outputs_dir,
    )


if __name__ == "__main__":
    main()
