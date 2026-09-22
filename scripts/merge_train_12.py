"""Сборка датасета train_12: 9 базовых + roller, crane_manipulator, truck.

Источники:
- ``hakaton (mos)/data/train_all`` — текущие 9 классов
- ``hakaton (mos)/data/new_classes/rf_jspark/_raw`` — Roller, Truck, Crane→manipulator,
  StaticCrane→усиление tower_crane

Запуск из корня v2_hakaton::

    py scripts/merge_train_12.py
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT.parent / "hakaton (mos)" / "data"
OUT_ROOT = PROJECT_ROOT / "data" / "train_12"

# Финальный порядок классов (расширение train_all)
FINAL_NAMES: list[str] = [
    "excavator",  # 0
    "bulldozer",  # 1
    "loader",  # 2
    "dump_truck",  # 3
    "concrete_mixer",  # 4
    "concrete_pump",  # 5
    "tower_crane",  # 6  ← усиливаем StaticCrane
    "autocrane",  # 7
    "pile_driver",  # 8
    "roller",  # 9  NEW
    "crane_manipulator",  # 10 NEW (из jspark Crane)
    "truck",  # 11 NEW
]

# Roboflow jspark _raw class id → FINAL index
JSPARK_RAW_MAP: dict[int, int] = {
    0: 1,  # Bulldozer
    1: 4,  # ConcreteMixer
    2: 10,  # Crane → crane_manipulator (не autocrane)
    3: 0,  # Excavator
    4: 2,  # Loader
    5: 8,  # PileDriving
    6: 5,  # PumpTruck → concrete_pump
    7: 9,  # Roller
    8: 6,  # StaticCrane → tower_crane
    9: 11,  # Truck
}

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _md5_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _find_image(images_dir: Path, stem: str) -> Path | None:
    for ext in IMG_EXTS:
        candidate = images_dir / f"{stem}{ext}"
        if candidate.is_file():
            return candidate
    # Roboflow иногда кладёт .jpg с разным регистром
    matches = list(images_dir.glob(f"{stem}.*"))
    for m in matches:
        if m.suffix.lower() in IMG_EXTS:
            return m
    return None


def _remap_label_lines(text: str, mapping: dict[int, int]) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        try:
            old = int(parts[0])
        except ValueError:
            continue
        new = mapping.get(old)
        if new is None:
            continue
        parts[0] = str(new)
        out.append(" ".join(parts))
    return out


def _copy_pair(
    img_src: Path,
    label_lines: list[str],
    split_out: Path,
    seen_hashes: set[str],
    prefix: str,
    stats: Counter,
) -> bool:
    """Копирует image+label, пропускает дубликаты по md5 картинки."""
    digest = _md5_file(img_src)
    if digest in seen_hashes:
        stats["skipped_dup"] += 1
        return False
    seen_hashes.add(digest)

    images_dir = split_out / "images"
    labels_dir = split_out / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    stem = f"{prefix}_{img_src.stem}"
    img_dst = images_dir / f"{stem}{img_src.suffix.lower()}"
    lbl_dst = labels_dir / f"{stem}.txt"
    shutil.copy2(img_src, img_dst)
    lbl_dst.write_text("\n".join(label_lines) + ("\n" if label_lines else ""), encoding="utf-8")
    stats["copied"] += 1
    for line in label_lines:
        stats[f"cls_{line.split()[0]}"] += 1
    return True


def ingest_train_all(seen: set[str], stats: Counter) -> None:
    """База: существующий train_all (id 0..8 без изменений)."""
    src = SRC_ROOT / "train_all"
    identity = {i: i for i in range(9)}
    for split in ("train", "valid", "test"):
        labels_dir = src / split / "labels"
        images_dir = src / split / "images"
        if not labels_dir.is_dir():
            continue
        out_split = OUT_ROOT / split
        n = 0
        for lbl in labels_dir.iterdir():
            if lbl.suffix.lower() != ".txt":
                continue
            img = _find_image(images_dir, lbl.stem)
            if img is None:
                stats["missing_image"] += 1
                continue
            lines = _remap_label_lines(lbl.read_text(encoding="utf-8", errors="ignore"), identity)
            if _copy_pair(img, lines, out_split, seen, "ta", stats):
                n += 1
        print(f"train_all {split}: +{n}")


def ingest_jspark_raw(seen: set[str], stats: Counter) -> None:
    """Добавляет Roller/Truck/Crane/StaticCrane (+ остальное) из jspark raw."""
    src = SRC_ROOT / "new_classes" / "rf_jspark" / "_raw"
    # Классы, ради которых тащим кадр (новые + усиление крана)
    boost = {6, 9, 10, 11}  # tower_crane, roller, crane_manipulator, truck

    for split in ("train", "valid", "test"):
        labels_dir = src / split / "labels"
        images_dir = src / split / "images"
        if not labels_dir.is_dir():
            continue
        out_split = OUT_ROOT / split
        n = 0
        n_boost = 0
        for lbl in labels_dir.iterdir():
            if lbl.suffix.lower() != ".txt":
                continue
            lines = _remap_label_lines(
                lbl.read_text(encoding="utf-8", errors="ignore"),
                JSPARK_RAW_MAP,
            )
            if not lines:
                continue
            ids = {int(x.split()[0]) for x in lines}
            # Берём кадр, если есть новый класс / tower_crane, либо всегда
            # (всегда — чтобы не потерять разметку; дедуп по hash отсеет копии из train_all)
            interesting = bool(ids & boost)
            img = _find_image(images_dir, lbl.stem)
            if img is None:
                stats["missing_image"] += 1
                continue
            if _copy_pair(img, lines, out_split, seen, "jsp", stats):
                n += 1
                if interesting:
                    n_boost += 1
        print(f"jspark_raw {split}: +{n} (boost-related {n_boost})")


def write_data_yaml() -> None:
    yaml_path = OUT_ROOT / "data.yaml"
    lines = [
        f"path: {OUT_ROOT.resolve().as_posix()}",
        "train: train/images",
        "val: valid/images",
        "test: test/images",
        "",
        f"nc: {len(FINAL_NAMES)}",
        "names:",
    ]
    for i, name in enumerate(FINAL_NAMES):
        lines.append(f"  {i}: {name}")
    lines.append("")
    yaml_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {yaml_path}")


def print_summary() -> None:
    print("\n=== train_12 summary ===")
    for split in ("train", "valid", "test"):
        labels_dir = OUT_ROOT / split / "labels"
        if not labels_dir.is_dir():
            continue
        c: Counter = Counter()
        files = 0
        for f in labels_dir.iterdir():
            if f.suffix.lower() != ".txt":
                continue
            files += 1
            for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                c[int(line.split()[0])] += 1
        imgs = len(list((OUT_ROOT / split / "images").iterdir())) if (OUT_ROOT / split / "images").is_dir() else 0
        print(f"{split}: images={imgs} labels={files}")
        for i, name in enumerate(FINAL_NAMES):
            print(f"  {i:2d} {name:18s} {c[i]}")


def main() -> None:
    if not (SRC_ROOT / "train_all").is_dir():
        print(f"Не найден {SRC_ROOT / 'train_all'}", file=sys.stderr)
        sys.exit(1)
    raw = SRC_ROOT / "new_classes" / "rf_jspark" / "_raw"
    if not raw.is_dir():
        print(f"Не найден {raw}", file=sys.stderr)
        sys.exit(1)

    if OUT_ROOT.exists():
        print(f"Удаляю старый {OUT_ROOT}")
        shutil.rmtree(OUT_ROOT)
    OUT_ROOT.mkdir(parents=True)

    seen: set[str] = set()
    stats: Counter = Counter()
    print("1) ingest train_all…")
    ingest_train_all(seen, stats)
    print("2) ingest jspark _raw (roller/truck/manipulator + tower boost)…")
    ingest_jspark_raw(seen, stats)
    write_data_yaml()
    print_summary()
    print(f"\ncopied={stats['copied']} skipped_dup={stats['skipped_dup']} missing_image={stats['missing_image']}")
    print("DONE ->", OUT_ROOT)


if __name__ == "__main__":
    main()
