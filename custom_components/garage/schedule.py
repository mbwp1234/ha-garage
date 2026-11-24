"""The maintenance schedule and the maths over it.

Plain Python, no Home Assistant imports, so it can be tested on its own.

Vocabulary:
  interval   miles between services for an item under the chosen profile
  first      the first due point when it differs from the interval (coolant: 100k, then every 50k)
  last       the newest log entry that counts for the item
  status     over | soon | ok | nolog
             nolog = never logged AND the first due point has passed. An item that has
             never been logged but is not due yet (coolant before 100k) is ok, not nolog:
             a missing record only matters once something should have happened.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

SCHEDULE_DIR = Path(__file__).parent / "schedules"

# Which logged actions reset an item's clock, by the item's kind.
RESETS: dict[str, set[str]] = {
    "change": {"changed"},
    "inspect": {"inspected", "changed"},
    "rotate": {"rotated"},
    "grease": {"greased"},
}
DEFAULT_ACTION = {"change": "changed", "inspect": "inspected", "rotate": "rotated", "grease": "greased"}

STATUS_RANK = {"over": 0, "soon": 1, "nolog": 2, "ok": 3}


def available_schedules() -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(SCHEDULE_DIR.glob("*.json")):
        try:
            out[p.stem] = json.loads(p.read_text(encoding="utf-8"))["title"]
        except (OSError, ValueError, KeyError):
            continue
    return out


def load_schedule(schedule_id: str) -> dict[str, Any]:
    if not schedule_id.replace("_", "").isalnum():
        raise ValueError(f"Bad schedule id {schedule_id!r}")
    data = json.loads((SCHEDULE_DIR / f"{schedule_id}.json").read_text(encoding="utf-8"))
    ns = [it["n"] for it in data["items"]]
    if len(ns) != len(set(ns)):
        raise ValueError("Schedule item numbers must be unique")
    return data


def soon_window(interval: int) -> tuple[int, int]:
    """(miles, days) before the due point that count as 'soon'. Scales with the interval."""
    if interval <= 5000:
        return 500, 30
    if interval <= 25000:
        return 1000, 45
    if interval <= 30000:
        return 1500, 60
    if interval <= 60000:
        return 2000, 60
    return 3000, 90


def effective_interval(item: dict[str, Any], profile: str) -> int:
    if profile == "severe" and item.get("severe"):
        return int(item["severe"])
    return int(item["normal"])


def first_due(item: dict[str, Any], profile: str) -> int:
    return int(item.get("first") or effective_interval(item, profile))


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    return date(year, month, 28)


@dataclass
class ItemStatus:
    n: int
    id: str
    name: str
    short: str
    kind: str
    zone: str
    profile: str
    interval: int
    status: str
    remaining: int | None          # miles to the due point; negative = over; None when unknowable
    due_at: int | None
    last_odometer: int | None = None
    last_date: str | None = None
    last_action: str | None = None
    due_date: str | None = None
    days_left: int | None = None
    eta: str | None = None         # projected date from pace, only for items with a due point ahead
    months: int | None = None
    history: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


def entries_for(entries: list[dict[str, Any]], n: int, kind: str) -> list[dict[str, Any]]:
    """Log entries that reset item n, oldest first. Entries without an odometer still count by date."""
    resets = RESETS.get(kind, {"changed"})
    out = []
    for e in entries:
        if e.get("deleted"):
            continue
        for it in e.get("items", []):
            if int(it.get("n", -1)) == n and it.get("action", DEFAULT_ACTION.get(kind)) in resets:
                out.append({"id": e.get("id"), "date": e.get("date"), "odometer": e.get("odometer"),
                            "action": it.get("action"), "measure": it.get("measure"),
                            "source": e.get("source"), "edited": bool(e.get("edited"))})
                break
    out.sort(key=lambda h: ((h["odometer"] if h["odometer"] is not None else -1), h["date"] or ""))
    return out


def pace_per_day(entries: list[dict[str, Any]], odometer: float | None, today: date,
                 min_days: int = 90, max_days: int = 730) -> float | None:
    """Miles per day from the newest log entry at least `min_days` old (and no older than max_days)."""
    if odometer is None:
        return None
    best = None
    for e in entries:
        if e.get("deleted") or e.get("odometer") is None or not e.get("date"):
            continue
        try:
            d = date.fromisoformat(e["date"])
        except ValueError:
            continue
        age = (today - d).days
        if min_days <= age <= max_days and (best is None or d > best[0]):
            best = (d, float(e["odometer"]))
    if best is None:
        return None
    days = (today - best[0]).days
    miles = float(odometer) - best[1]
    if days <= 0 or miles < 0:
        return None
    return miles / days


def compute(schedule: dict[str, Any], entries: list[dict[str, Any]], odometer: float | None,
            today: date, profiles: dict[str, str] | None = None,
            months: dict[str, int] | None = None) -> list[ItemStatus]:
    """Status of every item. `odometer` None means the reading is missing (not zero)."""
    profiles = profiles or {}
    months = months or {}
    pace = pace_per_day(entries, odometer, today)
    out: list[ItemStatus] = []
    for item in schedule["items"]:
        n = int(item["n"])
        profile = profiles.get(str(n), "normal")
        if profile == "severe" and not item.get("severe"):
            profile = "normal"
        interval = effective_interval(item, profile)
        hist = entries_for(entries, n, item["kind"])
        last = hist[-1] if hist else None
        mo = months.get(str(n))
        st = ItemStatus(n=n, id=item["id"], name=item["name"], short=item["short"], kind=item["kind"],
                        zone=item.get("zone", ""), profile=profile, interval=interval,
                        status="ok", remaining=None, due_at=None, months=int(mo) if mo else None,
                        history=hist)
        if last:
            st.last_odometer = last["odometer"]
            st.last_date = last["date"]
            st.last_action = last["action"]
            if last["odometer"] is not None:
                st.due_at = int(last["odometer"]) + interval
            if mo and last["date"]:
                dd = _add_months(date.fromisoformat(last["date"]), int(mo))
                st.due_date = dd.isoformat()
                st.days_left = (dd - today).days
        else:
            st.due_at = first_due(item, profile)

        if st.due_at is not None and odometer is not None:
            st.remaining = int(round(st.due_at - float(odometer)))

        win_mi, win_days = soon_window(interval)
        if not last and st.remaining is not None and st.remaining <= 0:
            st.status = "nolog"
            st.remaining = None          # unknowable, never a number
        elif st.remaining is None and st.days_left is None:
            st.status = "nolog" if not last else "ok"
        else:
            over = (st.remaining is not None and st.remaining < 0) or (st.days_left is not None and st.days_left < 0)
            soon = (st.remaining is not None and st.remaining <= win_mi) or (st.days_left is not None and st.days_left <= win_days)
            st.status = "over" if over else ("soon" if soon else "ok")

        if pace and st.remaining is not None and st.remaining > 0:
            st.eta = (today + timedelta(days=round(st.remaining / pace))).isoformat()
        out.append(st)
    return out


def summary(statuses: list[ItemStatus]) -> dict[str, Any]:
    counts = {k: 0 for k in STATUS_RANK}
    for s in statuses:
        counts[s.status] += 1
    ahead = [s for s in statuses if s.remaining is not None and s.status != "over"]
    ahead.sort(key=lambda s: s.remaining)
    nxt = ahead[0] if ahead else None
    return {
        "over": counts["over"], "soon": counts["soon"], "nolog": counts["nolog"], "ok": counts["ok"],
        "overdue_items": [s.short for s in statuses if s.status == "over"],
        "next": None if nxt is None else {"n": nxt.n, "short": nxt.short, "name": nxt.name,
                                          "remaining": nxt.remaining, "eta": nxt.eta},
    }


def poster_columns(schedule: dict[str, Any], upto: int = 300000, step: int = 5000) -> dict[int, dict[str, list[int]]]:
    """What a mileage-from-zero chart would mark at each step: the normal schedule, plus
    severe-only extras. The same chart the printed Maintenance Map draws."""
    cols: dict[int, dict[str, list[int]]] = {}
    for m in range(step, upto + 1, step):
        normal, severe = [], []
        for item in schedule["items"]:
            n = int(item["n"])
            every = int(item["normal"])
            first = int(item.get("first") or every)
            if m == first or (m > first and (m - first) % every == 0):
                normal.append(n)
            elif item.get("severe") and m % int(item["severe"]) == 0:
                severe.append(n)
        cols[m] = {"normal": sorted(normal), "severe": sorted(severe)}
    return cols
