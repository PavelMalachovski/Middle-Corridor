import type { CustomLayerInterface, CustomRenderMethodInput, Map as MLMap } from "maplibre-gl";
import type { WindField } from "../api";
import { FrameWatch } from "./frameWatch";
import { buildWindGrid, colorRamp, type WindGrid } from "./windGrid";

/**
 * Живой ветер частицами — собственный WebGL-слой поверх MapLibre по мотивам
 * классического webgl-wind (Mapbox, Владимир Агафонкин).
 *
 * Как устроено:
 * - поле ветра лежит в маленькой текстуре (u, v в м/с, нормированные);
 * - положения частиц — в RGBA8-текстуре N×N (16 бит на координату), каждый
 *   кадр фрагментный шейдер сдвигает их по полю и случайно «перерождает»;
 * - следы — экранный буфер: прошлый кадр рисуется с затуханием, поверх —
 *   точки частиц; при движении камеры прошлый кадр сбрасывается, иначе следы
 *   бы «размазались» вместе с картой;
 * - проекция — через прелюдию MapLibre (`projectTile`): координаты частицы
 *   переводятся в меркатор 0..1, и слой одинаково работает на глобусе и в
 *   плоской проекции; обратную сторону планеты отсекает сама прелюдия.
 *
 * Слой не трогает состояние MapLibre: чужой framebuffer и viewport
 * восстанавливаются, а painter после нас сбрасывает кэш GL-состояния сам.
 */

type GL = WebGL2RenderingContext;

export interface WindParticleOptions {
  count: number; // число частиц (округляется до квадрата)
  speedFactor: number; // градусов за кадр на 1 м/с при зуме 4.5
  fadeOpacity: number; // сколько прошлого кадра остаётся: длина следа
  dropRate: number; // доля частиц, перерождающихся каждый кадр
  dropRateBump: number; // прибавка к dropRate для быстрых частиц
  pointSize: number; // CSS-пиксели
  opacity: number; // прозрачность всего слоя
  colors: string[]; // шкала цвета по скорости
  speedScale: number; // м/с, верх шкалы
}

