// WebGL lifecycle protection, written fresh for this project.
//
// The failure this guards against: calling stage.handleResize() while the modal is closed and
// the viewport is 0x0 permanently loses the WebGL context on real GPUs, while remaining
// invisible under headless software rendering. Every resize therefore goes through a
// visibility+size gate, and the context-lost event tears the stage down for a clean rebuild.

let stage = null;
let host = null;
let listeners = [];      // every listener we attach is tracked so it can be removed exactly once
let contextLost = false;

export function isVisible(node) {
  if (!node) return false;
  if (!node.isConnected) return false;
  const r = node.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
}

export function resizeStageIfVisible() {
  if (!stage || !host || contextLost) return false;
  if (!isVisible(host)) return false;
  stage.handleResize();
  return true;
}

function track(target, type, fn, opts) {
  target.addEventListener(type, fn, opts);
  listeners.push({ target, type, fn, opts });
}

export function hasStage() { return !!stage && !contextLost; }
export function getStage() { return stage; }
export function isContextLost() { return contextLost; }

export function createStage(NGL, node, params) {
  destroyStage();                       // never stack canvases or stages
  host = node;
  contextLost = false;
  stage = new NGL.Stage(node, params || {});
  // Wheel rotation keeps NGL's normal zoom behaviour. Holding the wheel (middle button) and
  // dragging pans, matching the right-button behaviour used by the aminergic reference viewer.
  try {
    stage.mouseControls.remove("drag-middle");
    stage.mouseControls.add("drag-middle", NGL.MouseActions.panDrag);
    /* NGL binds its own measurement to right-click and ctrl-left by default. It works — it has
       been quietly working here all along — but it is a second measurement mechanism with no
       readout, no way to clear it and no sign that it exists, and right-click also opens the
       browser's context menu. The atlas has its own measurement mode with a panel, so these are
       removed and there is exactly one way to measure. */
    stage.mouseControls.remove("clickPick-right");
    stage.mouseControls.remove("clickPick-ctrl-left");
  } catch (e) { /* retain the library defaults if a future NGL build changes this API */ }
  const canvas = node.querySelector("canvas");
  if (canvas) {
    track(canvas, "webglcontextlost", ev => {
      ev.preventDefault();
      contextLost = true;
      destroyStage();                   // drop the dead stage; the next open rebuilds it
    });
  }
  track(window, "resize", () => { resizeStageIfVisible(); });
  return stage;
}

export function destroyStage() {
  for (const l of listeners) {
    try { l.target.removeEventListener(l.type, l.fn, l.opts); } catch (e) {}
  }
  listeners = [];
  if (stage) {
    try { stage.removeAllComponents(); } catch (e) {}
    try { stage.dispose(); } catch (e) {}
  }
  stage = null;
  if (host) { while (host.firstChild) host.removeChild(host.firstChild); }
  host = null;
}

// Diagnostics used by the regression harness.
export function diagnostics() {
  return {
    canvasCount: document.querySelectorAll("canvas").length,
    stageCount: stage ? 1 : 0,
    listenerCount: listeners.length,
    contextLost
  };
}
