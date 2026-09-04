// Типы ответа /api/v1 — зеркало pydantic-моделей app/services/map_snapshot.py

export type AlertLevel = "watch" | "warning" | "critical";
export type NodeKind = "port" | "rail" | "border";
export type TransportMode = "rail" | "sea";
export type ShipmentState = "planned" | "in_transit" | "waiting" | "delivered";
export type CheckpointState = "done" | "current" | "planned";
export type PositionSource = "event" | "ais" | "projection";

export interface NodeStatus {
  code: string;
  name: string;
  country: string;
  leg: string;
  kind: NodeKind;
  lat: number;
  lon: number;
  is_weather_tracked: boolean;
  alert_level: AlertLevel | null;
  alert_message: string | null;
  wind_speed: number | null;
  wind_gust: number | null;
  wind_dir: number | null;
  weather_ts: string | null;
}

export interface VesselStatus {
  name: string;
  operator: string | null;
  mmsi: number | null;
  lat: number | null;
  lon: number | null;
  sog: number | null;
  cog: number | null;
  ts: string | null;
  has_recent_data: boolean;
  route: string | null;
  phase: string | null;
}

export interface Checkpoint {
  code: string;
  name: string;
  lat: number;
  lon: number;
  planned_at: string;
  actual_at: string | null;
  state: CheckpointState;
}

export interface ShipmentPosition {
  lat: number;
  lon: number;
  heading: number | null;
  confirmed: boolean;
  source: PositionSource;
  on_vessel: string | null;
  mode: TransportMode | null;
  from_code: string;
  to_code: string | null;
  leg_progress: number;
}

export interface Shipment {
  ref: string;
  client: string;
  cargo: string;
  origin: string;
  destination: string;
  state: ShipmentState;
  hold_reason: string | null;
  delay_hours: number;
  last_event: string;
  last_event_at: string | null;
  eta: string | null;
  position: ShipmentPosition;
  progress: number;
  checkpoints: Checkpoint[];
  track: [number, number][]; // [lon, lat]
}

export interface RouteSegment {
  from_code: string;
  to_code: string;
  mode: TransportMode;
  coordinates: [number, number][];
}

export interface NewsSummary {
  id: number;
  source: string;
  title: string;
  summary: string | null;
  url: string;
  published_at: string | null;
}

export interface ReportStatus {
  report_type: string;
  port_name: string | null;
  payload: Record<string, unknown>;
  note: string | null;
  ts: string;
}

export interface Thresholds {
  watch_wind: number;
  warning_wind: number;
  warning_gust: number;
  critical_wind: number;
  critical_gust: number;
}

export interface Snapshot {
  generated_at: string;
  mock: boolean;
  nodes: NodeStatus[];
  vessels: VesselStatus[];
  shipments: Shipment[];
  segments: RouteSegment[];
  news: NewsSummary[];
  reports: ReportStatus[];
  thresholds: Thresholds;
}

export interface WindPoint {
  lat: number;
  lon: number;
  speed: number;
  gust: number;
  dir: number; // откуда дует
}

export interface WindField {
  ts: string;
  lat_min: number;
  lon_min: number;
  lat_max: number;
  lon_max: number;
  step_deg: number;
  points: WindPoint[];
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${url}: HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export const fetchSnapshot = () => getJson<Snapshot>("/api/v1/snapshot");

/** null — поле ветра недоступно (в проде без источника отдаёт 404). */
export async function fetchWind(): Promise<WindField | null> {
  const response = await fetch("/api/v1/wind", { cache: "no-store" });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`/api/v1/wind: HTTP ${response.status}`);
  return (await response.json()) as WindField;
}