export const DEFAULT_WIND_OPTIONS: WindParticleOptions = {
  count: 6000,
  speedFactor: 0.0045,
  fadeOpacity: 0.955,
  dropRate: 0.003,
  dropRateBump: 0.01,
  pointSize: 1.6,
  opacity: 0.9,
  colors: ["#1c5cab", "#2a78d6", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"],
  speedScale: 20,
};

const REFERENCE_ZOOM = 4.5;

interface Program {
  program: WebGLProgram;
  uniforms: Map<string, WebGLUniformLocation | null>;
  attribs: Map<string, number>;
}

const QUAD = new Float32Array([0, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 1]);

const QUAD_VS = `#version 300 es
precision highp float;
in vec2 a_pos;
out vec2 v_tex;
void main() {
  v_tex = a_pos;
  gl_Position = vec4(a_pos * 2.0 - 1.0, 0.0, 1.0);
}`;

// Прошлый кадр с затуханием. Округление до 1/255 нужно, чтобы след действительно
// доходил до нуля, а не застревал на младших битах.
const SCREEN_FS = `#version 300 es
precision mediump float;
uniform sampler2D u_screen;
uniform float u_opacity;
in vec2 v_tex;
out vec4 fragColor;
void main() {
  vec4 c = texture(u_screen, v_tex);
  fragColor = floor(255.0 * c * u_opacity) / 255.0;
}`;

const UPDATE_FS = `#version 300 es
precision highp float;
uniform sampler2D u_particles;
uniform sampler2D u_wind;
uniform vec2 u_wind_min;
uniform vec2 u_wind_max;
uniform vec4 u_bbox;        // lonMin, latMin, lonSpan, latSpan
uniform float u_rand_seed;
uniform float u_speed_factor;
uniform float u_drop_rate;
uniform float u_drop_rate_bump;
uniform float u_speed_scale;
in vec2 v_tex;
out vec4 fragColor;

const vec3 rand_constants = vec3(12.9898, 78.233, 4375.85453);
float rand(const vec2 co) {
  float t = dot(rand_constants.xy, co);
  return fract(sin(t) * (rand_constants.z + t));
}

void main() {
  vec4 color = texture(u_particles, v_tex);
  vec2 pos = vec2(color.r / 255.0 + color.b, color.g / 255.0 + color.a);
  vec4 w = texture(u_wind, pos);
  vec2 velocity = mix(u_wind_min, u_wind_max, w.rg) * w.a;   // alpha 0 = нет данных → штиль
  float speed_t = clamp(length(velocity) / u_speed_scale, 0.0, 1.0);
  float lat = u_bbox.y + pos.y * u_bbox.w;
  float distortion = max(cos(radians(lat)), 0.2);
  vec2 offset = vec2(velocity.x / distortion, velocity.y) * u_speed_factor / vec2(u_bbox.z, u_bbox.w);
  pos += offset;
  vec2 seed = (pos + v_tex) * u_rand_seed;
  float drop_rate = u_drop_rate + speed_t * u_drop_rate_bump;
  float drop = step(1.0 - drop_rate, rand(seed));
  if (pos.x < 0.0 || pos.x > 1.0 || pos.y < 0.0 || pos.y > 1.0 || w.a < 0.5) drop = 1.0;
  vec2 random_pos = vec2(rand(seed + 1.3), rand(seed + 2.1));
  pos = mix(pos, random_pos, drop);
  fragColor = vec4(fract(pos * 255.0), floor(pos * 255.0) / 255.0);
}`;

function drawVertexSource(prelude: string, define: string): string {
  return `#version 300 es
precision highp float;
${prelude}
${define}
in float a_index;
uniform sampler2D u_particles;
uniform float u_particles_res;
uniform vec4 u_bbox;
uniform float u_point_size;
out vec2 v_particle_pos;
void main() {
  vec2 tex = vec2(fract(a_index / u_particles_res), floor(a_index / u_particles_res) / u_particles_res);
  vec4 color = texture(u_particles, tex);
  vec2 pos = vec2(color.r / 255.0 + color.b, color.g / 255.0 + color.a);
  v_particle_pos = pos;
  float lon = u_bbox.x + pos.x * u_bbox.z;
  float lat = u_bbox.y + pos.y * u_bbox.w;
  float mx = (lon + 180.0) / 360.0;
  float s = sin(radians(lat));
  float my = 0.5 - log((1.0 + s) / (1.0 - s)) / (4.0 * PI);
  gl_PointSize = u_point_size;
  gl_Position = projectTile(vec2(mx, my));
}`;
}

const DRAW_FS = `#version 300 es
precision mediump float;
uniform sampler2D u_wind;
uniform vec2 u_wind_min;
uniform vec2 u_wind_max;
uniform float u_speed_scale;
uniform sampler2D u_color_ramp;
in vec2 v_particle_pos;
out vec4 fragColor;
void main() {
  vec2 d = gl_PointCoord - 0.5;
  if (dot(d, d) > 0.25) discard;
  vec4 w = texture(u_wind, v_particle_pos);
  vec2 velocity = mix(u_wind_min, u_wind_max, w.rg) * w.a;
  float speed_t = clamp(length(velocity) / u_speed_scale, 0.0, 1.0);
  vec2 ramp_pos = vec2(fract(16.0 * speed_t), floor(16.0 * speed_t) / 16.0);
  fragColor = vec4(texture(u_color_ramp, ramp_pos).rgb, 1.0);
}`;

export class WindParticleLayer implements CustomLayerInterface {
  readonly id = "wind-particles";
  readonly type = "custom" as const;
  readonly renderingMode = "2d" as const;

  /** Сколько кадров нарисовано — для проверок и отладки. */
  frames = 0;
  /** Устройство не тянет: вызывается один раз, дальше слой лучше выключить. */
  onTooSlow: (() => void) | null = null;

  private map: MLMap | null = null;
  private gl: GL | null = null;
  private opts: WindParticleOptions;
  private grid: WindGrid | null = null;

  private quadBuffer: WebGLBuffer | null = null;
  private indexBuffer: WebGLBuffer | null = null;
  private fbo: WebGLFramebuffer | null = null;
  private windTexture: WebGLTexture | null = null;
  private rampTexture: WebGLTexture | null = null;
  private state: [WebGLTexture, WebGLTexture] | null = null;
  private screen: [WebGLTexture, WebGLTexture] | null = null;
  private screenSize = [0, 0];
  private res = 0;
  private screenProgram: Program | null = null;
  private updateProgram: Program | null = null;
  private drawPrograms = new Map<string, Program>();
  private lastMatrix: number[] | null = null;
  private watch = new FrameWatch(); // «не тянет» — по часам, не по счётчику кадров

  constructor(opts: Partial<WindParticleOptions> = {}) {
    this.opts = { ...DEFAULT_WIND_OPTIONS, ...opts };
  }

  /** Новое поле ветра (или null — частицы гаснут). Можно звать до onAdd. */
  setField(field: WindField | null): void {
    this.grid = field ? buildWindGrid(field) : null;
    if (this.gl) this.uploadWind(this.gl);
    this.map?.triggerRepaint();
  }

  setOptions(patch: Partial<WindParticleOptions>): void {
    const countChanged = patch.count != null && patch.count !== this.opts.count;
    this.opts = { ...this.opts, ...patch };
    if (countChanged && this.gl) this.createParticles(this.gl);
  }

  get ready(): boolean {
    return !!(this.gl && this.grid && this.windTexture && this.state);
  }

  onAdd(map: MLMap, gl: WebGLRenderingContext | WebGL2RenderingContext): void {
    if (!(gl instanceof WebGL2RenderingContext)) return; // MapLibre 6 — только WebGL2
    this.map = map;
    this.gl = gl;
    this.quadBuffer = createBuffer(gl, QUAD);
    this.fbo = gl.createFramebuffer();
    this.screenProgram = createProgram(gl, QUAD_VS, SCREEN_FS);
    this.updateProgram = createProgram(gl, QUAD_VS, UPDATE_FS);
    this.rampTexture = createTexture(gl, gl.LINEAR, colorRamp(this.opts.colors), 16, 16);
    this.createParticles(gl);
    if (this.grid) this.uploadWind(gl);
    this.lastMatrix = null;
    this.watch.reset();
  }

  onRemove(): void {
    const gl = this.gl;
    if (!gl) return;
    for (const p of [this.screenProgram, this.updateProgram, ...this.drawPrograms.values()]) {
      if (p) gl.deleteProgram(p.program);
    }
    this.drawPrograms.clear();
    this.screenProgram = this.updateProgram = null;
    for (const t of [
      this.windTexture,
      this.rampTexture,
      ...(this.state ?? []),
      ...(this.screen ?? []),
    ]) {
      if (t) gl.deleteTexture(t);
    }
    this.windTexture = this.rampTexture = null;
    this.state = this.screen = null;
    this.screenSize = [0, 0];
    if (this.quadBuffer) gl.deleteBuffer(this.quadBuffer);
    if (this.indexBuffer) gl.deleteBuffer(this.indexBuffer);
    if (this.fbo) gl.deleteFramebuffer(this.fbo);
    this.quadBuffer = this.indexBuffer = this.fbo = null;
    this.gl = null;
    this.map = null;
  }

  /** Offscreen-проход MapLibre: двигаем частицы и рисуем след в экранную текстуру. */
  prerender(
    _gl: WebGLRenderingContext | WebGL2RenderingContext,
    opts: CustomRenderMethodInput,
  ): void {
    const gl = this.gl;
    const grid = this.grid;
    if (!gl || !grid || !this.state || !this.windTexture || !this.map) return;
    const pd = opts.defaultProjectionData;
    const matrix = Array.from(pd.mainMatrix as ArrayLike<number>);
    const moved =
      !this.lastMatrix || matrix.some((v, i) => Math.abs(v - this.lastMatrix![i]) > 1e-9);
    this.lastMatrix = matrix;

    const prevFbo = gl.getParameter(gl.FRAMEBUFFER_BINDING) as WebGLFramebuffer | null;
    const prevViewport = gl.getParameter(gl.VIEWPORT) as Int32Array;
    this.ensureScreen(gl);
    if (!this.screen) return;

    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.STENCIL_TEST);
    gl.disable(gl.BLEND);
    gl.disable(gl.CULL_FACE);

    // 1. экран: затухающий прошлый кадр + частицы
    const [w, h] = this.screenSize;
    this.bindTarget(gl, this.screen[1], w, h);
    this.drawScreenTexture(gl, this.screen[0], moved ? 0 : this.opts.fadeOpacity);
    this.drawParticles(gl, opts);
    this.screen = [this.screen[1], this.screen[0]];

    // 2. состояние частиц: шаг по полю
    this.bindTarget(gl, this.state[1], this.res, this.res);
    this.updateParticles(gl, grid);
    this.state = [this.state[1], this.state[0]];

    gl.bindFramebuffer(gl.FRAMEBUFFER, prevFbo);
    gl.viewport(prevViewport[0], prevViewport[1], prevViewport[2], prevViewport[3]);
  }

  /** Основной проход: экранная текстура поверх карты с премультиплицированным смешиванием. */
  render(_gl: WebGLRenderingContext | WebGL2RenderingContext): void {
    const gl = this.gl;
    if (!gl || !this.screen || !this.grid || !this.map) return;
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.STENCIL_TEST);
    this.drawScreenTexture(gl, this.screen[0], this.opts.opacity);
    gl.disable(gl.BLEND);
    this.frames += 1;
    this.watchFrameTime();
    this.map.triggerRepaint(); // анимация непрерывна, пока слой виден
  }

  // --- внутреннее ------------------------------------------------------------------

  private watchFrameTime(): void {
    if (this.watch.tick(performance.now())) this.onTooSlow?.();
  }

  private createParticles(gl: GL): void {
    const res = Math.max(8, Math.ceil(Math.sqrt(this.opts.count)));
    this.res = res;
    const n = res * res;
    const initial = new Uint8Array(n * 4);
    for (let i = 0; i < initial.length; i++) initial[i] = Math.floor(Math.random() * 256);
    if (this.state) for (const t of this.state) gl.deleteTexture(t);
    this.state = [
      createTexture(gl, gl.NEAREST, initial, res, res),
      createTexture(gl, gl.NEAREST, initial, res, res),
    ];
    const index = new Float32Array(n);
    for (let i = 0; i < n; i++) index[i] = i;
    if (this.indexBuffer) gl.deleteBuffer(this.indexBuffer);
    this.indexBuffer = createBuffer(gl, index);
  }

  private uploadWind(gl: GL): void {
    if (this.windTexture) gl.deleteTexture(this.windTexture);
    this.windTexture = this.grid
      ? createTexture(gl, gl.LINEAR, this.grid.data, this.grid.cols, this.grid.rows)
      : null;
  }

  private ensureScreen(gl: GL): void {
    const w = gl.drawingBufferWidth;
    const h = gl.drawingBufferHeight;
    if (this.screen && this.screenSize[0] === w && this.screenSize[1] === h) return;
    if (this.screen) for (const t of this.screen) gl.deleteTexture(t);
    const empty = new Uint8Array(w * h * 4);
    this.screen = [
      createTexture(gl, gl.NEAREST, empty, w, h),
      createTexture(gl, gl.NEAREST, empty, w, h),
    ];
    this.screenSize = [w, h];
  }

  private bindTarget(gl: GL, texture: WebGLTexture, w: number, h: number): void {
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, texture, 0);
    gl.viewport(0, 0, w, h);
  }

  private drawScreenTexture(gl: GL, texture: WebGLTexture, opacity: number): void {
    const p = this.screenProgram;
    if (!p || !this.quadBuffer) return;
    activateProgram(gl, p.program);
    bindAttribute(gl, this.quadBuffer, p.attribs.get("a_pos")!, 2);
    bindTexture(gl, texture, 2);
    gl.uniform1i(p.uniforms.get("u_screen")!, 2);
    gl.uniform1f(p.uniforms.get("u_opacity")!, opacity);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
  }

  private drawParticles(gl: GL, opts: CustomRenderMethodInput): void {
    const grid = this.grid;
    if (!grid || !this.state || !this.windTexture || !this.rampTexture || !this.indexBuffer) return;
    const variant = opts.shaderData.variantName;
    let p = this.drawPrograms.get(variant);
    if (!p) {
      p = createProgram(
        gl,
        drawVertexSource(opts.shaderData.vertexShaderPrelude, opts.shaderData.define),
        DRAW_FS,
      );
      this.drawPrograms.set(variant, p);
    }
    activateProgram(gl, p.program);
    bindAttribute(gl, this.indexBuffer, p.attribs.get("a_index")!, 1);
    bindTexture(gl, this.state[0], 0);
    bindTexture(gl, this.windTexture, 1);
    bindTexture(gl, this.rampTexture, 3);
    gl.uniform1i(p.uniforms.get("u_particles")!, 0);
    gl.uniform1i(p.uniforms.get("u_wind")!, 1);
    gl.uniform1i(p.uniforms.get("u_color_ramp")!, 3);
    gl.uniform1f(p.uniforms.get("u_particles_res")!, this.res);
    gl.uniform4f(p.uniforms.get("u_bbox")!, grid.lonMin, grid.latMin, grid.lonSpan, grid.latSpan);
    gl.uniform2f(p.uniforms.get("u_wind_min")!, grid.uMin, grid.vMin);
    gl.uniform2f(p.uniforms.get("u_wind_max")!, grid.uMax, grid.vMax);
    gl.uniform1f(p.uniforms.get("u_speed_scale")!, this.opts.speedScale);
    gl.uniform1f(
      p.uniforms.get("u_point_size")!,
      this.opts.pointSize * (window.devicePixelRatio || 1),
    );
    // проекция MapLibre: те же uniforms, что у её собственных шейдеров
    const pd = opts.defaultProjectionData;
    setMatrix(gl, p, "u_projection_matrix", pd.mainMatrix);
    setMatrix(gl, p, "u_projection_fallback_matrix", pd.fallbackMatrix);
    setVec4(gl, p, "u_projection_tile_mercator_coords", pd.tileMercatorCoords);
    setVec4(gl, p, "u_projection_clipping_plane", pd.clippingPlane);
    const transition = p.uniforms.get("u_projection_transition");
    if (transition) gl.uniform1f(transition, pd.projectionTransition);
    gl.drawArrays(gl.POINTS, 0, this.res * this.res);
  }

  private updateParticles(gl: GL, grid: WindGrid): void {
    const p = this.updateProgram;
    if (!p || !this.state || !this.windTexture || !this.quadBuffer || !this.map) return;
    activateProgram(gl, p.program);
    bindAttribute(gl, this.quadBuffer, p.attribs.get("a_pos")!, 2);
    bindTexture(gl, this.state[0], 0);
    bindTexture(gl, this.windTexture, 1);
    gl.uniform1i(p.uniforms.get("u_particles")!, 0);
    gl.uniform1i(p.uniforms.get("u_wind")!, 1);
    gl.uniform4f(p.uniforms.get("u_bbox")!, grid.lonMin, grid.latMin, grid.lonSpan, grid.latSpan);
    gl.uniform2f(p.uniforms.get("u_wind_min")!, grid.uMin, grid.vMin);
    gl.uniform2f(p.uniforms.get("u_wind_max")!, grid.uMax, grid.vMax);
    gl.uniform1f(p.uniforms.get("u_rand_seed")!, Math.random());
    gl.uniform1f(p.uniforms.get("u_drop_rate")!, this.opts.dropRate);
    gl.uniform1f(p.uniforms.get("u_drop_rate_bump")!, this.opts.dropRateBump);
    gl.uniform1f(p.uniforms.get("u_speed_scale")!, this.opts.speedScale);
    // скорость в градусах за кадр: на крупном зуме медленнее, чтобы в пикселях
    // темп оставался похожим; кадр длиннее 16 мс — шаг больше
    const zoom = this.map.getZoom();
    const zoomScale = Math.min(Math.max(2 ** (REFERENCE_ZOOM - zoom), 0.08), 4);
    const frameScale = Math.min(Math.max(this.watch.frameMs / 16.7, 0.5), 3);
    gl.uniform1f(p.uniforms.get("u_speed_factor")!, this.opts.speedFactor * zoomScale * frameScale);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
  }
}

