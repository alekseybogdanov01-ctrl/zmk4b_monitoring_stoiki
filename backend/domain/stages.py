"""Методика «этап СМР → необходимая техника».

Этап по кадру определяется маркерами. Если на снимке машины разных этапов,
берётся более узкий сигнал: фундамент, благоустройство, каркас, котлован, расчистка.
Автокран и кран-манипулятор этап сами не открывают.
"""

from __future__ import annotations

from typing import Dict, List, Set

STAGE_LABELS_RU: Dict[str, str] = {
    "clearing": "Расчистка участка",
    "excavation": "Откопка котлована",
    "foundations": "Устройство фундаментов",
    "frame": "Монтаж каркаса, стены и перекрытия",
    "landscaping": "Благоустройство",
}

# Хронология для планов и сводок, не порядок выбора факта по кадру.
STAGE_PRIORITY: List[str] = [
    "clearing",
    "excavation",
    "foundations",
    "frame",
    "landscaping",
]

# Маркеры: достаточно одного из списка, чтобы считать этап идущим.
STAGE_MARKERS: Dict[str, Set[str]] = {
    "clearing": {"bulldozer", "loader"},
    "excavation": {"excavator"},
    "foundations": {"pile_driver"},
    "frame": {"tower_crane", "concrete_mixer", "concrete_pump"},
    "landscaping": {"roller"},
}

# Звено: все группы должны быть представлены (OR внутри группы).
STAGE_LINKS: Dict[str, List[Set[str]]] = {
    "clearing": [
        {"dump_truck", "truck"},
    ],
    "excavation": [
        {"dump_truck", "truck"},
    ],
    "foundations": [
        {"autocrane", "crane_manipulator"},
    ],
    # Для каркаса звено бетона включается, только если на кадре уже есть миксер или насос.
    "frame": [
        {"concrete_mixer"},
        {"concrete_pump"},
    ],
    "landscaping": [],
}

STAGE_OPTIONAL: Dict[str, Set[str]] = {
    "clearing": set(),
    "excavation": set(),
    "foundations": set(),
    "frame": set(),
    "landscaping": {"loader"},
}

# Сами этап не открывают.
SUPPORT_ONLY: Set[str] = {"dump_truck", "truck", "autocrane", "crane_manipulator"}


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
