"""Обновить в папке «Демо» график и кадры разбора. Фото типов техники не трогает."""

from __future__ import annotations

import shutil
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "Демо"

# Пять кадров = пять дат с шагом 10 дней от 2025-01-10.
# 15 кадров, шаг 10 дней от 2025-01-10. Состав сверен с моделью.
SHOTS = [
    {
        "file": "01_расчистка_норма.jpg",
        "src": "dataML/train_all/valid/images/ta_hf_03372.jpg",
        "date": "2025-01-10",
        "expect": "В норме",
        "why": "Расчистка: бульдозер и самосвал, звено вывоза закрыто.",
    },
    {
        "file": "02_расчистка_простой.jpg",
        "src": "dataML/train_all/valid/images/ta_hf_02965.jpg",
        "date": "2025-01-20",
        "expect": "Простой",
        "why": "Бульдозер есть, самосвала нет — вывозить нечем.",
    },
    {
        "file": "03_расчистка_опережение.jpg",
        "src": "dataML/train_all/valid/images/jsp_0000106_jpg.rf.00b9deefa28a820330afedae0d9b895a.jpg",
        "date": "2025-01-30",
        "expect": "Опережение графика",
        "why": "По плану расчистка, на кадре уже экскаватор.",
    },
    {
        "file": "04_котлован_норма.jpg",
        "src": "dataML/train_all/valid/images/ta_hf_02944.jpg",
        "date": "2025-02-09",
        "expect": "В норме",
        "why": "Котлован: экскаватор и самосвалы.",
    },
    {
        "file": "05_котлован_простой.jpg",
        "src": "dataML/train_all/valid/images/jsp_0000129_jpg.rf.9334505b5ab40770d62f66bc24ee1f11.jpg",
        "date": "2025-02-19",
        "expect": "Простой",
        "why": "Экскаватор есть, самосвала нет.",
    },
    {
        "file": "06_котлован_нарушение.jpg",
        "src": "data/seed_photos/jk-warn-2.jpg",
        "date": "2025-03-01",
        "expect": "Возможное нарушение",
        "why": "По плану котлован, на кадре только грузовик.",
    },
    {
        "file": "07_котлован_опережение.jpg",
        "src": "data/seed_photos/jk-ok-2.jpg",
        "date": "2025-03-11",
        "expect": "Опережение графика",
        "why": "По плану ещё котлован, на кадре башенный кран.",
    },
    {
        "file": "08_фундамент_норма.jpg",
        "src": "dataML/train_all/valid/images/jsp_0000669_jpg.rf.890a1b30054d2fd557a045fdb000078b.jpg",
        "date": "2025-03-21",
        "expect": "В норме",
        "why": "Фундамент: сваебой и кран-манипулятор.",
    },
    {
        "file": "09_фундамент_простой.jpg",
        "src": "dataML/train_all/valid/images/ta_jspark_00573.jpg",
        "date": "2025-03-31",
        "expect": "Простой",
        "why": "Сваебой есть, крана для подачи нет.",
    },
    {
        "file": "10_фундамент_опережение.jpg",
        "src": "dataML/train_all/valid/images/jsp_0000082_jpg.rf.7003f8dc4e3b9d43800922b9e356c447.jpg",
        "date": "2025-04-10",
        "expect": "Опережение графика",
        "why": "По плану фундамент, на кадре уже башенный кран каркаса.",
    },
    {
        "file": "11_каркас_норма.jpg",
        "src": "data/seed_photos/jk-info-1.jpg",
        "date": "2025-04-20",
        "expect": "В норме",
        "why": "Монтаж каркаса: башенный кран, бетонного звена на кадре нет — оно не требуется.",
    },
    {
        "file": "12_каркас_простой.jpg",
        "src": "data/seed_photos/jk-idle-2.jpg",
        "date": "2025-04-30",
        "expect": "Простой",
        "why": "Бетононасос без бетономешалки.",
    },
    {
        "file": "13_каркас_нарушение.jpg",
        "src": "dataML/train_all/valid/images/jsp_0000112_jpg.rf.eb16b23846a263e95a706d3db62a4a73.jpg",
        "date": "2025-05-10",
        "expect": "Возможное нарушение",
        "why": "По плану каркас, на кадре только самосвал.",
    },
    {
        "file": "14_благоустройство_норма.jpg",
        "src": "dataML/train_all/valid/images/jsp_0001248_jpg.rf.c2f8a35ff0d46d33ad01b0f0a7895ee8.jpg",
        "date": "2025-05-20",
        "expect": "В норме",
        "why": "Благоустройство: каток на площадке.",
    },
    {
        "file": "15_благоустройство_опережение.jpg",
        "src": "dataML/train_all/valid/images/ta_hf_02941.jpg",
        "date": "2025-05-30",
        "expect": "Опережение графика",
        "why": "По плану благоустройство, на кадре экскаватор и самосвалы.",
    },
]

