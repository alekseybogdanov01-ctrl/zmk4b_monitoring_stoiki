"""12 классов строительной техники (9 базовых + 3 новых)."""

from __future__ import annotations

from enum import Enum
from typing import Dict


class EquipmentClass(str, Enum):
    EXCAVATOR = "excavator"
    BULLDOZER = "bulldozer"
    LOADER = "loader"
    DUMP_TRUCK = "dump_truck"
    CONCRETE_MIXER = "concrete_mixer"
    CONCRETE_PUMP = "concrete_pump"
    TOWER_CRANE = "tower_crane"
    AUTOCRANE = "autocrane"
    PILE_DRIVER = "pile_driver"
    ROLLER = "roller"
    CRANE_MANIPULATOR = "crane_manipulator"
    TRUCK = "truck"


# YOLO class_id → код (порядок = data/train_12)
CLASS_MAPPING: Dict[int, str] = {
    0: EquipmentClass.EXCAVATOR.value,
    1: EquipmentClass.BULLDOZER.value,
    2: EquipmentClass.LOADER.value,
    3: EquipmentClass.DUMP_TRUCK.value,
    4: EquipmentClass.CONCRETE_MIXER.value,
    5: EquipmentClass.CONCRETE_PUMP.value,
    6: EquipmentClass.TOWER_CRANE.value,
    7: EquipmentClass.AUTOCRANE.value,
    8: EquipmentClass.PILE_DRIVER.value,
    9: EquipmentClass.ROLLER.value,
    10: EquipmentClass.CRANE_MANIPULATOR.value,
    11: EquipmentClass.TRUCK.value,
}

# Альтернативные имена из датасетов / моделей
CLASS_NAME_ALIASES: Dict[str, str] = {
    "dump": EquipmentClass.DUMP_TRUCK.value,
    "dumptruck": EquipmentClass.DUMP_TRUCK.value,
    "concrete_mixer_truck": EquipmentClass.CONCRETE_MIXER.value,
    "mixer": EquipmentClass.CONCRETE_MIXER.value,
    "pump": EquipmentClass.CONCRETE_PUMP.value,
    "mobile_crane": EquipmentClass.AUTOCRANE.value,
    "auto_crane": EquipmentClass.AUTOCRANE.value,
    "crane": EquipmentClass.AUTOCRANE.value,
    "manipulator": EquipmentClass.CRANE_MANIPULATOR.value,
    "crane_manipulator": EquipmentClass.CRANE_MANIPULATOR.value,
    "road_roller": EquipmentClass.ROLLER.value,
    "compactor": EquipmentClass.ROLLER.value,
    "lorry": EquipmentClass.TRUCK.value,
    "cargo_truck": EquipmentClass.TRUCK.value,
}

CLASS_LABELS_RU: Dict[str, str] = {
    EquipmentClass.EXCAVATOR.value: "Экскаватор",
    EquipmentClass.BULLDOZER.value: "Бульдозер",
    EquipmentClass.LOADER.value: "Погрузчик",
    EquipmentClass.DUMP_TRUCK.value: "Самосвал",
    EquipmentClass.CONCRETE_MIXER.value: "Бетономешалка",
    EquipmentClass.CONCRETE_PUMP.value: "Бетононасос",
    EquipmentClass.TOWER_CRANE.value: "Башенный кран",
    EquipmentClass.AUTOCRANE.value: "Автокран",
    EquipmentClass.PILE_DRIVER.value: "Сваебой",
    EquipmentClass.ROLLER.value: "Каток",
    EquipmentClass.CRANE_MANIPULATOR.value: "Кран-манипулятор",
    EquipmentClass.TRUCK.value: "Грузовик",
}

CLASS_COLORS: Dict[str, str] = {
    EquipmentClass.EXCAVATOR.value: "#E85D04",
    EquipmentClass.BULLDOZER.value: "#F48C06",
    EquipmentClass.LOADER.value: "#FAA307",
    EquipmentClass.DUMP_TRUCK.value: "#DC2F02",
    EquipmentClass.CONCRETE_MIXER.value: "#9D4EDD",
    EquipmentClass.CONCRETE_PUMP.value: "#7B2CBF",
    EquipmentClass.TOWER_CRANE.value: "#0077B6",
    EquipmentClass.AUTOCRANE.value: "#00B4D8",
    EquipmentClass.PILE_DRIVER.value: "#2D6A4F",
    EquipmentClass.ROLLER.value: "#BC6C25",
    EquipmentClass.CRANE_MANIPULATOR.value: "#48CAE4",
    EquipmentClass.TRUCK.value: "#6C757D",
}

CONFIDENCE_BY_CLASS: Dict[str, float] = {
    EquipmentClass.EXCAVATOR.value: 0.25,
    EquipmentClass.BULLDOZER.value: 0.25,
    EquipmentClass.LOADER.value: 0.25,
    EquipmentClass.DUMP_TRUCK.value: 0.10,
    EquipmentClass.CONCRETE_MIXER.value: 0.35,
    EquipmentClass.CONCRETE_PUMP.value: 0.25,
    EquipmentClass.TOWER_CRANE.value: 0.12,  # слабый класс — ниже порог
    EquipmentClass.AUTOCRANE.value: 0.25,
    EquipmentClass.PILE_DRIVER.value: 0.25,
    EquipmentClass.ROLLER.value: 0.25,
    EquipmentClass.CRANE_MANIPULATOR.value: 0.25,
    EquipmentClass.TRUCK.value: 0.15,
}

DEFAULT_CONFIDENCE = 0.25
YOLO_CONF_FLOOR = 0.05
