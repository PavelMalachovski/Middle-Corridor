import react from "@vitejs/plugin-react";
/// <reference types="vitest/config" />
import { defineConfig } from "vite";

// В dev фронт живёт на :5173, API — на :8000 (python -m app.main); прокси
// снимает вопрос CORS. В проде собранный dist раздаёт сам FastAPI.
export default defineConfig({
  plugins: [react()],
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
  test: { include: ["src/**/*.test.ts"], environment: "node" },
});
