import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// В dev фронт живёт на :5173, API — на :8000 (python -m app.main); прокси
// снимает вопрос CORS. В проде собранный dist раздаёт сам FastAPI.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
  build: { outDir: "dist", sourcemap: false },
});
