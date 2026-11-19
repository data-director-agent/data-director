import "@fontsource-variable/inter";
import "./tokens/neutral.css";
import "./styles/index.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { startPreferences } from "./preferences";

// Before the first render, so that a dark choice does not flash light.
startPreferences();

const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
