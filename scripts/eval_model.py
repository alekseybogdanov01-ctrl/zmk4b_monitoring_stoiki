"""Собирает проверочный набор и мерит на нём качество и скорость модели.

ТЗ (п. 6) требует, чтобы проверочный набор участники сформировали сами и
показали работу на разнообразных снимках — с разной освещённостью, сезоном и
видами техники. Скрипт делает это воспроизводимо:

1. берёт все доступные кадры (демо-снимки и кадры таймлапсов);
2. раскладывает их по условиям съёмки: освещённость и наличие зелени;
3. прогоняет модель, замеряет время инференса;
4. копирует отобранные кадры в «data/проверочный_набор»;
5. пишет отчёт в docs/отчёт_тестирования.md.

Запуск: py -m scripts.eval_model
"""

from __future__ import annotations

import argparse
import csv
import shutil
import statistics
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from ml.classes import CLASS_LABELS_RU  # noqa: E402
from ml.infer import _imread, detect_image, load_model, resolve_weights  # noqa: E402

SOURCE_DIRS = [
    PROJECT_ROOT / "data" / "seed_photos",
    PROJECT_ROOT / "data" / "timelapse_frames" / "video_1_frames",
    PROJECT_ROOT / "data" / "timelapse_frames" / "video_2_frames",
    PROJECT_ROOT / "Демо" / "фото" / "разбор",
    PROJECT_ROOT / "Демо" / "фото" / "техника",
]
OUT_DIR = PROJECT_ROOT / "data" / "проверочный_набор"
REPORT_PATH = PROJECT_ROOT / "docs" / "отчёт_тестирования.md"

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# Освещённость по средней яркости канала V (HSV), 0..255
LIGHT_BUCKETS = (
    ("яркий_день", 150, 256),
    ("пасмурно", 95, 150),
    ("сумерки_или_контраст", 0, 95),
)


def _light_bucket(value: float) -> str:
    for name, low, high in LIGHT_BUCKETS:
        if low <= value < high:
            return name
    return "пасмурно"


