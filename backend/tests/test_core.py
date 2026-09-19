import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATA_DIR", "/mnt/user-data/uploads")
from app.main import app
from app.restrictions import drive_with_restrictions

BERLIN = ZoneInfo("Europe/Berlin")


def test_restriction_sunday_waiting_is_dynamic():
    dep = datetime(2026, 9, 19, 20, 0, tzinfo=BERLIN).astimezone(timezone.utc)  # Saturday
    r = drive_with_restrictions(dep, 360, {})
    assert r["waiting_minutes"] == 22 * 60          # not a flat +24h
    assert r["arrival"].astimezone(BERLIN).strftime("%a %H:%M") == "Mon 00:00"


def test_restriction_holiday_waiting():
    hol = {"2026-10-05": "Test Holiday"}             # a Monday
    dep = datetime(2026, 10, 5, 6, 0, tzinfo=BERLIN).astimezone(timezone.utc)
    r = drive_with_restrictions(dep, 180, hol)
    assert r["waiting_minutes"] == 16 * 60           # 06:00 -> 22:00


def test_no_restriction_on_weekday():
    dep = datetime(2026, 9, 22, 8, 0, tzinfo=BERLIN).astimezone(timezone.utc)  # Tuesday
    r = drive_with_restrictions(dep, 300, {})
    assert r["waiting_minutes"] == 0


def test_network_is_real_and_complete():
    with TestClient(app) as c:
        net = c.get("/api/network").json()
        assert net["hub_id"] == "HN"
        assert len(net["nodes"]) == 31              # HN + 30 branches
        names = {n["name"] for n in net["nodes"]}
        assert {"Hamburg", "München", "Münster", "Heilbronn"} <= names


def test_route_includes_legal_wait_and_hub_delay():
    with TestClient(app) as c:
        c.post("/api/hubs/HN/delay", json={"minutes": 80, "reason": "High shipment volume"})
        r = c.post("/api/route", json={"origin": "R01", "destination": "R11",
                                       "depart_at": "2026-09-19T18:00:00Z"}).json()
        via = next(o for o in r["options"] if o["label"].startswith("Via"))
        assert any(s["type"] == "legal_wait" for s in via["steps"])
        assert any(s["type"] == "hub_delay" and s["minutes"] == 80 for s in via["steps"])


def test_providers_are_honest():
    with TestClient(app) as c:
        ps = {p["key"]: p["status"] for p in c.get("/api/providers").json()["providers"]}
        assert ps["traffic"] == "NOT_CONFIGURED"     # no key -> never fake LIVE
        assert ps["holidays"] == "LIVE"              # provided regulatory data
        assert ps["weather"] in ("LIVE", "ERROR", "STALE")
