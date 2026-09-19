import type { NetworkDoc, Hub, Provider, Holiday, AuditEvent, RouteResp, OperationalDelay } from "./types";
const BASE = import.meta.env.VITE_API_BASE ?? "/api";
async function req<T>(p: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${p}`, { headers: { "Content-Type": "application/json" }, ...init });
  if (!r.ok) { let d = r.statusText; try { d = (await r.json()).detail ?? d; } catch { /* */ } throw new Error(String(d)); }
  return r.json() as Promise<T>;
}
export const api = {
  network: () => req<NetworkDoc>("/network"),
  hubs: () => req<{ hubs: Hub[] }>("/hubs"),
  providers: () => req<{ providers: Provider[]; generated_at: string }>("/providers"),
  holidays: () => req<{ source: string; upcoming: Holiday[]; count: number }>("/holidays"),
  audit: () => req<{ events: AuditEvent[] }>("/audit"),
  route: (body: { origin: string; destination: string; depart_at?: string }) =>
    req<RouteResp>("/route", { method: "POST", body: JSON.stringify(body) }),
  setDelay: (id: string, body: { minutes: number; reason: string; note?: string }) =>
    req<{ ok: boolean; delay: OperationalDelay }>(`/hubs/${id}/delay`, { method: "POST", body: JSON.stringify(body) }),
  clearDelay: (id: string) => req<{ ok: boolean }>(`/hubs/${id}/delay`, { method: "DELETE" }),
};
