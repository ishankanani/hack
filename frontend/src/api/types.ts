export interface NetNode { id: string; name: string; type: "hub" | "branch"; lat: number; lon: number; relation?: string; source: string; }
export interface Edge { id: string; from: string; to: string; km: number; base_drive_minutes: number; mode: string; cost_eur: number; capacity_ldm: number; source: string; }
export interface NetworkDoc { hub_id: string; nodes: NetNode[]; edges: Edge[]; }

export interface TransferStat { samples: number; spillover_rate: number; avg_utilisation: number; avg_transfer_minutes: number; median_transfer_minutes: number; range_minutes: number[]; source: string; }
export interface OperationalDelay { minutes: number; reason: string; note?: string; status: string; at: string; }
export interface Hub extends NetNode { transfer: TransferStat | Record<string, never>; operational_delay: OperationalDelay | null; expected_transfer_minutes: number; }

export interface JourneyStep { type: "handling" | "drive" | "legal_wait" | "hub_delay"; location: string; location_name: string; start: string; end: string; minutes: number; detail: string; source: string; }
export interface Components { transport: number; transfer: number; hub_delay: number; traffic: number; legal_wait: number; }
export interface RouteOption { origin: string; destination: string; path: string[]; depart_at: string; eta: string; total_minutes: number; components: Components; steps: JourneyStep[]; data_sources: Record<string, string>; label: string; kind: string; }
export interface WeatherObs { node: string; name?: string; observed?: boolean; temp_c?: number; wind_kmh?: number; precipitation?: number; status: string; error?: string; }
export interface Provider { key: string; name: string; status: string; configured: boolean; kind: string; last_success: string | null; last_attempt: string | null; data_timestamp: string | null; error: string | null; }
export interface RouteResp { options: RouteOption[]; recommended: number; weather: WeatherObs[]; providers: Provider[]; evaluated_at: string; }
export interface Holiday { date: string; name: string; }
export interface AuditEvent { at: string; type: string; detail: string; source: string; }
