"""Quick label counts for train_all and rf_jspark raw."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

BASE = Path(r"C:\Users\Sber\Курсор\hakaton (mos)\data")


def count_labels(label_dir: Path) -> tuple[Counter, int]:
    c: Counter = Counter()
    files = 0
    if not label_dir.is_dir():
        return c, 0
    for f in label_dir.iterdir():
        if f.suffix.lower() != ".txt":
            continue
        files += 1
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                cid = int(line.split()[0])
            except ValueError:
                continue
            c[cid] += 1
    return c, files


def main() -> None:
    names9 = [
        "excavator",
        "bulldozer",
        "loader",
        "dump_truck",
        "concrete_mixer",
        "concrete_pump",
        "tower_crane",
        "autocrane",
        "pile_driver",
    ]
    for split in ("train", "valid"):
        c, n = count_labels(BASE / "train_all" / split / "labels")
        print(f"=== train_all {split} === files {n}")
        for i, name in enumerate(names9):
            print(f"  {i} {name}: {c[i]}")

    raw_names = [
        "Bulldozer",
        "ConcreteMixer",
        "Crane",
        "Excavator",
        "Loader",
        "PileDriving",
        "PumpTruck",
        "Roller",
        "StaticCrane",
        "Truck",
    ]
    for split in ("train", "valid"):
        c, n = count_labels(BASE / "new_classes" / "rf_jspark" / "_raw" / split / "labels")
        print(f"=== rf_jspark _raw {split} === files {n}")
        for i, name in enumerate(raw_names):
            print(f"  {i} {name}: {c[i]}")

    for split in ("train", "valid", "test"):
        img = BASE / "train_all" / split / "images"
        n_img = sum(1 for p in img.iterdir() if p.is_file()) if img.is_dir() else 0
        print(f"train_all {split} images: {n_img}")


if __name__ == "__main__":
    main()
