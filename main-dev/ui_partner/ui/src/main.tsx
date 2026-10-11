import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router";
import "@fontsource-variable/archivo/wdth.css";
import "@fontsource-variable/jetbrains-mono/wght.css";
import "./styles/app.css";
import { App } from "./app/App";
import { EngineProvider } from "./engine/EngineProvider";

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <HashRouter>
        <EngineProvider>
          <App />
        </EngineProvider>
      </HashRouter>
    </StrictMode>,
  );
}
