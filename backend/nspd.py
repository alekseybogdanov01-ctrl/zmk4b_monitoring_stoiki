"""Адрес и координаты участка по кадастровому номеру из НСПД."""

from __future__ import annotations

import json
import logging
import math
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CAD_RE = re.compile(r"^\d+:\d+:\d+:\d+$")
_SEARCH = "https://nspd.gov.ru/api/geoportal/v2/search/geoportal"
_EARTH = 6378137.0


class NspdError(Exception):
    pass


class NspdNotFound(NspdError):
    pass


def normalize_cadastral(raw: str) -> str:
    return re.sub(r"\s+", "", str(raw or "").strip())


def web_mercator_to_wgs(x: float, y: float) -> Tuple[float, float]:
    lon = (x / _EARTH) * 180.0 / math.pi
    lat = (2.0 * math.atan(math.exp(y / _EARTH)) - math.pi / 2.0) * 180.0 / math.pi
    return lat, lon


def ring_centroid(ring: List[List[float]]) -> Tuple[float, float]:
    pts = list(ring)
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return sum(xs) / len(xs), sum(ys) / len(ys)
    area = 0.0
    cx = 0.0
    cy = 0.0
    count = len(pts)
    for i in range(count):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % count]
        cross = x1 * y2 - x2 * y1
        area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    area *= 0.5
    if abs(area) < 1e-6:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return sum(xs) / len(xs), sum(ys) / len(ys)
    return cx / (6.0 * area), cy / (6.0 * area)


def geometry_point(geometry: Dict[str, Any]) -> Tuple[float, float]:
    kind = geometry.get("type")
    coords = geometry.get("coordinates")
    if kind == "Point":
        return float(coords[0]), float(coords[1])
    if kind == "Polygon":
        return ring_centroid(coords[0])
    if kind == "MultiPolygon":
        ring = max((poly[0] for poly in coords), key=len)
        return ring_centroid(ring)
    raise NspdError("У участка нет контура")


def _to_lat_lng(x: float, y: float) -> Tuple[float, float]:
    if abs(x) <= 180 and abs(y) <= 90:
        return y, x
    return web_mercator_to_wgs(x, y)


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "StroyRadar/1.0",
            "Referer": "https://nspd.gov.ru/",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read()
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, ssl.SSLCertVerificationError):
            # Сертификат НСПД выпущен российским удостоверяющим центром,
            # его часто нет в стандартном наборе доверенных корней.
            logger.warning("NSPD TLS verify failed, retrying without verification")
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(request, timeout=20, context=context) as response:
                return response.read()
        raise NspdError("НСПД не ответила") from exc
    except TimeoutError as exc:
        raise NspdError("НСПД не ответила") from exc


def lookup_parcel(raw_cadastral: str) -> Dict[str, Any]:
    cadastral = normalize_cadastral(raw_cadastral)
    if not CAD_RE.fullmatch(cadastral):
        raise NspdError("Кадастровый номер укажите в виде 77:09:0004012:1145")
    query = urllib.parse.urlencode({"thematicSearchId": 1, "query": cadastral})
    try:
        payload = json.loads(_fetch(f"{_SEARCH}?{query}").decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise NspdError("НСПД вернула неразборчивый ответ") from exc
    except NspdError:
        raise
    except Exception as exc:
        raise NspdError("НСПД не ответила") from exc

    features = ((payload.get("data") or {}).get("features")) or []
    feature = _match_feature(features, cadastral)
    if feature is None:
        raise NspdNotFound(f"Участок {cadastral} в НСПД не найден")
    props = feature.get("properties") or {}
    options = props.get("options") or {}
    x, y = geometry_point(feature.get("geometry") or {})
    lat, lng = _to_lat_lng(x, y)
    address = (options.get("readable_address") or "").strip() or None
    return {
        "cadastral_number": options.get("cad_num") or cadastral,
        "address": address,
        "lat": round(lat, 6),
        "lng": round(lng, 6),
    }


def _match_feature(features: List[Dict[str, Any]], cadastral: str) -> Optional[Dict[str, Any]]:
    exact = None
    for feature in features:
        props = feature.get("properties") or {}
        options = props.get("options") or {}
        number = options.get("cad_num") or props.get("externalKey") or props.get("descr")
        if normalize_cadastral(str(number or "")) == cadastral:
            exact = feature
            break
    return exact or (features[0] if features else None)
