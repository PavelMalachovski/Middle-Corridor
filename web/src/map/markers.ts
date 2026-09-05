import type { NodeStatus, Shipment, VesselStatus } from "../api";
import { LEVEL_ICON, levelOf } from "../format";
import { nodeName, t } from "../i18n";

/** Меняет наши классы, не трогая maplibregl-marker* — иначе маркер выпадает из абсолютного позиционирования. */
export function setOwnClasses(el: HTMLElement, classes: string[]): void {
  for (const cls of Array.from(el.classList)) {
    if (!cls.startsWith("maplibregl-")) el.classList.remove(cls);
  }
  el.classList.add(...classes.filter(Boolean));
}

// --- узлы ------------------------------------------------------------------------

export function nodeMarkerElement(): HTMLDivElement {
  const el = document.createElement("div");
  el.className = "node-marker";
  el.innerHTML =
    '<div class="node-marker__dot"><i></i></div>' +
    '<div class="node-marker__label"><b></b><span></span></div>';
  return el;
}

export function renderNodeMarker(el: HTMLDivElement, node: NodeStatus): void {
  const level = levelOf(node);
  setOwnClasses(el, ["node-marker", `node-marker--${node.kind}`, `level-${level}`]);
  const name = nodeName(node);
  el.title = name;
  el.querySelector("b")!.textContent = name;
  const sub = el.querySelector("span")!;
  if (node.is_weather_tracked && node.wind_speed != null) {
    const icon = node.alert_level ? `${LEVEL_ICON[node.alert_level]} ` : "";
    sub.textContent = `${icon}${node.wind_speed.toFixed(0)} ${t("common.ms")}`;
  } else {
    sub.textContent = "";
  }
}

// --- грузы -----------------------------------------------------------------------

export function shipmentMarkerElement(): HTMLDivElement {
  const el = document.createElement("div");
  el.className = "ship-marker";
  el.innerHTML = '<div class="ship-marker__dot"></div><div class="ship-marker__label"></div>';
  return el;
}

export function renderShipmentMarker(
  el: HTMLDivElement,
  s: Shipment,
  selected: boolean,
  followed: boolean,
  title: string = s.last_event,
): void {
  setOwnClasses(el, [
    "ship-marker",
    `ship-marker--${s.state}`,
    `ship-marker--${s.position.source}`,
    selected ? "is-selected" : "",
    followed ? "is-followed" : "",
    s.delay_hours > 0 ? "is-delayed" : "",
  ]);
  el.title = `${s.ref}: ${title}`;
  el.querySelector(".ship-marker__label")!.textContent = s.ref;
}

// --- паромы ----------------------------------------------------------------------

// Силуэт носом на север; поворот по курсу — CSS transform на внутреннем svg
const SHIP_SVG =
  '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">' +
  '<path d="M12 1.5 L18 9.5 V22.5 H6 V9.5 Z" fill="currentColor" stroke="rgba(0,0,0,.55)" stroke-width="1.2" stroke-linejoin="round"/>' +
  "</svg>";

export function vesselMarkerElement(): HTMLDivElement {
  const el = document.createElement("div");
  el.className = "vessel-marker";
  el.innerHTML = `<div class="vessel-marker__icon">${SHIP_SVG}</div><div class="vessel-marker__label"></div>`;
  return el;
}

export function renderVesselMarker(
  el: HTMLDivElement,
  v: VesselStatus,
  heading: number | null,
  route: string | null = v.route ?? null,
): void {
  setOwnClasses(el, ["vessel-marker", v.sog != null && v.sog > 0.5 ? "is-moving" : "is-moored"]);
  el.title = `${v.name}${route ? ` · ${route}` : ""}`;
  (el.querySelector(".vessel-marker__icon") as HTMLElement).style.transform =
    `rotate(${heading ?? v.cog ?? 0}deg)`;
  el.querySelector(".vessel-marker__label")!.textContent = v.name;
}
