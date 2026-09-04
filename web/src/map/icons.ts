// Иконки для symbol-слоёв рисуем на canvas: без внешних ассетов и без
// зависимости от glyph-сервера (подписи узлов и грузов — HTML-маркеры).

export interface IconImage {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}

function canvasImage(size: number, draw: (ctx: CanvasRenderingContext2D) => void): IconImage {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  draw(ctx);
  const image = ctx.getImageData(0, 0, size, size);
  return { width: size, height: size, data: new Uint8ClampedArray(image.data.buffer) };
}

/** Стрелка «вверх» (север); SDF — цвет задаётся в слое через icon-color. */
export function windArrow(size = 32): IconImage {
  return canvasImage(size, (ctx) => {
    const c = size / 2;
    ctx.fillStyle = "#fff";
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = size * 0.11;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(c, size * 0.88);
    ctx.lineTo(c, size * 0.2);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(c, size * 0.08);
    ctx.lineTo(c + size * 0.24, size * 0.4);
    ctx.lineTo(c - size * 0.24, size * 0.4);
    ctx.closePath();
    ctx.fill();
  });
}

/** Силуэт судна носом на север. */
export function shipIcon(size = 36): IconImage {
  return canvasImage(size, (ctx) => {
    const c = size / 2;
    ctx.fillStyle = "#fff";
    ctx.beginPath();
    ctx.moveTo(c, size * 0.06);
    ctx.lineTo(c + size * 0.28, size * 0.42);
    ctx.lineTo(c + size * 0.28, size * 0.9);
    ctx.lineTo(c - size * 0.28, size * 0.9);
    ctx.lineTo(c - size * 0.28, size * 0.42);
    ctx.closePath();
    ctx.fill();
  });
}
