import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, devices } from "@playwright/test";

/**
 * E2E против собранного фронта (web/dist), который раздаёт FastAPI с
 * MOCK_DATA=true — как в проде, только данные синтетические. Перед запуском:
 * npm run build. Локально переиспользует уже запущенный API на :8000.
 *
 * Тайлы подложки в CI недоступны — карта пустая, проверяем оверлеи и панели.
 */

const ROOT = resolve(fileURLToPath(new URL(".", import.meta.url)), ".."); // ESM: __dirname нет
const VENV_PYTHON = resolve(ROOT, ".venv/bin/python");
const PYTHON = process.env.MC_PYTHON ?? (existsSync(VENV_PYTHON) ? VENV_PYTHON : "python");
const PORT = 8000;

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1, // один API и один рендер на SwiftShader: параллель только мешает
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI
    ? [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]]
    : [["list"]],
  outputDir: "test-results",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    serviceWorkers: "block", // иначе page.route(404/503) не перехватит запросы через воркер
    locale: "ru-RU", // язык интерфейса по умолчанию берётся из браузера; тесты ждут русский
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    video: "off",
    launchOptions: {
      // Предустановленный Chromium (песочница разработки); в CI ставится штатный
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined,
      args: [
        "--use-gl=angle",
        "--use-angle=swiftshader",
        "--enable-unsafe-swiftshader",
        "--ignore-gpu-blocklist",
      ],
    },
  },
  projects: [
    {
      name: "desktop",
      testIgnore: /mobile\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 860 } },
    },
    {
      name: "mobile",
      testMatch: /mobile\.spec\.ts/,
      use: { ...devices["Pixel 7"], defaultBrowserType: "chromium" },
    },
  ],
  webServer: {
    command: `${PYTHON} -m app.main`,
    cwd: ROOT,
    url: `http://127.0.0.1:${PORT}/api/v1/snapshot`,
    reuseExistingServer: !process.env.CI,
    timeout: 90_000,
    env: {
      MOCK_DATA: "true",
      MOCK_TIME_SCALE: "600", // сутки мока за ~2,5 минуты: движение видно за секунды
      STREAM_INTERVAL_S: "2",
      BOT_TOKEN: "",
      AISSTREAM_API_KEY: "",
      SCHEDULER_ENABLED: "false",
      LOG_LEVEL: "WARNING",
      PORT: String(PORT),
    },
  },
});