PLAN_ROWS = [
    ("Расчистка участка", "2025-01-10", "2025-02-08", "Площадка"),
    ("Откопка котлована", "2025-02-09", "2025-03-20", "Котлован А"),
    ("Устройство фундаментов", "2025-03-21", "2025-04-19", "Сваи"),
    ("Монтаж каркаса", "2025-04-20", "2025-05-19", "Каркас"),
    ("Благоустройство", "2025-05-20", "2025-06-15", "Территория"),
]


def find_photo(shot: dict) -> Path:
    src = shot.get("src")
    if src:
        path = ROOT / src
        if path.is_file():
            return path
        raise FileNotFoundError(src)
    site_ids = shot.get("sites") or []
    for site_id in site_ids:
        candidates = [
            ROOT / "data" / "seed_photos" / f"{site_id}.jpg",
            ROOT / "data" / "photos" / site_id / f"seed-{site_id}.jpg",
        ]
        photos_dir = ROOT / "data" / "photos" / site_id
        if photos_dir.is_dir():
            candidates.extend(sorted(photos_dir.glob("*.jpg")))
        train = ROOT / "data" / "train_12"
        if train.is_dir():
            candidates.extend(train.rglob(f"*{site_id}*"))
        for path in candidates:
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                return path
    raise FileNotFoundError(f"Нет фото для {site_ids}")


def write_plan_csv(path: Path) -> None:
    lines = ["этап,начало,конец,зона"]
    for row in PLAN_ROWS:
        lines.append(",".join(row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def write_plan_xlsx(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "plan"
    ws.append(["этап", "начало", "конец", "зона"])
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9E8FB")
    for row in PLAN_ROWS:
        ws.append(list(row))
    for col, w in zip("ABCD", [28, 14, 14, 22]):
        ws.column_dimensions[col].width = w

    ws2 = wb.create_sheet("как_загружать")
    ws2.append(["Поле на вкладке Демо", "Значение"])
    ws2["A1"].font = Font(bold=True)
    ws2["B1"].font = Font(bold=True)
    for row in [
        ("Календарный план", path.name),
        ("Снимки", "папка «фото/разбор» — выделить все 15 файлов"),
        ("Базовая дата первого кадра", "2025-01-10"),
        ("Шаг между кадрами (дни)", "10"),
        ("Название объекта", "ДЕМО"),
    ]:
        ws2.append(list(row))
    ws2.column_dimensions["A"].width = 32
    ws2.column_dimensions["B"].width = 48
    for row in ws2.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    wb.save(path)


def write_readme(path: Path) -> None:
    shots = "\n".join(
        f"  {s['file']:40} {s['date']}  → {s['expect']}\n      {s['why']}" for s in SHOTS
    )
    path.write_text(
        f"""Демо для организаторов
======================

В папке четыре вещи.

график\\                              календарный план. CSV и Excel — один и тот же файл.
фото\\разбор\\                         15 кадров по порядку: пять этапов, разные статусы.
фото\\техника\\                        по одному кадру на каждый из 12 типов техники.
Для тест модели (Строительная_техника)\\ кадры, чтобы проверить детектор на вкладке «Тест модели».

Разбор площадки
---------------
1. Откройте http://127.0.0.1:5173/#/demo
2. Можно нажать «Загрузить демо-данные» — подставятся график и 15 кадров.
   Либо выберите файлы вручную:
   календарный план — график\\календарный_план.xlsx
   снимки — все файлы из фото\\разбор (порядок по имени 01…15)
3. Базовая дата первого кадра: 2025-01-10
4. Шаг между кадрами: 10 дней
5. «Запустить анализ»

Что показывают кадры разбора
----------------------------
{shots}

Типы техники
------------
Откройте фото\\техника и перетащите кадр на вкладку «Тест модели».
Имя файла — тип машины: экскаватор, бульдозер, погрузчик, самосвал,
бетономешалка, бетононасос, башенный кран, автокран, сваебой, каток,
кран-манипулятор, грузовик.

Папка «Для тест модели (Строительная_техника)» — дополнительные кадры
для той же вкладки. В разбор площадки их загружать не нужно.
""",
        encoding="utf-8",
    )


def main() -> None:
    plan_dir = OUT / "график"
    shots_dir = OUT / "фото" / "разбор"
    for folder in (plan_dir, shots_dir):
        folder.mkdir(parents=True, exist_ok=True)

    write_plan_csv(plan_dir / "календарный_план.csv")
    write_plan_xlsx(plan_dir / "календарный_план.xlsx")
    write_readme(OUT / "ИНСТРУКЦИЯ.txt")

    copied = []
    for old in shots_dir.glob("*.jpg"):
        old.unlink()
    for shot in SHOTS:
        src = find_photo(shot)
        dest = shots_dir / shot["file"]
        shutil.copy2(src, dest)
        copied.append(f"{dest.name} <- {src}")

    print(f"written: {OUT}")
    for line in copied:
        print(" ", line)


if __name__ == "__main__":
    main()
