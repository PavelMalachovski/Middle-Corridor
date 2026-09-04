/**
 * Плавное движение между снимками. Снимок приходит раз в refresh_s секунд,
 * а объекты за это время «доезжают» до новых координат по ease-out, вместо
 * прыжка. Курс интерполируется по короткой дуге.
 */

export interface Pose {
  lon: number;
  lat: number;
  heading: number | null;
}

interface Tween {
  from: Pose;
  to: Pose;
  start: number;
  end: number;
}

const easeOut = (t: number) => 1 - (1 - t) * (1 - t);

/** Разница углов в диапазоне −180..180, чтобы поворот шёл по короткой дуге. */
function angleDelta(from: number, to: number): number {
  return ((((to - from) % 360) + 540) % 360) - 180;
}

export class Interpolator {
  private tweens = new Map<string, Tween>();

  /**
   * Новая цель для объекта. Если объект уже движется, стартуем из его
   * текущей (интерполированной) точки, чтобы не было рывка назад.
   */
  setTarget(id: string, to: Pose, now: number, durationMs: number): void {
    const current = this.pose(id, now) ?? to;
    if (durationMs <= 0 || samePose(current, to)) {
      this.tweens.set(id, { from: to, to, start: now, end: now });
      return;
    }
    this.tweens.set(id, { from: current, to, start: now, end: now + durationMs });
  }

  /** Мгновенно поставить объект (replay-скраб, первое появление). */
  snap(id: string, pose: Pose, now: number): void {
    this.tweens.set(id, { from: pose, to: pose, start: now, end: now });
  }

  remove(id: string): void {
    this.tweens.delete(id);
  }

  has(id: string): boolean {
    return this.tweens.has(id);
  }

  pose(id: string, now: number): Pose | null {
    const tw = this.tweens.get(id);
    if (!tw) return null;
    if (now >= tw.end) return tw.to;
    const t = easeOut((now - tw.start) / (tw.end - tw.start));
    const heading =
      tw.from.heading == null || tw.to.heading == null
        ? tw.to.heading
        : (tw.from.heading + angleDelta(tw.from.heading, tw.to.heading) * t + 360) % 360;
    return {
      lon: tw.from.lon + (tw.to.lon - tw.from.lon) * t,
      lat: tw.from.lat + (tw.to.lat - tw.from.lat) * t,
      heading,
    };
  }

  /** Есть ли ещё незавершённые движения — чтобы не крутить rAF впустую. */
  active(now: number): boolean {
    for (const tw of this.tweens.values()) if (now < tw.end) return true;
    return false;
  }

  ids(): IterableIterator<string> {
    return this.tweens.keys();
  }
}

function samePose(a: Pose, b: Pose): boolean {
  return (
    Math.abs(a.lon - b.lon) < 1e-7 &&
    Math.abs(a.lat - b.lat) < 1e-7 &&
    (a.heading ?? 0) === (b.heading ?? 0)
  );
}
