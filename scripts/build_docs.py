"""Собирает PDF из markdown-документации (ТЗ требует .doc или .pdf).

Источник правды — текст в `docs/*.md`; PDF генерируется из него, чтобы правки
вносились в одном месте.

Запуск: py -m scripts.build_docs
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path
from typing import Iterable, List

import matplotlib
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"

# DejaVu идёт вместе с matplotlib (зависимость ultralytics) и содержит кириллицу,
# поэтому шрифт доступен и в Docker, и на Windows без установки в систему.
FONT_DIR = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
FONTS = {
    "Doc": "DejaVuSans.ttf",
    "Doc-Bold": "DejaVuSans-Bold.ttf",
    "Doc-Mono": "DejaVuSansMono.ttf",
}


def _register_fonts() -> None:
    for name, filename in FONTS.items():
        path = FONT_DIR / filename
        if not path.is_file():
            raise SystemExit(f"Не найден шрифт {path}")
        pdfmetrics.registerFont(TTFont(name, str(path)))


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "DocH1",
            parent=base["Heading1"],
            fontName="Doc-Bold",
            fontSize=20,
            leading=26,
            spaceBefore=0,
            spaceAfter=10,
            textColor=colors.HexColor("#111318"),
        ),
        "h2": ParagraphStyle(
            "DocH2",
            parent=base["Heading2"],
            fontName="Doc-Bold",
            fontSize=14,
            leading=19,
            spaceBefore=16,
            spaceAfter=6,
            textColor=colors.HexColor("#1b2430"),
        ),
        "h3": ParagraphStyle(
            "DocH3",
            parent=base["Heading3"],
            fontName="Doc-Bold",
            fontSize=11.5,
            leading=16,
            spaceBefore=11,
            spaceAfter=4,
            textColor=colors.HexColor("#243040"),
        ),
        "body": ParagraphStyle(
            "DocBody",
            parent=base["BodyText"],
            fontName="Doc",
            fontSize=9.8,
            leading=14.5,
            spaceAfter=7,
            alignment=TA_LEFT,
        ),
        "cell": ParagraphStyle(
            "DocCell", fontName="Doc", fontSize=8.6, leading=12
        ),
        "cellHead": ParagraphStyle(
            "DocCellHead", fontName="Doc-Bold", fontSize=8.6, leading=12
        ),
        "code": ParagraphStyle(
            "DocCode", fontName="Doc-Mono", fontSize=8.4, leading=11.5
        ),
        "caption": ParagraphStyle(
            "DocCaption",
            fontName="Doc",
            fontSize=8.4,
            leading=11,
            textColor=colors.HexColor("#5b6472"),
            spaceAfter=10,
        ),
    }


def _inline(text: str) -> str:
    """Markdown-разметка внутри строки → мини-HTML для reportlab."""
    out = html.escape(text, quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(
        r"`(.+?)`",
        r'<font face="Doc-Mono" size="8.6">\1</font>',
        out,
    )
    out = re.sub(r"\[(.+?)\]\((.+?)\)", r'<link href="\2">\1</link>', out)
    return out


def _is_table_row(line: str) -> bool:
    return line.startswith("|") and line.endswith("|")


def _split_row(line: str) -> List[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _make_table(rows: List[List[str]], styles: dict, width: float) -> Table:
    header, *body = rows
    data = [[Paragraph(_inline(c), styles["cellHead"]) for c in header]]
    data += [[Paragraph(_inline(c), styles["cell"]) for c in row] for row in body]

    columns = len(header)
    # Первая колонка шире: в наших таблицах там поле или параметр
    if columns > 1:
        first = width * (0.3 if columns <= 3 else 0.24)
        rest = (width - first) / (columns - 1)
        col_widths = [first] + [rest] * (columns - 1)
    else:
        col_widths = [width]

    table = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f5")),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#b9c2ce")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d5dbe3")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _build_flowables(lines: Iterable[str], styles: dict, width: float) -> List:
    flow: List = []
    buffer: List[str] = []
    bullets: List[str] = []
    numbered: List[str] = []
    table_rows: List[List[str]] = []
    code: List[str] = []
    in_code = False

    def flush_paragraph() -> None:
        if buffer:
            flow.append(Paragraph(_inline(" ".join(buffer)), styles["body"]))
            buffer.clear()

    def flush_bullets() -> None:
        if not bullets:
            return
        items = [
            ListItem(Paragraph(_inline(b), styles["body"]), leftIndent=12)
            for b in bullets
        ]
        flow.append(
            ListFlowable(items, bulletType="bullet", start="•", leftIndent=14)
        )
        bullets.clear()

    def flush_numbered() -> None:
        if not numbered:
            return
        items = [
            ListItem(Paragraph(_inline(n), styles["body"]), leftIndent=14)
            for n in numbered
        ]
        flow.append(ListFlowable(items, bulletType="1", leftIndent=16))
        numbered.clear()

    def flush_table() -> None:
        if not table_rows:
            return
        flow.append(Spacer(1, 3))
        flow.append(_make_table(table_rows, styles, width))
        flow.append(Spacer(1, 9))
        table_rows.clear()

    def flush_all() -> None:
        flush_paragraph()
        flush_bullets()
        flush_numbered()
        flush_table()

    for raw in lines:
        line = raw.rstrip()

        if line.strip().startswith("```"):
            if in_code:
                flow.append(
                    Preformatted("\n".join(code), styles["code"], maxLineLength=110)
                )
                flow.append(Spacer(1, 8))
                code.clear()
            else:
                flush_all()
            in_code = not in_code
            continue
        if in_code:
            code.append(line)
            continue

        if not line.strip():
            flush_all()
            continue

        image = re.fullmatch(r"!\[(.*?)\]\((.+?)\)", line.strip())
        if image:
            flush_all()
            path = (DOCS_DIR / image.group(2)).resolve()
            if path.is_file():
                from PIL import Image as PILImage  # noqa: PLC0415

                with PILImage.open(path) as img:
                    ratio = img.height / img.width
                flow.append(Image(str(path), width=width, height=width * ratio))
                if image.group(1):
                    flow.append(Paragraph(_inline(image.group(1)), styles["caption"]))
            continue

        if _is_table_row(line):
            cells = _split_row(line)
            if all(set(c) <= {"-", ":", " "} and c for c in cells):
                continue  # строка-разделитель заголовка
            flush_paragraph()
            flush_bullets()
            flush_numbered()
            table_rows.append(cells)
            continue
        flush_table()

        if line.startswith("### "):
            flush_all()
            flow.append(Paragraph(_inline(line[4:]), styles["h3"]))
            continue
        if line.startswith("## "):
            flush_all()
            flow.append(Paragraph(_inline(line[3:]), styles["h2"]))
            continue
        if line.startswith("# "):
            flush_all()
            if flow:
                flow.append(PageBreak())
            flow.append(Paragraph(_inline(line[2:]), styles["h1"]))
            continue

        stripped = line.strip()
        if stripped.startswith(("- ", "* ")):
            flush_paragraph()
            flush_numbered()
            bullets.append(stripped[2:])
            continue
        ordered = re.match(r"\d+\.\s+(.*)", stripped)
        if ordered:
            flush_paragraph()
            flush_bullets()
            numbered.append(ordered.group(1))
            continue
        # Перенос строки внутри пункта списка — продолжение того же пункта
        if line.startswith(("  ", "\t")):
            if numbered:
                numbered[-1] = f"{numbered[-1]} {stripped}"
                continue
            if bullets:
                bullets[-1] = f"{bullets[-1]} {stripped}"
                continue

        flush_bullets()
        flush_numbered()
        buffer.append(stripped)

    flush_all()
    return flow


def build(source: Path, target: Path) -> None:
    _register_fonts()
    styles = _styles()

    doc = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        title=source.stem,
        author="Build Watch",
    )
    width = doc.width

    def footer(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont("Doc", 8)
        canvas.setFillColor(colors.HexColor("#7a838f"))
        canvas.drawRightString(
            A4[0] - 18 * mm, 10 * mm, f"стр. {document.page}"
        )
        canvas.drawString(20 * mm, 10 * mm, "Build Watch — мониторинг стройплощадки")
        canvas.restoreState()

    lines = source.read_text(encoding="utf-8").splitlines()
    doc.build(
        _build_flowables(lines, styles, width),
        onFirstPage=footer,
        onLaterPages=footer,
    )
    print(f"{source.name} -> {target} ({target.stat().st_size / 1024:.0f} КБ)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "sources",
        nargs="*",
        type=Path,
        default=None,
        help="Markdown-файлы (по умолчанию все docs/*.md)",
    )
    args = parser.parse_args()

    sources = args.sources or sorted(DOCS_DIR.glob("*.md"))
    if not sources:
        raise SystemExit("Не найдено ни одного markdown-файла в docs/")

    for source in sources:
        build(source, source.with_suffix(".pdf"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
