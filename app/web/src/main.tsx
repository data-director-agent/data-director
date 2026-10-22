import "./tokens/neutral.css";
import "./base.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { applyTheme, storedTheme } from "./theme";

// Before the first render, so a dark choice does not flash light.
applyTheme(storedTheme());

const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
