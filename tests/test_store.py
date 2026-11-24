"""store.py tests: plain pytest, no Home Assistant needed."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
_SPEC = importlib.util.spec_from_file_location("g_store", ROOT / "custom_components" / "garage" / "store.py")
store = importlib.util.module_from_spec(_SPEC)
sys.modules["g_store"] = store
_SPEC.loader.exec_module(store)

TODAY = date(2026, 6, 1)
ITEMS = set(range(1, 17))


@pytest.fixture
def gs(tmp_path):
    (tmp_path / "share").mkdir()
    cfg = store.StoreConfig(mount_path=str(tmp_path / "share"), folder="example", require_mount=False)
    return store.GarageStore(cfg, ITEMS, today=lambda: TODAY)


def test_refuses_to_write_when_not_mounted(tmp_path):
    (tmp_path / "share").mkdir()
    cfg = store.StoreConfig(mount_path=str(tmp_path / "share"), folder="example")
    gs = store.GarageStore(cfg, ITEMS, today=lambda: TODAY)
    with pytest.raises(store.StorageUnavailable):
        gs.add({"odometer": 1000, "items": [{"n": 1, "action": "changed"}]})
    assert not (tmp_path / "share" / "example" / "log.json").exists()


def test_add_update_delete_roundtrip(gs):
    e = gs.add({"odometer": "12,345", "date": "2026-05-30", "items": [{"n": 1, "action": "changed"}],
                "cost": "$45.10", "by": "self", "notes": "  synthetic   "})
    assert e["odometer"] == 12345 and e["cost"] == 45.1 and e["notes"] == "synthetic" and e["source"] == "app"
    gs.update(e["id"], {"odometer": 12346})
    got = gs.entries()[0]
    assert got["odometer"] == 12346 and got["edited"] is True
    gs.delete(e["id"])
    assert gs.entries() == []
    raw = json.loads((gs.root / "log.json").read_text())
    assert raw["entries"][0]["deleted"] is True            # kept, only marked


def test_snapshot_once_per_day(gs):
    gs.add({"odometer": 1, "items": [{"n": 2, "action": "rotated"}]})
    gs.add({"odometer": 2, "items": [{"n": 2, "action": "rotated"}]})
    snaps = list((gs.root / "backups").glob("log-*.json"))
    assert [p.name for p in snaps] == ["log-2026-06-01.json"]
    assert len(json.loads(snaps[0].read_text())["entries"]) == 1   # taken BEFORE the second write


@pytest.mark.parametrize("bad", [
    {"odometer": 1, "items": []},
    {"odometer": 1, "items": [{"n": 99}]},
    {"odometer": 1, "items": [{"n": 1, "action": "polished"}]},
    {"odometer": "lots", "items": [{"n": 1}]},
    {"odometer": 1, "date": "2027-01-01", "items": [{"n": 1}]},
    {"odometer": 1, "by": "robot", "items": [{"n": 1}]},
])
def test_rejects_bad_input(gs, bad):
    with pytest.raises(store.GarageError):
        gs.add(bad)


def test_missing_odometer_is_none_not_zero(gs):
    e = gs.add({"odometer": "", "items": [{"n": 3, "action": "changed"}]})
    assert e["odometer"] is None


def test_set_profile(gs):
    s = gs.set_profile(1, "severe")
    assert s["profile"]["1"] == "severe"
    with pytest.raises(store.GarageError):
        gs.set_profile(1, "extreme")
