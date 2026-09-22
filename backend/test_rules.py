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


if __name__ == "__main__":
    test_incomplete_link_like_tz_example()
    test_full_link_ok()
    test_missing_required()
    print("ok")
