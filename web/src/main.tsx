import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { registerSW } from "virtual:pwa-register";
import { App } from "./App";

// Сервис-воркер: оболочка офлайн, последний снимок из кэша. Обновление — тихое,
// новая версия подхватывается при следующем открытии.
registerSW({ immediate: true });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