// --- GL-мелочи ------------------------------------------------------------------------

function createShader(gl: GL, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type);
  if (!shader) throw new Error("wind: createShader");
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(`wind: shader compile failed: ${log}`);
  }
  return shader;
}

function createProgram(gl: GL, vs: string, fs: string): Program {
  const program = gl.createProgram();
  if (!program) throw new Error("wind: createProgram");
  const v = createShader(gl, gl.VERTEX_SHADER, vs);
  const f = createShader(gl, gl.FRAGMENT_SHADER, fs);
  gl.attachShader(program, v);
  gl.attachShader(program, f);
  gl.linkProgram(program);
  gl.deleteShader(v);
  gl.deleteShader(f);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const log = gl.getProgramInfoLog(program);
    gl.deleteProgram(program);
    throw new Error(`wind: program link failed: ${log}`);
  }
  const uniforms = new Map<string, WebGLUniformLocation | null>();
  const nUniforms = gl.getProgramParameter(program, gl.ACTIVE_UNIFORMS) as number;
  for (let i = 0; i < nUniforms; i++) {
    const info = gl.getActiveUniform(program, i);
    if (info) uniforms.set(info.name, gl.getUniformLocation(program, info.name));
  }
  const attribs = new Map<string, number>();
  const nAttribs = gl.getProgramParameter(program, gl.ACTIVE_ATTRIBUTES) as number;
  for (let i = 0; i < nAttribs; i++) {
    const info = gl.getActiveAttrib(program, i);
    if (info) attribs.set(info.name, gl.getAttribLocation(program, info.name));
  }
  return { program, uniforms, attribs };
}

