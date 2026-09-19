import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { NetNode } from "../api/types";

const STYLE = "https://tiles.openfreemap.org/styles/liberty";
const HUB = "#1a3682", BRANCH = "#66738c", ROUTE = "#1a3682";

function hasWebGL() { try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch { return false; } }

export function LiveMap({ nodes, path }: { nodes: NetNode[]; path: string[] }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const markers = useRef<maplibregl.Marker[]>([]);
  const [fallback, setFallback] = useState(!hasWebGL());
  const [ready, setReady] = useState(false);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  useEffect(() => {
    if (fallback || !ref.current || map.current) return;
    let m: maplibregl.Map;
    try { m = new maplibregl.Map({ container: ref.current, style: STYLE, center: [10.2, 51.0], zoom: 5.1, attributionControl: { compact: true } }); }
    catch { setFallback(true); return; }
    m.on("error", (e) => { if (String(e?.error?.message ?? "").match(/style|tiles|fetch|network/i)) setFallback(true); });
    m.on("load", () => setReady(true));
    map.current = m;
    return () => { m.remove(); map.current = null; };
  }, [fallback]);

  useEffect(() => {
    const m = map.current; if (!m || !ready) return;
    const line = { type: "FeatureCollection" as const, features: path.length > 1 ? [{ type: "Feature" as const, properties: {}, geometry: { type: "LineString" as const, coordinates: path.map((id) => { const n = byId.get(id)!; return [n.lon, n.lat]; }) } }] : [] };
    const src = m.getSource("route") as maplibregl.GeoJSONSource | undefined;
    if (src) src.setData(line);
    else { m.addSource("route", { type: "geojson", data: line }); m.addLayer({ id: "route-l", type: "line", source: "route", paint: { "line-color": ROUTE, "line-width": 4, "line-opacity": .9 } }); }
    markers.current.forEach((x) => x.remove());
    const onPath = new Set(path);
    markers.current = nodes.map((n) => {
      const el = document.createElement("div");
      const isHub = n.type === "hub", hot = onPath.has(n.id);
      const size = isHub ? 14 : hot ? 11 : 8;
      el.style.cssText = `width:${size}px;height:${size}px;border-radius:${isHub ? "3px" : "50%"};background:${hot ? ROUTE : "#fff"};border:2px solid ${isHub ? HUB : hot ? ROUTE : BRANCH};box-shadow:0 1px 2px rgba(0,0,0,.2)`;
      return new maplibregl.Marker({ element: el }).setLngLat([n.lon, n.lat])
        .setPopup(new maplibregl.Popup({ offset: 12 }).setHTML(`<strong>${n.name}</strong><br/><span style="color:#66738c">${n.type}${n.relation ? " · " + n.relation : ""}</span>`))
        .addTo(m);
    });
    if (path.length > 1) { const b = new maplibregl.LngLatBounds(); path.forEach((id) => { const n = byId.get(id)!; b.extend([n.lon, n.lat]); }); m.fitBounds(b, { padding: 60, maxZoom: 7, duration: 500 }); }
  }, [ready, nodes, path, byId]);

  if (fallback) return <Fallback nodes={nodes} path={path} />;
  return <div className="mapwrap"><div ref={ref} className="maplibre" /><div className="map-attrib">© OpenFreeMap · OpenStreetMap</div></div>;
}

function Fallback({ nodes, path }: { nodes: NetNode[]; path: string[] }) {
  const W = 760, H = 360, P = 30;
  const lons = nodes.map((n) => n.lon), lats = nodes.map((n) => n.lat);
  const lo0 = Math.min(...lons), lo1 = Math.max(...lons), la0 = Math.min(...lats), la1 = Math.max(...lats);
  const X = (lon: number) => P + ((lon - lo0) / (lo1 - lo0 || 1)) * (W - 2 * P);
  const Y = (lat: number) => P + ((la1 - lat) / (la1 - la0 || 1)) * (H - 2 * P);
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const onPath = new Set(path);
  return (
    <div className="mapwrap mapfallback">
      <div className="map-lbl">Basemap offline — schematic coordinates (production: MapLibre + OpenFreeMap)</div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ display: "block", width: "100%" }}>
        {path.length > 1 && <polyline fill="none" stroke={ROUTE} strokeWidth={3} points={path.map((id) => { const n = byId.get(id)!; return `${X(n.lon)},${Y(n.lat)}`; }).join(" ")} />}
        {nodes.map((n) => {
          const x = X(n.lon), y = Y(n.lat), isHub = n.type === "hub", hot = onPath.has(n.id);
          return isHub
            ? <rect key={n.id} x={x - 6} y={y - 6} width={12} height={12} rx={2} fill={HUB} />
            : <circle key={n.id} cx={x} cy={y} r={hot ? 5 : 3.5} fill={hot ? ROUTE : "#fff"} stroke={hot ? ROUTE : BRANCH} strokeWidth={1.8} />;
        })}
        {nodes.filter((n) => n.type === "hub" || onPath.has(n.id)).map((n) => (
          <text key={n.id + "t"} x={X(n.lon) + 8} y={Y(n.lat) + 3} fontSize={10} fontWeight={700} fill="#334">{n.name}</text>
        ))}
      </svg>
    </div>
  );
}
