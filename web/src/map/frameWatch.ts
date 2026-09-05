/**
 * Наблюдение за временем кадра — решение «устройство не тянет».
 *
 * Средний кадр (экспоненциальное среднее) дольше порога — «медленный».
 * Сигнал даётся один раз, когда медленные кадры идут подряд не меньше
 * minFrames И не меньше windowMs по часам. По часам, а не по числу кадров:
 * на слабом устройстве (или в CI на SwiftShader) кадров в секунду единицы,
 * и счётчик до сотни кадров занял бы минуту с замёрзшей страницей; минимум
 * кадров отсекает одиночный тяжёлый кадр (загрузка стиля, первая отрисовка
 * рельефа).
 */

export interface FrameWatchOptions {
  slowMs?: number; // средний кадр дольше — медленный
  minFrames?: number; // медленных кадров подряд не меньше…
  windowMs?: number; // …и не меньше времени подряд
}

const PAUSE_CAP_MS = 250; // пауза вкладки (rAF стоит) — не «медленный кадр»

export class FrameWatch {
  private readonly slowMs: number;
  private readonly minFrames: number;
  private readonly windowMs: number;
  private last = 0;
  private avg = 16;
  private slowFrames = 0;
  private slowSince = 0;
  private reported = false;

  constructor({ slowMs = 55, minFrames = 10, windowMs = 3000 }: FrameWatchOptions = {}) {
    this.slowMs = slowMs;
    this.minFrames = minFrames;
    this.windowMs = windowMs;
  }

  /** Среднее время кадра, мс — для масштабирования шага частиц. */
  get frameMs(): number {
    return this.avg;
  }

  /** Сброс замеров (новый GL-контекст, смена стиля); использованный сигнал не возвращается. */
  reset(): void {
    this.last = 0;
    this.avg = 16;
    this.slowFrames = 0;
    this.slowSince = 0;
  }

  /** Вызывать на каждом кадре. true — ровно один раз, когда пора деградировать. */
  tick(now: number): boolean {
    if (this.last) {
      const dt = Math.min(now - this.last, PAUSE_CAP_MS);
      this.avg = this.avg * 0.9 + dt * 0.1;
      if (this.avg > this.slowMs) {
        this.slowFrames += 1;
        if (!this.slowSince) this.slowSince = now;
      } else {
        this.slowFrames = 0;
        this.slowSince = 0;
      }
    }
    this.last = now;
    if (this.reported || this.slowFrames < this.minFrames) return false;
    if (now - this.slowSince < this.windowMs) return false;
    this.reported = true;
    return true;
  }
}
