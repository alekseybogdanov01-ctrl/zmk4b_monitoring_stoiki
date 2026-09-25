"""JSON-хранилище сайтов, планов, фото и детекций."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
STORE_PATH = DATA_DIR / "store.json"
PHOTOS_DIR = DATA_DIR / "photos"

_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _empty_store() -> Dict[str, Any]:
    return {"sites": {}, "photos": {}, "demo_sessions": {}}


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)


def load_store() -> Dict[str, Any]:
    ensure_dirs()
    if not STORE_PATH.exists():
        store = _empty_store()
        save_store(store)
        return store
    with STORE_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("sites", {})
    data.setdefault("photos", {})
    data.setdefault("demo_sessions", {})
    return data


def save_store(store: Dict[str, Any]) -> None:
    ensure_dirs()
    tmp = STORE_PATH.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    tmp.replace(STORE_PATH)


def list_sites() -> List[Dict[str, Any]]:
    with _lock:
        store = load_store()
        return list(store["sites"].values())


def get_site(site_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        return load_store()["sites"].get(site_id)


def upsert_site(site: Dict[str, Any]) -> Dict[str, Any]:
    with _lock:
        store = load_store()
        site_id = site.get("id") or str(uuid.uuid4())
        site["id"] = site_id
        site.setdefault("plan", [])
        site.setdefault("created_at", _now_iso())
        site["updated_at"] = _now_iso()
        store["sites"][site_id] = site
        save_store(store)
        return site


def ensure_object_numbers() -> None:
    """Короткий номер объекта для тех площадок, у которых его ещё нет."""
    with _lock:
        data = load_store()
        if _fill_object_numbers(data):
            save_store(data)


def insert_site(site: Dict[str, Any]) -> Dict[str, Any]:
    """Новая площадка с очередным номером. Пустое имя становится «Объект № N»."""
    with _lock:
        data = load_store()
        _fill_object_numbers(data)
        number = _next_object_no(data)
        site_id = site.get("id") or str(uuid.uuid4())
        name = str(site.get("name") or "").strip() or f"Объект № {number}"
        record = {
            **site,
            "id": site_id,
            "name": name,
            "object_no": number,
            "plan": site.get("plan") or [],
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        data["sites"][site_id] = record
        save_store(data)
        return record


def _next_object_no(data: Dict[str, Any]) -> int:
    numbers = [
        site.get("object_no")
        for site in (data.get("sites") or {}).values()
        if isinstance(site.get("object_no"), int)
    ]
    return max(numbers, default=0) + 1


def _fill_object_numbers(data: Dict[str, Any]) -> bool:
    sites = data.get("sites") or {}
    changed = False
    pending = sorted(
        (
            (site.get("created_at") or "", site_id)
            for site_id, site in sites.items()
            if not isinstance(site.get("object_no"), int)
        )
    )
    number = _next_object_no(data)
    for _, site_id in pending:
        sites[site_id]["object_no"] = number
        number += 1
        changed = True
    return changed


def set_site_plan(site_id: str, plan: List[Dict[str, Any]]) -> Dict[str, Any]:
    with _lock:
        store = load_store()
        site = store["sites"].get(site_id)
        if site is None:
            raise KeyError(site_id)
        site["plan"] = plan
        site["updated_at"] = _now_iso()
        save_store(store)
        return site


def save_photo_bytes(
    site_id: str,
    raw: bytes,
    *,
    filename: str,
    captured_at: str,
    detections: List[Dict[str, Any]],
    width: int,
    height: int,
    model: str,
) -> Dict[str, Any]:
    with _lock:
        store = load_store()
        if site_id not in store["sites"]:
            raise KeyError(site_id)

        photo_id = str(uuid.uuid4())
        ext = Path(filename).suffix.lower() or ".jpg"
        if ext not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
            ext = ".jpg"
        rel = f"{site_id}/{photo_id}{ext}"
        abs_path = PHOTOS_DIR / rel
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(raw)

        photo = {
            "id": photo_id,
            "site_id": site_id,
            "captured_at": captured_at[:10],
            "filename": filename,
            "path": str(rel).replace("\\", "/"),
            "width": width,
            "height": height,
            "model": model,
            "detections": detections,
            "created_at": _now_iso(),
        }
        store["photos"][photo_id] = photo
        save_store(store)
        return photo


def list_photos(site_id: str) -> List[Dict[str, Any]]:
    with _lock:
        store = load_store()
        photos = [
            p for p in store["photos"].values() if p.get("site_id") == site_id
        ]
        photos.sort(key=lambda p: (p.get("captured_at", ""), p.get("created_at", "")))
        return photos


def get_photo(photo_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        return load_store()["photos"].get(photo_id)


def photo_file_path(photo: Dict[str, Any]) -> Path:
    return PHOTOS_DIR / photo["path"]


def save_demo_session(session: Dict[str, Any]) -> Dict[str, Any]:
    with _lock:
        store = load_store()
        sid = session.get("id") or str(uuid.uuid4())
        session["id"] = sid
        session["updated_at"] = _now_iso()
        store["demo_sessions"][sid] = session
        save_store(store)
        return session


def get_demo_session(session_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        return load_store()["demo_sessions"].get(session_id)
