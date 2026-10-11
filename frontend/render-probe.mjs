// Headless render probe: executes the real app bundle in jsdom against the
// real production API, in both logged-out and logged-in states. Catches
// "white screen" bugs (render crashes) that API checks and unit tests miss.
//
// Usage (from frontend/): first build the IIFE test bundle, then run:
//   npx esbuild src/main.jsx --bundle --format=iife --outfile=dist/test-iife.js ^
//     "--define:import.meta.env={}" --loader:.css=empty --jsx=automatic
//   node render-probe.mjs
import { JSDOM } from "jsdom";
import fs from "node:fs";

const BASE = "https://chess-vs-computer-five.vercel.app";
const bundle = fs.readFileSync("dist/test-iife.js", "utf8");

async function render(label, token) {
  const errors = [];
  const dom = new JSDOM(`<!doctype html><html><body><div id="root"></div></body></html>`, {
    url: BASE + "/",
    runScripts: "outside-only",
    pretendToBeVisual: true,
    beforeParse(window) {
      window.fetch = (url, opts) => fetch(new URL(url, BASE), opts);
      window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
      window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
      window.addEventListener("error", (e) => errors.push(String(e.error?.stack || e.error || e.message)));
      window.addEventListener("unhandledrejection", (e) => errors.push("rejection: " + String(e.reason?.stack || e.reason)));
    },
  });
  if (token) dom.window.localStorage.setItem("chess_auth_token", token);
  dom.window.eval(bundle);
  await new Promise((r) => setTimeout(r, 7000));
  const text = dom.window.document.body.textContent.replace(/\s+/g, " ").trim();
  console.log(`== ${label} ==`);
  console.log("js errors :", errors.length ? errors.join("\n") : "none");
  console.log("rendered  :", text.slice(0, 260) || "(EMPTY - would be a white screen!)");
  console.log();
  dom.window.close();
}

await render("logged out", null);
const g = await (await fetch(BASE + "/api/auth/guest", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: '{"name":"HeadlessProbe"}',
})).json();
await render(`logged in as ${g.user.name}`, g.token);
