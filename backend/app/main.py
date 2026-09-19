"""
DACHSER Live Transit Planner — API.
Real network (relationen.csv), real holidays (kalender.csv), dynamic restriction
engine, ETA engine, live providers (honest status), manager hub delays, audit.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import data as dataloader
from .eta import compute_journey
from .providers import Providers

DATA_DIR = os.environ.get("DATA_DIR", "")
S = {}


def _audit(kind, detail, source="system"):
    S["audit"].insert(0, {"at": datetime.now(timezone.utc).isoformat(),
                          "type": kind, "detail": detail, "source": source})
    S["audit"] = S["audit"][:200]


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not DATA_DIR or not os.path.isdir(DATA_DIR):
        raise RuntimeError("Set DATA_DIR to the folder containing the DACHSER CSVs.")
    S["network"] = dataloader.load_network(DATA_DIR)
    S["holidays"] = dataloader.load_holidays(DATA_DIR)
    S["transfer"] = dataloader.transfer_stats(DATA_DIR)
    S["providers"] = Providers(S["holidays"])
    S["hub_delays"] = {}
    S["audit"] = []
    _audit("startup", f"Loaded {len(S['network']['nodes'])} hubs, {len(S['holidays'])} holidays, "
                      f"{len(S['transfer'])} transfer proxies")
    yield


app = FastAPI(title="DACHSER Live Transit Planner", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class RouteReq(BaseModel):
    origin: str
    destination: str
    depart_at: Optional[str] = None


class DelayReq(BaseModel):
    minutes: int
    reason: str
    note: Optional[str] = ""


def _now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@app.get("/api/health")
def health():
    return {"status": "ok", "hubs": len(S["network"]["nodes"]), "time": _now_iso()}


@app.get("/api/network")
def network():
    n = S["network"]
    return {"hub_id": n["hub_id"],
            "nodes": list(n["nodes"].values()),
            "edges": list(n["edges"].values())}


@app.get("/api/hubs")
def hubs():
    out = []
    for nid, node in S["network"]["nodes"].items():
        rel = node.get("relation")
        st = S["transfer"].get(rel, {}) if rel else {}
        delay = S["hub_delays"].get(nid)
        out.append({**node,
                    "transfer": st,
                    "operational_delay": delay,
                    "expected_transfer_minutes": (st.get("avg_transfer_minutes", 120) if node["type"] == "branch" else 120) + (delay["minutes"] if delay else 0)})
    return {"hubs": out}


@app.get("/api/providers")
def providers():
    return {"providers": S["providers"].all(), "generated_at": _now_iso()}


@app.get("/api/holidays")
def holidays():
    today = datetime.now(timezone.utc).date().isoformat()
    upcoming = sorted([{"date": d, "name": n} for d, n in S["holidays"].items() if d >= today])[:12]
    return {"source": "kalender.csv (Baden-Württemberg)", "upcoming": upcoming, "count": len(S["holidays"])}


@app.get("/api/weather")
def weather(node: str):
    n = S["network"]["nodes"].get(node)
    if not n:
        raise HTTPException(404, "unknown node")
    return {"node": node, **S["providers"].weather.fetch(n["lat"], n["lon"])}


@app.post("/api/route")
def route(req: RouteReq):
    net = S["network"]
    if req.origin not in net["nodes"] or req.destination not in net["nodes"]:
        raise HTTPException(422, "unknown origin or destination")
    if req.origin == req.destination:
        raise HTTPException(422, "origin equals destination")
    depart = (datetime.fromisoformat(req.depart_at.replace("Z", "+00:00"))
              if req.depart_at else datetime.now(timezone.utc)).astimezone(timezone.utc)

    # option A: via the Heilbronn hub (real scheduled lanes)
    primary = compute_journey(net, S["holidays"], S["transfer"], S["hub_delays"],
                              S["providers"], req.origin, req.destination, depart)
    options = [{**primary, "label": "Via Heilbronn hub", "kind": "scheduled"}]

    # option B: direct estimate (no scheduled lane) — restriction-aware, for comparison
    if len(primary["path"]) == 3:
        na, nb = net["nodes"][req.origin], net["nodes"][req.destination]
        # temporary direct edge is handled by the ETA fallback (haversine)
        direct = _direct_estimate(net, S, req.origin, req.destination, depart)
        options.append({**direct, "label": "Direct estimate (no scheduled lane)", "kind": "estimate"})

    options.sort(key=lambda o: o["eta"])
    # weather along the recommended path (live; honest if unavailable)
    wx = []
    for nid in options[0]["path"]:
        nn = net["nodes"][nid]
        wx.append({"node": nid, "name": nn["name"], **S["providers"].weather.fetch(nn["lat"], nn["lon"])})
    _audit("route_calculated", f"{req.origin} → {req.destination}: recommended ETA {options[0]['eta']}")
    return {"options": options, "recommended": options[0]["id"] if options and options[0].get("id") else 0,
            "weather": wx, "providers": S["providers"].all(), "evaluated_at": _now_iso()}


def _direct_estimate(net, state, origin, dest, depart):
    from .eta import _haversine_km
    from .restrictions import drive_with_restrictions
    from datetime import timedelta
    na, nb = net["nodes"][origin], net["nodes"][dest]
    km = round(_haversine_km((na["lat"], na["lon"]), (nb["lat"], nb["lon"])) * 1.25)
    drive = round(km / 65 * 60)
    cur = depart
    steps = []
    h = 120
    steps.append({"type": "handling", "location": origin, "location_name": na["name"],
                  "start": cur.isoformat(), "end": (cur + timedelta(minutes=h)).isoformat(),
                  "minutes": h, "detail": "Loading & handling (proxy)", "source": "proxy"})
    cur += timedelta(minutes=h)
    leg = drive_with_restrictions(cur, drive, state["holidays"])
    t = cur; driven = 0
    for p in leg["pauses"]:
        before = int((p["start"] - t).total_seconds() // 60)
        if before > 0:
            steps.append({"type": "drive", "location": origin, "location_name": na["name"], "start": t.isoformat(),
                          "end": p["start"].isoformat(), "minutes": before,
                          "detail": f"Direct road {na['name']} → {nb['name']} ({km} km, estimated)", "source": "estimated"})
            driven += before
        steps.append({"type": "legal_wait", "location": origin, "location_name": na["name"], "start": p["start"].isoformat(),
                      "end": p["end"].isoformat(), "minutes": p["minutes"], "detail": p["reason"], "source": "REGULATORY DATA"})
        t = p["end"]
    rest = drive - driven
    if rest > 0:
        steps.append({"type": "drive", "location": origin, "location_name": na["name"], "start": t.isoformat(),
                      "end": leg["arrival"].isoformat(), "minutes": rest,
                      "detail": f"Direct road {na['name']} → {nb['name']} ({km} km, estimated)", "source": "estimated"})
    cur = leg["arrival"]
    total = int((cur - depart).total_seconds() // 60)
    return {"origin": origin, "destination": dest, "path": [origin, dest], "depart_at": depart.isoformat(),
            "eta": cur.isoformat(), "total_minutes": total,
            "components": {"transport": drive, "transfer": h, "hub_delay": 0, "traffic": 0, "legal_wait": leg["waiting_minutes"]},
            "steps": steps, "weather_notes": [],
            "data_sources": {"transport": "estimated (haversine × 1.25)", "legal_wait": "REGULATORY DATA"}}


@app.post("/api/hubs/{node_id}/delay")
def set_delay(node_id: str, req: DelayReq):
    if node_id not in S["network"]["nodes"]:
        raise HTTPException(404, "unknown hub")
    S["hub_delays"][node_id] = {"minutes": req.minutes, "reason": req.reason,
                                "note": req.note, "status": "ACTIVE", "at": _now_iso()}
    _audit("hub_delay_set", f"{S['network']['nodes'][node_id]['name']}: +{req.minutes}m — {req.reason}", "MANAGER INPUT")
    return {"ok": True, "hub": node_id, "delay": S["hub_delays"][node_id]}


@app.delete("/api/hubs/{node_id}/delay")
def clear_delay(node_id: str):
    if S["hub_delays"].pop(node_id, None):
        _audit("hub_delay_resolved", f"{S['network']['nodes'][node_id]['name']}: operational delay resolved", "MANAGER INPUT")
    return {"ok": True}


@app.get("/api/audit")
def audit():
    return {"events": S["audit"]}