function createBuffer(gl: GL, data: Float32Array): WebGLBuffer {
  const buffer = gl.createBuffer();
  if (!buffer) throw new Error("wind: createBuffer");
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
  return buffer;
}

/** gl.useProgram через обёртку: имя `use*` Biome принимает за React-хук. */
function activateProgram(gl: GL, program: WebGLProgram): void {
  // biome-ignore lint/correctness/useHookAtTopLevel: WebGL API, не React-хук
  gl.useProgram(program);
}

function bindAttribute(gl: GL, buffer: WebGLBuffer, location: number, size: number): void {
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.enableVertexAttribArray(location);
  gl.vertexAttribPointer(location, size, gl.FLOAT, false, 0, 0);
}

function createTexture(
  gl: GL,
  filter: number,
  data: Uint8Array,
  w: number,
  h: number,
): WebGLTexture {
  const texture = gl.createTexture();
  if (!texture) throw new Error("wind: createTexture");
  gl.bindTexture(gl.TEXTURE_2D, texture);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter);
  gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, data);
  gl.bindTexture(gl.TEXTURE_2D, null);
  return texture;
}

function bindTexture(gl: GL, texture: WebGLTexture, unit: number): void {
  gl.activeTexture(gl.TEXTURE0 + unit);
  gl.bindTexture(gl.TEXTURE_2D, texture);
}

function setMatrix(gl: GL, p: Program, name: string, m: ArrayLike<number> | undefined): void {
  const loc = p.uniforms.get(name);
  if (loc && m) gl.uniformMatrix4fv(loc, false, Float32Array.from(m as ArrayLike<number>));
}

function setVec4(gl: GL, p: Program, name: string, v: ArrayLike<number> | undefined): void {
  const loc = p.uniforms.get(name);
  if (loc && v) gl.uniform4f(loc, v[0], v[1], v[2], v[3]);
}
