"""Методика «этап СМР → необходимая техника» (ТЗ ДГП Москвы)."""

from __future__ import annotations

from typing import Dict, List, Set

STAGE_LABELS_RU: Dict[str, str] = {
    "earthworks": "Земляные работы / котлован",
    "piling": "Свайный фундамент",
    "monolith": "Монолитные работы",
    "superstructure": "Надземная часть / монтаж",
}

# Маркеры: достаточно одного из списка, чтобы считать этап «идущим»
STAGE_MARKERS: Dict[str, Set[str]] = {
    "earthworks": {"excavator", "bulldozer"},
    "piling": {"pile_driver"},
    "monolith": {"concrete_mixer", "concrete_pump"},
    "superstructure": {"tower_crane", "autocrane", "crane_manipulator"},
}

# Звено: для incomplete_link (все группы должны быть представлены)
# Группа = set альтернатив (OR внутри, AND между группами)
STAGE_LINKS: Dict[str, List[Set[str]]] = {
    "earthworks": [
        {"dump_truck", "truck"},  # вывоз
    ],
    "piling": [
        {"autocrane", "crane_manipulator"},  # мягкое звено
    ],
    "monolith": [
        {"concrete_mixer"},
        {"concrete_pump"},
    ],
    "superstructure": [],
}

# Опционально ожидаемые (не блокируют, но могут усиливать предупреждение)
STAGE_OPTIONAL: Dict[str, Set[str]] = {
    "earthworks": {"loader", "roller"},
    "piling": set(),
    "monolith": set(),
    "superstructure": set(),
}

# Приоритет при нескольких сигналах на кадре
STAGE_PRIORITY: List[str] = ["piling", "monolith", "earthworks", "superstructure"]

# Классы, которые сами по себе не открывают этап
SUPPORT_ONLY: Set[str] = {"loader", "dump_truck", "truck", "roller"}


def stages_catalog() -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for code in STAGE_PRIORITY:
        out.append(
            {
                "code": code,
                "label": STAGE_LABELS_RU[code],
                "markers": sorted(STAGE_MARKERS[code]),
                "link_groups": [sorted(g) for g in STAGE_LINKS.get(code, [])],
                "optional": sorted(STAGE_OPTIONAL.get(code, set())),
            }
        )
    return out
