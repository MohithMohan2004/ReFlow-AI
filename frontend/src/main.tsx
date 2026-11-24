import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { installNativeGeolocation } from "./lib/nativeGeolocation";
import { installTheme } from "./lib/theme";
// Fonts are served from ReFlow itself (no request to Google Fonts).
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/sora/600.css";
import "@fontsource/sora/700.css";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/ui.css";
import "./styles/mobile.css";

installNativeGeolocation();
installTheme();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
