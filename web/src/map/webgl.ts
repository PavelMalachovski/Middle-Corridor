/**
 * Программный ли рендер WebGL. SwiftShader (Chrome без GPU), llvmpipe/softpipe
 * (Mesa на Linux без драйвера), «Software» в названии — объёмный рельеф на
 * них рисует кадр секундами, а частицы ветра сразу уходят в стрелки.
 * Определение — по WEBGL_debug_renderer_info; без него считаем, что GPU есть.
 */

const SOFTWARE_RENDERERS = /swiftshader|llvmpipe|softpipe|software|mesa offscreen/i;
const FORCE_KEY = "mc-force-gpu"; // e2e на SwiftShader: «считай, что GPU есть»

export function isSoftwareRenderer(renderer: string | null | undefined): boolean {
  return !!renderer && SOFTWARE_RENDERERS.test(renderer);
}

/** Название рендерера из временного контекста WebGL 2, null — не узнать. */
export function detectRenderer(): string | null {
  try {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl2");
    if (!gl) return null;
    const info = gl.getExtension("WEBGL_debug_renderer_info");
    const renderer = info ? (gl.getParameter(info.UNMASKED_RENDERER_WEBGL) as string) : null;
    gl.getExtension("WEBGL_lose_context")?.loseContext();
    return renderer;
  } catch {
    return null;
  }
}

/** Программный рендер на этой странице (с учётом принудительного override для тестов). */
export function softwareGl(): boolean {
  try {
    if (localStorage.getItem(FORCE_KEY) === "1") return false;
  } catch {
    /* приватный режим */
  }
  return isSoftwareRenderer(detectRenderer());
}
