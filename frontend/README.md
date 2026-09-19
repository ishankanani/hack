# DACHSER Live Transit Planner — Frontend

White manager dashboard (React + TypeScript + Vite + MapLibre + lucide icons):
route planning, a live map of all hubs, the restriction-aware ETA breakdown with
**legal waiting shown as its own step**, provider-status panel, hub operational
delays, holidays and an audit trail.

## Run (backend must be on :8000 with DATA_DIR set)
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173  (proxies /api -> :8000)
npm run build      # typecheck + production bundle
```
