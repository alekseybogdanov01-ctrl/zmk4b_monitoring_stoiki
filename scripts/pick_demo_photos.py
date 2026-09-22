"""Подбор реальных фото из data/train_12 под сценарии ЖК → Демо/test_photos."""

from __future__ import annotations

import random
import shutil
from collections import defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "data" / "train_12"
OUT = ROOT / "Демо" / "test_photos"
NAMES = {
    0: "excavator",
    1: "bulldozer",
    2: "loader",
    3: "dump_truck",
    4: "concrete_mixer",
    5: "concrete_pump",
    6: "tower_crane",
    7: "autocrane",
    8: "pile_driver",
    9: "roller",
    10: "crane_manipulator",
    11: "truck",
}

# site_id → условие по множеству классов на кадре
CRITERIA = {
    "jk-idle-1": lambda c: "excavator" in c and "dump_truck" not in c and "truck" not in c,
    "jk-idle-2": lambda c: "concrete_pump" in c and "concrete_mixer" not in c,
    # жёлтый: нет маркерной техники планового этапа и нет «чужого» сильного маркера
    "jk-warn-1": lambda c: not (
        c & {"excavator", "bulldozer", "tower_crane", "pile_driver", "concrete_mixer", "concrete_pump"}
    ),
    "jk-warn-2": lambda c: not (
        c
        & {
            "pile_driver",
            "excavator",
            "bulldozer",
            "tower_crane",
            "concrete_mixer",
            "concrete_pump",
        }
    ),
    "jk-ok-1": lambda c: "excavator" in c and ("dump_truck" in c or "truck" in c),
    # монолит с полным звеном ИЛИ надземка с краном
    "jk-ok-2": lambda c: (
        ("concrete_mixer" in c and "concrete_pump" in c)
        or ("tower_crane" in c and "excavator" not in c and "concrete_mixer" not in c)
    ),
    "jk-info-1": lambda c: "tower_crane" in c and "excavator" not in c and "bulldozer" not in c,
    "jk-info-2": lambda c: (
        ("concrete_mixer" in c or "concrete_pump" in c)
        and "excavator" not in c
        and "bulldozer" not in c
    ),
}


def _iter_labeled_images():
    for split in ("train", "valid", "test"):
        img_dir = DATASET / split / "images"
        lbl_dir = DATASET / split / "labels"
        if not img_dir.is_dir():
            continue
        for img in img_dir.glob("*.jpg"):
            lbl = lbl_dir / (img.stem + ".txt")
            yield img, lbl if lbl.exists() else None


def _classes_and_dets(img_path: Path, lbl_path: Path | None):
    with Image.open(img_path) as im:
        w, h = im.size
    counts: dict[str, int] = defaultdict(int)
    dets = []
    if lbl_path and lbl_path.exists():
        for line in lbl_path.read_text(encoding="utf-8").splitlines():
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            cid = int(float(parts[0]))
            code = NAMES.get(cid)
            if not code:
                continue
            xc, yc, bw, bh = map(float, parts[1:5])
            x1 = (xc - bw / 2) * w
            y1 = (yc - bh / 2) * h
            x2 = (xc + bw / 2) * w
            y2 = (yc + bh / 2) * h
            counts[code] += 1
            dets.append(
                {
                    "class": code,
                    "confidence": 0.9,
                    "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                }
            )
    return dict(counts), dets, w, h


def pick_images(seed: int = 42) -> dict:
    random.seed(seed)
    buckets: dict[str, list] = {k: [] for k in CRITERIA}
    for img, lbl in _iter_labeled_images():
        counts, dets, w, h = _classes_and_dets(img, lbl)
        present = set(counts)
        for site_id, pred in CRITERIA.items():
            if pred(present):
                score = len(present)
                buckets[site_id].append((score, img, counts, dets, w, h))

    selected = {}
    used = set()
    for site_id, items in buckets.items():
        if site_id.startswith("jk-warn"):
            items = sorted(items, key=lambda x: x[0])  # меньше классов
        else:
            random.shuffle(items)
        for item in items:
            img = item[1]
            if img in used:
                continue
            used.add(img)
            selected[site_id] = item
            break
        if site_id not in selected and items:
            selected[site_id] = items[0]
            used.add(items[0][1])
    return selected


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    selected = pick_images()
    meta_lines = ["site_id\tsource\tclasses"]
    for site_id, item in selected.items():
        _score, img, counts, dets, w, h = item
        dest = OUT / f"{site_id}.jpg"
        shutil.copy2(img, dest)
        # рядом json с детекциями из разметки
        import json

        (OUT / f"{site_id}.json").write_text(
            json.dumps(
                {
                    "source": str(img.relative_to(ROOT)).replace("\\", "/"),
                    "width": w,
                    "height": h,
                    "counts": counts,
                    "detections": dets,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        meta_lines.append(f"{site_id}\t{img.name}\t{counts}")
        print(f"{site_id}: {img.name} {counts}")

    missing = [k for k in CRITERIA if k not in selected]
    if missing:
        print("WARNING missing:", missing)
    (OUT / "SOURCES.txt").write_text("\n".join(meta_lines) + "\n", encoding="utf-8")
    print(f"copied {len(selected)} photos -> {OUT}")


if __name__ == "__main__":
    main()
