export type LonLat = [number, number];

const R = 6371;

export function haversineKm(a: LonLat, b: LonLat): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(b[1] - a[1]);
  const dLon = toRad(b[0] - a[0]);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a[1])) * Math.cos(toRad(b[1])) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

/** Делит ломаную на пройденную и оставшуюся части по доле длины. */
export function splitTrack(track: LonLat[], fraction: number): { done: LonLat[]; rest: LonLat[] } {
  if (track.length < 2) return { done: track, rest: [] };
  const total = track.slice(1).reduce((acc, p, i) => acc + haversineKm(track[i], p), 0);
  const target = Math.min(Math.max(fraction, 0), 1) * total;
  const done: LonLat[] = [track[0]];
  let walked = 0;
  for (let i = 0; i < track.length - 1; i++) {
    const seg = haversineKm(track[i], track[i + 1]);
    if (walked + seg >= target) {
      const t = seg > 0 ? (target - walked) / seg : 0;
      const split: LonLat = [
        track[i][0] + (track[i + 1][0] - track[i][0]) * t,
        track[i][1] + (track[i + 1][1] - track[i][1]) * t,
      ];
      done.push(split);
      return { done, rest: [split, ...track.slice(i + 1)] };
    }
    walked += seg;
    done.push(track[i + 1]);
  }
  return { done, rest: [] };
}