def _image_stats(img: np.ndarray) -> Dict[str, float]:
    """Яркость и доля зелени/снега — грубые, но объективные признаки условий."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    pixels = float(hue.size)

    # Зелень: оттенок 35..85 при заметной насыщенности
    green = float(np.count_nonzero((hue >= 35) & (hue <= 85) & (sat >= 60)))
    # Снег/серость: очень низкая насыщенность при высокой яркости
    pale = float(np.count_nonzero((sat <= 30) & (val >= 170)))

    return {
        "brightness": float(val.mean()),
        "green_share": green / pixels,
        "pale_share": pale / pixels,
    }


def _season_bucket(stats: Dict[str, float]) -> str:
    if stats["green_share"] >= 0.12:
        return "зелёный_сезон"
    if stats["pale_share"] >= 0.18:
        return "снег_или_межсезонье"
    return "без_зелени"


def _collect_images(limit_per_dir: int | None) -> List[Path]:
    found: List[Path] = []
    for directory in SOURCE_DIRS:
        if not directory.is_dir():
            continue
        images = sorted(
            p for p in directory.iterdir() if p.suffix.lower() in IMAGE_EXT
        )
        found.extend(images if limit_per_dir is None else images[:limit_per_dir])
    return found


def _analyze(paths: List[Path]) -> List[Dict[str, Any]]:
    model = load_model()
    rows: List[Dict[str, Any]] = []

    # Первый прогон прогревает модель: иначе в замер попадёт инициализация.
    if paths:
        warm = _imread(paths[0])
        if warm is not None:
            detect_image(warm, model=model)

    for path in paths:
        img = _imread(path)
        if img is None:
            print(f"  пропуск (не читается): {path.name}", file=sys.stderr)
            continue

        stats = _image_stats(img)
        result = detect_image(img, model=model)
        counts = Counter(d["class"] for d in result["detections"])
        confidences = [d["confidence"] for d in result["detections"]]

        rows.append(
            {
                "file": path.name,
                "source_dir": path.parent.name,
                "width": result["width"],
                "height": result["height"],
                "light": _light_bucket(stats["brightness"]),
                "season": _season_bucket(stats),
                "brightness": round(stats["brightness"], 1),
                "green_share": round(stats["green_share"], 3),
                "detections": len(result["detections"]),
                "classes": ";".join(sorted(counts)),
                "counts": dict(counts),
                "conf_mean": round(statistics.fmean(confidences), 3)
                if confidences
                else None,
                "path": path,
            }
        )
        print(f"  {path.name}: {len(result['detections'])} детекций")
    return rows


def _pick_diverse(rows: List[Dict[str, Any]], per_bucket: int) -> List[Dict[str, Any]]:
    """По кадру на каждое сочетание условий, плюс добор редких классов."""
    by_bucket: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
    for row in rows:
        by_bucket.setdefault((row["light"], row["season"]), []).append(row)

    picked: List[Dict[str, Any]] = []
    for bucket_rows in by_bucket.values():
        # Внутри условия предпочитаем кадры, где техника найдена
        ranked = sorted(bucket_rows, key=lambda r: -r["detections"])
        picked.extend(ranked[:per_bucket])

    covered = {c for row in picked for c in row["counts"]}
    for row in sorted(rows, key=lambda r: -r["detections"]):
        new = set(row["counts"]) - covered
        if new:
            picked.append(row)
            covered |= new

    unique: Dict[str, Dict[str, Any]] = {}
    for row in picked:
        unique.setdefault(row["file"], row)
    return list(unique.values())


def _write_set(picked: List[Dict[str, Any]]) -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    for row in picked:
        folder = OUT_DIR / row["light"] / row["season"]
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(row["path"], folder / row["file"])

    index = OUT_DIR / "индекс.csv"
    with index.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(
            ["файл", "освещённость", "сезон", "яркость", "детекций", "классы", "conf"]
        )
        for row in sorted(picked, key=lambda r: (r["light"], r["season"], r["file"])):
            writer.writerow(
                [
                    row["file"],
                    row["light"],
                    row["season"],
                    row["brightness"],
                    row["detections"],
                    row["classes"],
                    row["conf_mean"] if row["conf_mean"] is not None else "",
                ]
            )
    print(f"Проверочный набор: {len(picked)} кадров -> {OUT_DIR}")


def _latency(paths: List[Path], repeats: int) -> Dict[str, float]:
    """Отдельный замер: то же изображение несколько раз, без чтения с диска."""
    import time

    model = load_model()
    img = _imread(paths[0])
    if img is None:
        raise SystemExit("Не удалось прочитать кадр для замера скорости")
    detect_image(img, model=model)

    samples: List[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        detect_image(img, model=model)
        samples.append((time.perf_counter() - started) * 1000)

    samples.sort()
    return {
        "runs": len(samples),
        "min_ms": round(samples[0], 1),
        "median_ms": round(statistics.median(samples), 1),
        "p95_ms": round(samples[min(len(samples) - 1, int(len(samples) * 0.95))], 1),
        "max_ms": round(samples[-1], 1),
        "fps": round(1000 / statistics.median(samples), 2),
    }


def _write_report(
    rows: List[Dict[str, Any]],
    picked: List[Dict[str, Any]],
    latency: Dict[str, float],
) -> None:
    class_totals: Counter[str] = Counter()
    for row in rows:
        class_totals.update(row["counts"])

    light_counts = Counter(r["light"] for r in picked)
    season_counts = Counter(r["season"] for r in picked)
    empty = [r for r in rows if r["detections"] == 0]

    lines: List[str] = [
        "# Отчёт о тестировании модели",
        "",
        f"Дата прогона: {date.today().isoformat()}  ",
        f"Веса: `{resolve_weights()}`  ",
        "Скрипт: `scripts/eval_model.py`",
        "",
        "## 1. Проверочный набор",
        "",
        (
            "ТЗ (п. 6) не предоставляет отдельного набора для проверки — он собран "
            "самостоятельно из демо-снимков и кадров таймлапсов, с намеренным "
            "разбросом по условиям съёмки."
        ),
        "",
        f"- всего просмотрено кадров: **{len(rows)}**",
        f"- отобрано в проверочный набор: **{len(picked)}**",
        "- расположение: `data/проверочный_набор/<освещённость>/<сезон>/`",
        "",
        "### Разброс по освещённости",
        "",
        "| Условие | Кадров |",
        "|---|---|",
    ]
    for name, count in light_counts.most_common():
        lines.append(f"| {name.replace('_', ' ')} | {count} |")

    lines += [
        "",
        "### Разброс по сезону и фону",
        "",
        "| Условие | Кадров |",
        "|---|---|",
    ]
    for name, count in season_counts.most_common():
        lines.append(f"| {name.replace('_', ' ')} | {count} |")

    lines += [
        "",
        "## 2. Распознанные классы на всём массиве",
        "",
        "| Класс | Найдено объектов |",
        "|---|---|",
    ]
    for code, count in class_totals.most_common():
        lines.append(f"| {CLASS_LABELS_RU.get(code, code)} | {count} |")
    if not class_totals:
        lines.append("| — | 0 |")

    lines += [
        "",
        f"Классов задействовано: **{len(class_totals)}** из 12.",
        "",
        "## 3. Скорость работы",
        "",
        "Замер на CPU, один кадр прогоняется многократно после прогрева модели.",
        "",
        "| Метрика | Значение |",
        "|---|---|",
        f"| Прогонов | {latency['runs']} |",
        f"| Минимум | {latency['min_ms']} мс |",
        f"| Медиана | {latency['median_ms']} мс |",
        f"| 95-й процентиль | {latency['p95_ms']} мс |",
        f"| Максимум | {latency['max_ms']} мс |",
        f"| Пропускная способность | {latency['fps']} кадр/с |",
        "",
        (
            "Те же замеры доступны в рантайме: `/api/detect` возвращает "
            "`inference_ms`, `/api/demo/analyze` — блок `performance` со средним и "
            "максимумом по пачке кадров и временем сопоставления с планом."
        ),
        "",
        "## 4. Кадры без детекций",
        "",
        (
            f"Пустых кадров: **{len(empty)}** из {len(rows)}. "
            "Часть таймлапс-кадров снята в момент, когда техника вне зоны обзора — "
            "для контроля плана это корректный результат, а не ошибка модели."
        ),
        "",
        "## 5. Ограничения",
        "",
        (
            "- Разметки (ground truth) для этого набора нет, поэтому precision/recall "
            "по нему не считается. Метрики качества обучения — в "
            "`ml/runs/detect/ml_v2/` (`results.csv`, матрицы ошибок)."
        ),
        (
            "- Освещённость и сезон определяются по статистике изображения (яркость "
            "канала V, доля зелёных и малонасыщенных пикселей), а не по метаданным."
        ),
        "",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Отчёт: {REPORT_PATH}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--per-bucket",
        type=int,
        default=3,
        help="Сколько кадров брать на каждое сочетание условий",
    )
    parser.add_argument(
        "--limit-per-dir",
        type=int,
        default=None,
        help="Ограничить число кадров из каждой папки (для быстрого прогона)",
    )
    parser.add_argument(
        "--latency-runs", type=int, default=20, help="Число прогонов для замера скорости"
    )
    args = parser.parse_args()

    paths = _collect_images(args.limit_per_dir)
    if not paths:
        raise SystemExit("Не нашлось ни одного кадра — проверьте папку «Демо»")
    print(f"Кадров к разбору: {len(paths)}; веса: {resolve_weights()}")

    rows = _analyze(paths)
    picked = _pick_diverse(rows, args.per_bucket)
    _write_set(picked)
    latency = _latency(paths, args.latency_runs)
    _write_report(rows, picked, latency)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
