"""All file I/O for Garage. Plain Python, no Home Assistant imports; every method blocks.

Layout under <mount>/<folder>/:

    log.json                     the service log (source of truth), rewritten atomically
    settings.json                per-item Normal/Severe choice, month limits
    stats.json                   learned: last tank reading, fill-ups, battery at rest
    backups/log-<date>.json      a snapshot taken before the first write of each day
    exports/                     service records made for a sale (HTML + CSV)
    receipts/                    photos linked from entries (later)

Nothing is ever deleted: removing an entry marks it `deleted` and keeps it in the file.
"""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

LOG_FILE = "log.json"
SETTINGS_FILE = "settings.json"
STATS_FILE = "stats.json"
BACKUP_DIR = "backups"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ACTIONS = {"changed", "inspected", "rotated", "greased"}
BY = {"self", "dealer", "shop", ""}
PROFILES = {"normal", "severe"}


class GarageError(Exception):
    """Message is shown to the person."""

    status = 400


class StorageUnavailable(GarageError):
    status = 503


class NotFound(GarageError):
    status = 404


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _txt(v: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", "" if v is None else str(v)).strip()[:limit]


@dataclass
class StoreConfig:
    mount_path: str
    folder: str
    require_mount: bool = True


class GarageStore:
    def __init__(self, config: StoreConfig, valid_items: set[int], today: Callable[[], date] | None = None) -> None:
        self.config = config
        self.mount = Path(config.mount_path)
        self.root = self.mount / config.folder if config.folder else self.mount
        self.valid_items = valid_items
        self._today = today or date.today
        self._lock = threading.RLock()

    # ------------------------------------------------------------ readiness
    def status(self) -> dict[str, Any]:
        mounted = (not self.config.require_mount) or os.path.ismount(self.mount)
        return {"mounted": mounted, "path": str(self.root),
                "exists": self.root.is_dir(), "has_log": (self.root / LOG_FILE).is_file()}

    def _require(self) -> None:
        if self.config.require_mount and not os.path.ismount(self.mount):
            raise StorageUnavailable(f"The garage folder isn't mounted ({self.mount}). Nothing was saved.")

    # ------------------------------------------------------------ files
    def _read(self, name: str, default: dict[str, Any]) -> dict[str, Any]:
        p = self.root / name
        if not p.exists():
            return json.loads(json.dumps(default))
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            raise StorageUnavailable(f"Couldn't read {name}: {err}") from err

    def _write(self, name: str, data: dict[str, Any]) -> None:
        self._require()
        self.root.mkdir(parents=True, exist_ok=True)
        p = self.root / name
        tmp = p.with_name(f".{name}.{uuid.uuid4().hex}.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, p)

    def _snapshot(self) -> None:
        src = self.root / LOG_FILE
        if not src.exists():
            return
        dst = self.root / BACKUP_DIR / f"log-{self._today().isoformat()}.json"
        if dst.exists():
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())

    # ------------------------------------------------------------ reads
    def log(self) -> dict[str, Any]:
        with self._lock:
            return self._read(LOG_FILE, {"version": 1, "entries": []})

    def entries(self) -> list[dict[str, Any]]:
        return [e for e in self.log().get("entries", []) if not e.get("deleted")]

    def settings(self) -> dict[str, Any]:
        with self._lock:
            return self._read(SETTINGS_FILE, {"version": 1, "profile": {}, "months": {}})

    # ------------------------------------------------------------ validation
    def _clean(self, data: dict[str, Any], partial: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if "date" in data or not partial:
            d = str(data.get("date") or self._today().isoformat())
            if not DATE_RE.match(d):
                raise GarageError("Date must be YYYY-MM-DD.")
            if date.fromisoformat(d) > self._today():
                raise GarageError("That date is in the future.")
            out["date"] = d
        if "odometer" in data or not partial:
            odo = data.get("odometer")
            if odo in (None, ""):
                out["odometer"] = None
            else:
                try:
                    o = int(round(float(str(odo).replace(",", ""))))
                except ValueError as err:
                    raise GarageError("Odometer must be a number of miles.") from err
                if not 0 <= o <= 2_000_000:
                    raise GarageError("Odometer is out of range.")
                out["odometer"] = o
        if "items" in data or not partial:
            items = []
            for it in data.get("items") or []:
                n = int(it.get("n", -1))
                if n not in self.valid_items:
                    raise GarageError(f"Unknown item {n}.")
                action = it.get("action") or "changed"
                if action not in ACTIONS:
                    raise GarageError(f"Unknown action {action!r}.")
                row: dict[str, Any] = {"n": n, "action": action}
                if it.get("measure") not in (None, ""):
                    try:
                        row["measure"] = round(float(it["measure"]), 2)
                    except (TypeError, ValueError) as err:
                        raise GarageError("A measurement must be a number.") from err
                items.append(row)
            if not items and not partial:
                raise GarageError("Pick at least one item.")
            if "items" in data and not items:
                raise GarageError("Pick at least one item.")
            out["items"] = items
        for key, limit in (("notes", 500), ("by", 10)):
            if key in data or not partial:
                out[key] = _txt(data.get(key), limit)
        if out.get("by", "") not in BY:
            raise GarageError("Who did it must be self, dealer or shop.")
        if "cost" in data or not partial:
            c = data.get("cost")
            if c in (None, ""):
                out["cost"] = None
            else:
                try:
                    out["cost"] = round(float(str(c).replace("$", "").replace(",", "")), 2)
                except ValueError as err:
                    raise GarageError("Cost must be a number.") from err
        return out

    # ------------------------------------------------------------ writes
    def add(self, data: dict[str, Any], source: str = "app", user: str = "") -> dict[str, Any]:
        entry = self._clean(data)
        entry.update({"id": uuid.uuid4().hex[:12], "source": source, "created": _now_iso()})
        if user:
            entry["user"] = _txt(user, 60)
        with self._lock:
            log = self.log()
            self._require()
            self._snapshot()
            log.setdefault("entries", []).append(entry)
            self._write(LOG_FILE, log)
        return entry

    def update(self, entry_id: str, data: dict[str, Any], user: str = "") -> dict[str, Any]:
        patch = self._clean(data, partial=True)
        with self._lock:
            log = self.log()
            for e in log.get("entries", []):
                if e.get("id") == entry_id and not e.get("deleted"):
                    e.update(patch)
                    e["edited"] = True
                    e["updated"] = _now_iso()
                    if user:
                        e["updated_by"] = _txt(user, 60)
                    self._snapshot()
                    self._write(LOG_FILE, log)
                    return e
        raise NotFound("That entry no longer exists.")

    def delete(self, entry_id: str, user: str = "") -> None:
        with self._lock:
            log = self.log()
            for e in log.get("entries", []):
                if e.get("id") == entry_id and not e.get("deleted"):
                    e["deleted"] = True
                    e["deleted_at"] = _now_iso()
                    if user:
                        e["deleted_by"] = _txt(user, 60)
                    self._snapshot()
                    self._write(LOG_FILE, log)
                    return
        raise NotFound("That entry no longer exists.")

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return self._read(STATS_FILE, {"version": 1, "fuel_last": None, "refuels": [], "rest": []})

    def save_stats(self, data: dict[str, Any]) -> None:
        with self._lock:
            self._write(STATS_FILE, data)

    def save_export(self, files: dict[str, str]) -> str:
        """Write each {filename: text} under exports/. Returns the folder."""
        self._require()
        out = self.root / "exports"
        with self._lock:
            out.mkdir(parents=True, exist_ok=True)
            for name, text in files.items():
                if "/" in name or name.startswith("."):
                    raise GarageError(f"Bad export name {name!r}.")
                (out / name).write_text(text, encoding="utf-8")
        return str(out)

    def set_odometer(self, miles: Any) -> dict[str, Any]:
        """A reading typed off the dash, for a vehicle with no odometer sensor. Dated today."""
        try:
            m = int(round(float(str(miles).replace(",", ""))))
        except (TypeError, ValueError) as err:
            raise GarageError("Mileage must be a number of miles.") from err
        if not 0 < m <= 2_000_000:
            raise GarageError("Mileage is out of range.")
        with self._lock:
            s = self.settings()
            s["odometer"] = {"miles": m, "date": self._today().isoformat(), "at": _now_iso()}
            self._write(SETTINGS_FILE, s)
            return s["odometer"]

    def set_profile(self, n: int, profile: str) -> dict[str, Any]:
        if n not in self.valid_items:
            raise GarageError(f"Unknown item {n}.")
        if profile not in PROFILES:
            raise GarageError("Profile must be normal or severe.")
        with self._lock:
            s = self.settings()
            s.setdefault("profile", {})[str(n)] = profile
            self._write(SETTINGS_FILE, s)
            return s
