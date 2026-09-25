"""Минимальные тесты методики план/факт (без модели)."""

from backend.domain.rules import analyze_day
from backend.plan_parse import parse_plan_csv
from backend.seed import EXAMPLE_CSV


def test_incomplete_link_like_tz_example():
    plan = parse_plan_csv(EXAMPLE_CSV)
    r = analyze_day(
        day="2025-03-05",
        counts={"excavator": 1},
        plan_rows=plan,
        photo_ids=["p1"],
    )
    assert r["plan_status"] == "on_track"
    assert any(d["type"] == "incomplete_link" for d in r["deviations"])


def test_full_link_ok():
    plan = parse_plan_csv(EXAMPLE_CSV)
    r = analyze_day(
        day="2025-03-05",
        counts={"excavator": 1, "dump_truck": 2},
        plan_rows=plan,
        photo_ids=["p1"],
    )
    assert r["plan_status"] == "on_track"
    assert r["deviations"] == []


def test_missing_required():
    plan = parse_plan_csv(EXAMPLE_CSV)
    r = analyze_day(
        day="2025-03-05",
        counts={},
        plan_rows=plan,
        photo_ids=["p1"],
    )
    assert r["plan_status"] == "lag"
    assert any(d["type"] == "missing_required" for d in r["deviations"])


def test_foundations_beat_crane():
    plan = parse_plan_csv(EXAMPLE_CSV)
    r = analyze_day(
        day="2025-03-20",
        counts={"pile_driver": 1, "tower_crane": 1, "autocrane": 1},
        plan_rows=plan,
        photo_ids=["p1"],
    )
    assert r["primary_stage"] == "foundations"


def test_roller_alone_is_landscaping():
    plan = parse_plan_csv(EXAMPLE_CSV)
    r = analyze_day(
        day="2025-05-01",
        counts={"roller": 1},
        plan_rows=plan,
        photo_ids=["p1"],
    )
    assert r["primary_stage"] == "landscaping"
    assert r["plan_status"] == "on_track"


def test_crane_alone_does_not_need_concrete_link():
    plan = parse_plan_csv(EXAMPLE_CSV)
    r = analyze_day(
        day="2025-04-10",
        counts={"tower_crane": 1},
        plan_rows=plan,
        photo_ids=["p1"],
    )
    assert r["primary_stage"] == "frame"
    assert r["plan_status"] == "on_track"
    assert r["deviations"] == []


def test_pump_alone_needs_mixer():
    plan = parse_plan_csv(EXAMPLE_CSV)
    r = analyze_day(
        day="2025-04-10",
        counts={"concrete_pump": 1},
        plan_rows=plan,
        photo_ids=["p1"],
    )
    assert r["primary_stage"] == "frame"
    assert any(d["type"] == "incomplete_link" for d in r["deviations"])
    plan = parse_plan_csv(EXAMPLE_CSV)
    r = analyze_day(
        day="2025-03-05",
        counts={"excavator": 1, "roller": 1, "dump_truck": 1},
        plan_rows=plan,
        photo_ids=["p1"],
    )
    assert r["primary_stage"] == "excavation"
    assert "landscaping" not in r["inferred_stages"]


def test_excavator_beats_bulldozer():
    plan = parse_plan_csv(EXAMPLE_CSV)
    r = analyze_day(
        day="2025-03-05",
        counts={"excavator": 1, "bulldozer": 1, "dump_truck": 1},
        plan_rows=plan,
        photo_ids=["p1"],
    )
    assert r["primary_stage"] == "excavation"
    assert "clearing" not in r["inferred_stages"]


if __name__ == "__main__":
    test_incomplete_link_like_tz_example()
    test_full_link_ok()
    test_missing_required()
    test_foundations_beat_crane()
    test_roller_alone_is_landscaping()
    test_crane_alone_does_not_need_concrete_link()
    test_pump_alone_needs_mixer()
    test_roller_with_excavator_stays_pit()
    test_excavator_beats_bulldozer()
    print("ok")
