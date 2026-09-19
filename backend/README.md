# DACHSER Live Transit Planner — Backend

FastAPI service on the **real DACHSER dataset**: the hub-and-spoke network from
`relationen.csv` (Heilbronn central hub + 30 branches), the real German
(Baden-Württemberg) holiday calendar from `kalender.csv`, and hub transfer-time
proxies derived from `disposition.csv`. It computes explainable ETAs with a
**dynamic legal-restriction engine** (real Sunday/holiday waiting time, not a
flat +24h) and integrates live providers with **honest status**.

## Run
```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DATA_DIR=/path/to/the/7/csvs                    # REQUIRED (the DACHSER files)
uvicorn app.main:app --port 8000                       # docs at /docs
pytest -q                                              # 6 tests, all green
```
> Python 3.11–3.13 recommended. On 3.14 first run `pip install --upgrade pydantic`.

## Endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/network` | hubs + edges (map) |
| GET | `/api/hubs` | hubs with transfer proxy + operational delay |
| POST | `/api/route` | plan a route → options + ETA breakdown + weather |
| GET | `/api/providers` | provider statuses (LIVE/STALE/ERROR/NOT_CONFIGURED) |
| GET | `/api/holidays` | upcoming holidays (kalender.csv) |
| GET | `/api/weather?node=` | live weather for a hub |
| POST/DELETE | `/api/hubs/{id}/delay` | set / resolve a manager operational delay |
| GET | `/api/audit` | audit trail |

## Live providers — honest status
| Provider | Source | Live without a key? |
|---|---|---|
| Weather | Open-Meteo | ✅ yes (needs internet) |
| Holidays / restrictions | kalender.csv + German rules | ✅ yes |
| Routing geometry | OSRM public | ✅ yes (needs internet) |
| **Traffic / incidents** | TomTom / HERE | ⚠️ **NOT_CONFIGURED** until `TOMTOM_API_KEY` / `HERE_API_KEY` |

Nothing is ever shown as LIVE unless a real fetch returned current data. In an
offline sandbox, weather/routing show ERROR — which is the honest behaviour; on a
machine with internet they go LIVE.

## Honest notes
- **Transfer times are a derived proxy** (the CSVs carry no measured handling
  timestamps) — labelled `HISTORICAL (derived proxy)` everywhere.
- The network is the real 30-relation **hub-and-spoke** (branch→Heilbronn→branch);
  the "direct estimate" option is clearly labelled *estimate, no scheduled lane*.
