"""Скачивает веса модели (Ml_v2) в ml/weights/best.pt.

Веса не хранятся в git: файл ~50 МБ и меняется каждым переобучением.
Запуск: py -m scripts.fetch_weights
"""

from __future__ import annotations

import argparse
import io
import shutil
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEIGHTS_DIR = PROJECT_ROOT / "ml" / "weights"
TARGET = WEIGHTS_DIR / "best.pt"
RUNS_DIR = PROJECT_ROOT / "ml" / "runs" / "detect" / "ml_v2"

DEFAULT_URL = (
    "https://github.com/alekseybogdanov01-ctrl/zmk4b_monitoring_stoiki"
    "/raw/master/Ml_v2.zip"
)

# Ожидаемые классы: если в архиве другая модель, лучше упасть сразу.
EXPECTED_CLASSES = 12


def _download(url: str) -> bytes:
    print(f"Скачиваю {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "build-watch/1.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            chunks: list[bytes] = []
            got = 0
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                chunks.append(chunk)
                got += len(chunk)
                if total:
                    print(f"\r  {got / 1e6:6.1f} / {total / 1e6:.1f} МБ", end="")
                else:
                    print(f"\r  {got / 1e6:6.1f} МБ", end="")
        print()
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"HTTP {exc.code}: не удалось скачать архив весов") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Нет сети или адрес недоступен: {exc.reason}") from exc
    return b"".join(chunks)


def _extract(raw: bytes, *, keep_metrics: bool) -> None:
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        weights = [i for i in archive.infolist() if i.filename.endswith(".pt")]
        if not weights:
            raise SystemExit("В архиве нет файла .pt")
        best = max(weights, key=lambda i: i.file_size)
        with archive.open(best) as src, TARGET.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        print(f"  веса -> {TARGET} ({TARGET.stat().st_size / 1e6:.1f} МБ)")

        if not keep_metrics:
            return
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        for info in archive.infolist():
            if info.is_dir() or info.filename.endswith(".pt"):
                continue
            dest = RUNS_DIR / Path(info.filename).name
            with archive.open(info) as src, dest.open("wb") as dst:
                shutil.copyfileobj(src, dst)
        print(f"  метрики обучения -> {RUNS_DIR}")


def _verify() -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from ml.infer import load_model, model_class_coverage  # noqa: PLC0415

    model = load_model(TARGET)
    covered = model_class_coverage(model)
    print(f"  классов в модели: {len(model.names)}, из наших распознаётся: {covered}")
    if covered < EXPECTED_CLASSES:
        print(
            f"ВНИМАНИЕ: ожидалось {EXPECTED_CLASSES} классов. "
            f"Проверьте, что скачан актуальный архив.",
            file=sys.stderr,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL, help="Адрес zip-архива с весами")
    parser.add_argument(
        "--from-zip",
        type=Path,
        default=None,
        help="Взять локальный архив вместо скачивания",
    )
    parser.add_argument(
        "--force", action="store_true", help="Перекачать, даже если веса уже на месте"
    )
    parser.add_argument(
        "--no-metrics",
        action="store_true",
        help="Не распаковывать графики и results.csv из архива",
    )
    parser.add_argument(
        "--no-verify", action="store_true", help="Не загружать модель для проверки"
    )
    args = parser.parse_args()

    if TARGET.is_file() and not args.force:
        print(f"Веса уже на месте: {TARGET} — пропускаю (--force чтобы перекачать)")
        return 0

    raw = args.from_zip.read_bytes() if args.from_zip else _download(args.url)
    _extract(raw, keep_metrics=not args.no_metrics)
    if not args.no_verify:
        _verify()
    print("Готово.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
