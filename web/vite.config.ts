import react from "@vitejs/plugin-react";
/// <reference types="vitest/config" />
import { defineConfig, loadEnv, type Plugin } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// В dev фронт живёт на :5173, API — на :8000 (python -m app.main); прокси
// снимает вопрос CORS. В проде собранный dist раздаёт сам FastAPI.

/**
 * Превью ссылок (Telegram, WhatsApp, Slack) требуют абсолютный URL картинки.
 * Публичный адрес берём из VITE_PUBLIC_URL, а на Vercel — из адреса продакшена;
 * без них og:image остаётся относительным (превью не будет, страница — будет).
 */
function absoluteOgUrls(publicUrl: string): Plugin {
  return {
    name: "mc-absolute-og-urls",
    transformIndexHtml(html) {
      if (!publicUrl) return html;
      const base = publicUrl.replace(/\/$/, "");
      return html
        .replaceAll('content="/og.png"', `content="${base}/og.png"`)
        .replace("</title>", `</title>\n    <meta property="og:url" content="${base}/" />`);
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, process.cwd(), ""), ...process.env };
  const publicUrl =
    env.VITE_PUBLIC_URL ||
    (env.VERCEL_PROJECT_PRODUCTION_URL ? `https://${env.VERCEL_PROJECT_PRODUCTION_URL}` : "");
  return {
    plugins: [
      react(),
      absoluteOgUrls(publicUrl),
      // PWA: манифест и сервис-воркер. Оболочка — офлайн; последний снимок и
      // ветер — NetworkFirst (сеть, при обрыве — кэш, фронт помечает «офлайн»).
      // SSE-поток и replay (at=) через воркер не кэшируются.
      VitePWA({
        registerType: "autoUpdate",
        includeAssets: ["icon.svg", "apple-touch-icon.png"],
        manifest: {
          name: "Middle Corridor · карта статуса коридора",
          short_name: "Middle Corridor",
          description:
            "Грузы, паромы, ветер и погода портов Каспия в реальном времени; replay за трое суток.",
          lang: "ru",
          theme_color: "#12161f",
          background_color: "#0f1216",
          display: "standalone",
          orientation: "any",
          start_url: "/",
          scope: "/",
          icons: [
            { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
            { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
            {
              src: "/icon-maskable-512.png",
              sizes: "512x512",
              type: "image/png",
              purpose: "maskable",
            },
          ],
        },
        workbox: {
          globPatterns: ["**/*.{js,css,html,svg,png,webmanifest}"],
          globIgnores: ["**/og.png", "**/og.svg"], // превью ссылок в оболочку не нужно
          maximumFileSizeToCacheInBytes: 3 * 1024 * 1024,
          navigateFallback: "/index.html",
          navigateFallbackDenylist: [/^\/api\//, /^\/health/],
          runtimeCaching: [
            {
              urlPattern: ({ url }) =>
                url.pathname === "/api/v1/snapshot" && !url.searchParams.has("at"),
              handler: "NetworkFirst",
              options: {
                cacheName: "mc-snapshot",
                networkTimeoutSeconds: 8,
                expiration: { maxEntries: 2, maxAgeSeconds: 24 * 3600 },
              },
            },
            {
              urlPattern: ({ url }) =>
                url.pathname === "/api/v1/wind" && !url.searchParams.has("at"),
              handler: "NetworkFirst",
              options: {
                cacheName: "mc-wind",
                networkTimeoutSeconds: 8,
                expiration: { maxEntries: 2, maxAgeSeconds: 24 * 3600 },
              },
            },
          ],
        },
        devOptions: { enabled: false },
      }),
    ],
    server: {
      port: 5173,
      proxy: { "/api": "http://localhost:8000" },
    },
    // Dev-оптимизатор (Rolldown) дублирует maplibre-gl-shared в пребандле: два
    // экземпляра style-spec, и валидатор не знает line-layer-opacity. Отдаём
    // maplibre как есть — он и так ESM.
    optimizeDeps: { exclude: ["maplibre-gl"] },
    build: { outDir: "dist", sourcemap: false },
    // Юнит-тесты чистой логики (vitest): без DOM и без сети
    test: { include: ["src/**/*.test.{ts,tsx}"], environment: "node" },
  };
});
