import { useEffect, useMemo, useState } from "react";
import {
  MapPin, Navigation, Clock, Zap, Building2, CloudSun, CalendarDays, History,
  Package, Ban, Factory, Gauge, RefreshCw, AlertTriangle, Plus, X,
} from "lucide-react";
import { DACHSER_LOGO } from "./logo";
import { api } from "./api/client";
import type { NetworkDoc, Hub, Provider, Holiday, AuditEvent, RouteResp, RouteOption } from "./api/types";
import { LiveMap } from "./components/LiveMap";
import { JourneyTimeline } from "./components/JourneyTimeline";

function hm(m: number) { const h = Math.floor(m / 60), mm = m % 60; return h ? `${h}h ${mm ? mm + "m" : ""}`.trim() : `${mm}m`; }
function dt(iso: string) { return new Date(iso).toLocaleString("en-GB", { weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Berlin", hour12: false }); }
function statusClass(s: string) { return "pill st-" + s.toLowerCase(); }

export default function App() {
  const [net, setNet] = useState<NetworkDoc | null>(null);
  const [hubs, setHubs] = useState<Hub[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [origin, setOrigin] = useState("R01");
  const [dest, setDest] = useState("R11");
  const [depart, setDepart] = useState("2026-09-19T18:00:00Z");
  const [resp, setResp] = useState<RouteResp | null>(null);
  const [sel, setSel] = useState(0);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [delayFor, setDelayFor] = useState<Hub | null>(null);

  const nodes = net?.nodes ?? [];
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const option: RouteOption | undefined = resp?.options[sel];

  function loadStatics() {
    api.hubs().then((r) => setHubs(r.hubs)).catch(() => {});
    api.providers().then((r) => setProviders(r.providers)).catch(() => {});
    api.audit().then((r) => setAudit(r.events)).catch(() => {});
  }
  useEffect(() => {
    api.network().then(setNet).catch((e) => setErr(String(e)));
    api.holidays().then((r) => setHolidays(r.upcoming)).catch(() => {});
    loadStatics();
    const t = window.setInterval(() => { api.providers().then((r) => setProviders(r.providers)).catch(() => {}); api.audit().then((r) => setAudit(r.events)).catch(() => {}); }, 15000);
    return () => window.clearInterval(t);
  }, []);

  async function calculate() {
    setLoading(true); setErr(null);
    try { const r = await api.route({ origin, destination: dest, depart_at: depart }); setResp(r); setSel(0); setProviders(r.providers); loadStatics(); }
    catch (e) { setErr(String(e)); setResp(null); }
    finally { setLoading(false); }
  }

  return (
    <>
      <header className="top">
        <img className="top__logo" src={DACHSER_LOGO} alt="DACHSER" />
        <div><div className="top__title">Live Transit Planner</div><div className="top__sub">real network · dynamic restrictions · live providers</div></div>
        <div className="top__spacer" />
        {providers.map((p) => (
          <span key={p.key} className={statusClass(p.status)} title={`${p.name}${p.last_success ? " · last ok " + dt(p.last_success) : ""}${p.error ? " · " + p.error : ""}`}>
            <span className="dot" /> {p.key}: {p.status.replace("_", " ")}
          </span>
        ))}
        <button className="btn btn--ghost btn--sm" onClick={loadStatics}><RefreshCw size={14} /> Refresh</button>
      </header>

      <div className="wrap">
        {err && <div className="notice notice--warn"><AlertTriangle size={15} /> {err}</div>}

        {/* route search */}
        <div className="card">
          <div className="search">
            <div className="fld"><label><MapPin size={12} /> Origin</label>
              <select value={origin} onChange={(e) => setOrigin(e.target.value)}>{nodes.map((n) => <option key={n.id} value={n.id}>{n.name} ({n.id})</option>)}</select></div>
            <div className="fld"><label><Navigation size={12} /> Destination</label>
              <select value={dest} onChange={(e) => setDest(e.target.value)}>{nodes.map((n) => <option key={n.id} value={n.id}>{n.name} ({n.id})</option>)}</select></div>
            <div className="fld"><label><Clock size={12} /> Departure (ISO, UTC)</label>
              <input value={depart} onChange={(e) => setDepart(e.target.value)} /></div>
            <div className="fld"><button className="btn" onClick={calculate} disabled={loading}>{loading ? "Calculating…" : <><Zap size={15} /> Plan route</>}</button></div>
          </div>
        </div>

        <div className="grid">
          {/* LEFT */}
          <div className="col">
            <div className="card">
              <div className="card__h"><div><h2><MapPin size={15} className="h-ic" /> Network &amp; route</h2><div className="sub">Heilbronn hub + 30 branches · selected route highlighted</div></div></div>
              <LiveMap nodes={nodes} path={option?.path ?? []} />
            </div>

            {resp && (
              <div className="card">
                <div className="card__h"><div><h2><Navigation size={15} className="h-ic" /> Route options</h2><div className="sub">Restriction-aware — a faster leg can lose to a driving ban</div></div></div>
                <div className="opts">
                  {resp.options.map((o, i) => (
                    <div key={i} className="opt" aria-selected={i === sel} onClick={() => setSel(i)}>
                      <div className="opt__top"><span className="opt__label">{o.label}{i === 0 && <span className="tag--rec" style={{ marginLeft: 8 }}>Recommended</span>}</span><span className="opt__eta">{dt(o.eta)}</span></div>
                      <div className="opt__path">{o.path.map((p) => byId.get(p)?.name ?? p).join(" → ")}</div>
                      <div className="opt__badges">
                        <span className="mini"><Clock size={12} /> {hm(o.total_minutes)}</span>
                        {o.components.legal_wait > 0 && <span className="mini mini--legal"><Ban size={12} /> {hm(o.components.legal_wait)} legal wait</span>}
                        <span className="mini"><Package size={12} /> {hm(o.components.transfer)} handling</span>
                        {o.components.hub_delay > 0 && <span className="mini"><Factory size={12} /> {hm(o.components.hub_delay)} delay</span>}
                        {o.kind === "estimate" && <span className="mini mini--est">estimate</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {option && (
              <div className="card">
                <div className="card__h"><div><h2><History size={15} className="h-ic" /> ETA breakdown · {dt(option.eta)}</h2><div className="sub">Every component explained — legal waiting is a visible step</div></div></div>
                <div className="summary">
                  {([["transport", "Transport", false], ["transfer", "Hub handling", false], ["hub_delay", "Hub delays", false], ["traffic", "Traffic", false], ["legal_wait", "Legal wait", true]] as const).map(([k, l, red]) => (
                    <div className="sumtile" key={k}><div className="l">{l}</div><div className={`v ${red ? "legal" : ""}`}>{hm(option.components[k])}</div></div>
                  ))}
                  <div className="sumtile" style={{ background: "var(--blue-050)", borderColor: "transparent" }}><div className="l">Total transit</div><div className="v" style={{ color: "var(--blue)" }}>{hm(option.total_minutes)}</div></div>
                </div>
                <JourneyTimeline steps={option.steps} />
              </div>
            )}
          </div>

          {/* RIGHT */}
          <div className="col">
            <div className="card">
              <div className="card__h"><div><h2><Gauge size={15} className="h-ic" /> Data sources</h2><div className="sub">LIVE only when a real fetch succeeded</div></div></div>
              <div className="plist">
                {providers.map((p) => (
                  <div className="prow" key={p.key}>
                    <div><div className="nm">{p.name}</div><div className="meta">{p.kind} · {p.last_success ? "last ok " + dt(p.last_success) : p.error ? p.error.slice(0, 40) : "—"}</div></div>
                    <span className={statusClass(p.status)}><span className="dot" /> {p.status.replace("_", " ")}</span>
                  </div>
                ))}
              </div>
            </div>

            {resp?.weather && resp.weather.length > 0 && (
              <div className="card">
                <div className="card__h"><div><h2><CloudSun size={15} className="h-ic" /> Weather along route</h2></div></div>
                <div className="plist">
                  {resp.weather.map((w, i) => (
                    <div className="prow" key={i}>
                      <div className="nm">{w.name}</div>
                      {w.observed ? <span className="meta">{w.temp_c}°C · wind {w.wind_kmh} km/h</span>
                        : <span className={statusClass(w.status)}><span className="dot" /> {w.status.replace("_", " ")}</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="card">
              <div className="card__h"><div><h2><CalendarDays size={15} className="h-ic" /> Upcoming holidays</h2><div className="sub">kalender.csv (Baden-Württemberg)</div></div></div>
              <div style={{ padding: "8px 16px 14px" }}>
                {holidays.length === 0 && <div className="empty">None loaded.</div>}
                {holidays.map((h) => <div className="hol" key={h.date}><span>{h.name}</span><span className="d">{h.date}</span></div>)}
              </div>
            </div>

            <div className="card">
              <div className="card__h"><div><h2><History size={15} className="h-ic" /> Audit trail</h2><div className="sub">every change is traceable</div></div></div>
              <div className="audit">
                {audit.length === 0 && <div className="empty">No events yet.</div>}
                {audit.map((a, i) => (
                  <div className="arow" key={i}><span className="tm">{dt(a.at)}</span><div><span className="ty">{a.type}</span><div>{a.detail}</div></div></div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* hubs table */}
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card__h"><div><h2><Building2 size={15} className="h-ic" /> Hubs &amp; operational status</h2><div className="sub">Transfer time is a historical proxy from disposition.csv · managers set live operational delays</div></div></div>
          <div style={{ overflow: "auto" }}>
            <table className="htbl">
              <thead><tr><th>Hub</th><th>Type</th><th>Avg transfer</th><th>Spillover</th><th>Samples</th><th>Operational delay</th><th></th></tr></thead>
              <tbody>
                {hubs.map((h) => {
                  const st = "avg_transfer_minutes" in h.transfer ? h.transfer : null;
                  return (
                    <tr key={h.id}>
                      <td><b>{h.name}</b> <span style={{ color: "var(--faint)", fontSize: 11 }}>{h.id}</span></td>
                      <td style={{ color: "var(--muted)" }}>{h.type}</td>
                      <td className="num">{st ? hm(st.avg_transfer_minutes) : "120m"}</td>
                      <td className="num">{st ? (st.spillover_rate * 100).toFixed(0) + "%" : "—"}</td>
                      <td className="num" style={{ color: "var(--muted)" }}>{st ? st.samples.toLocaleString() : "—"}</td>
                      <td>{h.operational_delay
                        ? <span className="chip chip--delay"><Factory size={11} /> +{h.operational_delay.minutes}m · {h.operational_delay.reason}</span>
                        : <span style={{ color: "var(--faint)", fontSize: 12 }}>none</span>}</td>
                      <td style={{ textAlign: "right" }}>
                        {h.operational_delay
                          ? <button className="delaybtn" onClick={() => api.clearDelay(h.id).then(loadStatics)}><X size={12} /> resolve</button>
                          : <button className="delaybtn" onClick={() => setDelayFor(h)}><Plus size={12} /> add delay</button>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {delayFor && <DelayModal hub={delayFor} onClose={() => setDelayFor(null)} onSaved={() => { setDelayFor(null); loadStatics(); if (resp) calculate(); }} />}
    </>
  );
}

function DelayModal({ hub, onClose, onSaved }: { hub: Hub; onClose: () => void; onSaved: () => void }) {
  const [minutes, setMinutes] = useState("60");
  const [reason, setReason] = useState("High shipment volume");
  const [note, setNote] = useState("");
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3><Factory size={16} style={{ verticalAlign: "-3px" }} /> Operational delay · {hub.name}</h3>
        <div className="fld"><label>Additional minutes</label><input className="num" value={minutes} onChange={(e) => setMinutes(e.target.value)} /></div>
        <div className="fld"><label>Reason</label>
          <select value={reason} onChange={(e) => setReason(e.target.value)}>
            {["High shipment volume", "Loading delay", "Unloading delay", "Sorting delay", "Equipment failure", "Staff shortage", "IT/system problem", "Vehicle availability", "Capacity problem", "Other"].map((r) => <option key={r}>{r}</option>)}
          </select></div>
        <div className="fld"><label>Note</label><input value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Evening volume significantly above normal" /></div>
        <div className="row">
          <button className="btn btn--ghost btn--sm" onClick={onClose}>Cancel</button>
          <button className="btn btn--sm" onClick={() => api.setDelay(hub.id, { minutes: Number(minutes), reason, note }).then(onSaved)}>Save delay</button>
        </div>
      </div>
    </div>
  );
}
