"""Геометрия ответа НСПД без сети."""

from backend.nspd import ring_centroid, web_mercator_to_wgs
from backend.store import _fill_object_numbers, _next_object_no


def test_web_mercator_roundtrip_near_moscow():
    lat, lng = web_mercator_to_wgs(4187590.0, 7508960.0)
    assert 55.6 < lat < 55.9
    assert 37.5 < lng < 37.8


def test_ring_centroid_is_inside_square():
    ring = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    x, y = ring_centroid(ring)
    assert abs(x - 5) < 0.01
    assert abs(y - 5) < 0.01


def test_object_numbers_fill_gaps_in_created_order():
    data = {
        "sites": {
            "b": {"created_at": "2025-02-01"},
            "a": {"created_at": "2025-01-01", "object_no": 4},
        }
    }
    assert _fill_object_numbers(data) is True
    assert data["sites"]["a"]["object_no"] == 4
    assert data["sites"]["b"]["object_no"] == 5
    assert _next_object_no(data) == 6
