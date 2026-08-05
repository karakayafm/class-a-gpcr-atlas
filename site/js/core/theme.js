// Only two themes exist. Any stored value outside the set falls back to grey.
const THEMES = ["grey", "dark"];
let theme = "grey";
export function initTheme() {
  let s = null; try { s = localStorage.getItem("atlas.theme"); } catch (e) {}
  setTheme(THEMES.indexOf(s) >= 0 ? s : "grey"); }
export function setTheme(name) {
  theme = THEMES.indexOf(name) >= 0 ? name : "grey";
  document.documentElement.setAttribute("data-theme", theme);
  try { localStorage.setItem("atlas.theme", theme); } catch (e) {} }
export function getTheme() { return theme; }
export function themes() { return THEMES.slice(); }
