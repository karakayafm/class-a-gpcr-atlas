/* Turning the connectivity into a flat sketch, instead of flattening the pose.
 *
 * Projection alone cannot draw a ring that stands perpendicular to the projection plane: it comes
 * out as a line, and a phenyl drawn as a line is worse than useless. Measured on 7E33, projected
 * bond lengths ran from 13.7 to 30.7 px for bonds that are all about the same length in reality.
 *
 * So rings are built rather than projected. Every ring becomes a regular polygon of the same bond
 * length, fused rings are placed edge-to-edge, and the chains hanging off them zigzag at 120° the
 * way a hand-drawn structure does. The pose is not thrown away: the finished sketch is rotated (and
 * reflected if that fits better) onto the projected coordinates, so the molecule still faces the way
 * it does in the pocket and the residue bubbles — which are still placed by projection — stay on
 * the side they belong to.
 */

const TAU = Math.PI * 2;

/* Every small ring, found as the shortest cycle through each bond. Removing a bond and asking for
   the shortest path back between its ends gives that bond's smallest ring; doing it for all bonds
   and deduplicating gives both rings of an indole and neither of the envelopes around them. */
export function findRings(atoms, bonds, maxSize = 8) {
  const adj = new Map(atoms.map(a => [a.index, []]));
  for (const [i, j] of bonds) {
    if (adj.has(i) && adj.has(j)) { adj.get(i).push(j); adj.get(j).push(i); }
  }
  const seen = new Set(), rings = [];
  for (const [u, v] of bonds) {
    if (!adj.has(u) || !adj.has(v)) continue;
    // shortest path u -> v without using the u-v bond
    const prev = new Map([[u, null]]);
    const queue = [u];
    let found = false;
    for (let qi = 0; qi < queue.length && !found; qi++) {
      const x = queue[qi];
      for (const y of adj.get(x)) {
        if (x === u && y === v) continue;
        if (x === v && y === u) continue;
        if (prev.has(y)) continue;
        prev.set(y, x);
        if (y === v) { found = true; break; }
        queue.push(y);
      }
    }
    if (!found) continue;
    const path = [];
    for (let x = v; x != null; x = prev.get(x)) path.push(x);
    if (path.length < 3 || path.length > maxSize) continue;
    const key = path.slice().sort((a, b) => a - b).join(",");
    if (seen.has(key)) continue;
    seen.add(key);
    rings.push(path);                 // already in cyclic order
  }
  return { rings, adj };
}

/* Rings sharing any atom are laid out together; anything else can be placed independently. */
function fuseSystems(rings) {
  const parent = rings.map((_, i) => i);
  const find = i => (parent[i] === i ? i : (parent[i] = find(parent[i])));
  for (let i = 0; i < rings.length; i++)
    for (let j = i + 1; j < rings.length; j++)
      if (rings[i].some(a => rings[j].indexOf(a) >= 0)) parent[find(i)] = find(j);
  const groups = new Map();
  rings.forEach((r, i) => {
    const k = find(i);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(r);
  });
  return [...groups.values()];
}

const sub = (a, b) => [a[0]-b[0], a[1]-b[1]];
const norm = v => { const d = Math.hypot(v[0], v[1]) || 1; return [v[0]/d, v[1]/d]; };

/* The centre and vertex order of a regular n-gon that has `a`-`b` as one of its edges, placed on
   whichever side of that edge points away from `away`. */
function polygonOnEdge(pa, pb, n, away) {
  const L = Math.hypot(pb[0]-pa[0], pb[1]-pa[1]) || 1;
  const apothem = L / (2 * Math.tan(Math.PI / n));
  const mid = [(pa[0]+pb[0])/2, (pa[1]+pb[1])/2];
  const dir = norm(sub(pb, pa));
  const perp = [-dir[1], dir[0]];
  const c1 = [mid[0] + perp[0]*apothem, mid[1] + perp[1]*apothem];
  const c2 = [mid[0] - perp[0]*apothem, mid[1] - perp[1]*apothem];
  const d1 = Math.hypot(c1[0]-away[0], c1[1]-away[1]);
  const d2 = Math.hypot(c2[0]-away[0], c2[1]-away[1]);
  return d1 >= d2 ? c1 : c2;
}

/* Lay one fused ring system out, starting from its biggest ring.
 *
 * `anchor` is how a ring system that hangs off a chain gets positioned. Without it, every system
 * was built around the origin, so a molecule like BRL-54443 — an indole and a piperidine joined by
 * a single bond, which is two systems, not one — drew both rings on top of each other. With it, the
 * ring is built around the atom the chain already placed, extending away from where the chain came
 * from. */
function layoutSystem(system, pos, bondLen, anchor) {
  const ordered = system.slice().sort((a, b) => b.length - a.length);
  const placedHere = [];

  const placeFirst = ring => {
    const n = ring.length;
    const R = bondLen / (2 * Math.sin(Math.PI / n));
    let centre = [0, 0], phase = -Math.PI/2;
    if (anchor) {
      const k0 = ring.indexOf(anchor.idx);
      if (k0 >= 0) {
        centre = [anchor.pos[0] + anchor.dir[0]*R, anchor.pos[1] + anchor.dir[1]*R];
        phase = Math.atan2(anchor.pos[1]-centre[1], anchor.pos[0]-centre[0]) - k0 * TAU / n;
      }
    }
    ring.forEach((idx, k) => {
      const th = phase + k * TAU / n;
      pos.set(idx, [centre[0] + R * Math.cos(th), centre[1] + R * Math.sin(th)]);
      placedHere.push(idx);
    });
  };

  // With an anchor, the ring carrying it has to be the one laid down first.
  if (anchor) {
    const i = ordered.findIndex(r => r.indexOf(anchor.idx) >= 0);
    if (i > 0) ordered.unshift(ordered.splice(i, 1)[0]);
  }
  let anyPlaced = false;
  for (let pass = 0; pass < ordered.length * 3; pass++) {
    let progressed = false;
    for (const ring of ordered) {
      if (ring.every(i => pos.has(i))) continue;
      if (!anyPlaced) { placeFirst(ring); anyPlaced = true; progressed = true; continue; }
      if (ring.some(i => pos.has(i)) === false) continue;   // wait until it touches the system
      // find an edge of this ring whose two atoms are already placed
      const n = ring.length;
      let ei = -1;
      for (let k = 0; k < n; k++)
        if (pos.has(ring[k]) && pos.has(ring[(k+1) % n])) { ei = k; break; }
      if (ei < 0) continue;
      const a = ring[ei], b = ring[(ei+1) % n];
      const pa = pos.get(a), pb = pos.get(b);
      let cx = 0, cy = 0;
      for (const i of placedHere) { const p = pos.get(i); cx += p[0]; cy += p[1]; }
      const away = [cx / placedHere.length, cy / placedHere.length];
      const centre = polygonOnEdge(pa, pb, n, away);
      const angA = Math.atan2(pa[1]-centre[1], pa[0]-centre[0]);
      const angB = Math.atan2(pb[1]-centre[1], pb[0]-centre[0]);
      let delta = angB - angA;
      while (delta > Math.PI) delta -= TAU;
      while (delta < -Math.PI) delta += TAU;
      const step = Math.sign(delta) * TAU / n;
      const R = Math.hypot(pa[0]-centre[0], pa[1]-centre[1]);
      for (let k = 2; k < n; k++) {
        const idx = ring[(ei + k) % n];
        if (pos.has(idx)) continue;
        const th = angA + step * k;
        pos.set(idx, [centre[0] + R*Math.cos(th), centre[1] + R*Math.sin(th)]);
        placedHere.push(idx);
      }
      progressed = true;
    }
    if (!progressed) break;
  }
  return placedHere;
}

/* Do two segments cross? Shared endpoints do not count — bonds meeting at an atom are not a
   crossing, they are a bond angle. */
function crosses(a, b, c, d) {
  const eq = (p, q) => Math.abs(p[0]-q[0]) < 1e-6 && Math.abs(p[1]-q[1]) < 1e-6;
  if (eq(a,c) || eq(a,d) || eq(b,c) || eq(b,d)) return false;
  const s = (p, q, r) => Math.sign((q[0]-p[0])*(r[1]-p[1]) - (q[1]-p[1])*(r[0]-p[0]));
  return s(a,b,c) !== s(a,b,d) && s(c,d,a) !== s(c,d,b);
}

/* Chains and substituents.
 *
 * A substituent goes 120° off the bond that reached its neighbour, which is what makes a chain
 * zigzag instead of doubling back on itself. Of the two directions that satisfy that, the one
 * chosen is whichever crosses no existing bond, stays clear of other atoms, and — only as a
 * tie-break — points the way the real pose points, so the sketch still faces the pocket correctly.
 *
 * Scoring by clearance alone, which is what the first version did, drew the linker of BI-167107
 * straight back across its own phenyl. */
function layoutChains(atoms, adj, pos, bondLen, sysOf, systems, placedSys, bonds, projected) {
  const all = atoms.map(a => a.index);
  if (!pos.size) pos.set(all[0], [0, 0]);

  const segments = () => bonds
    .filter(([i, j]) => pos.has(i) && pos.has(j))
    .map(([i, j]) => [pos.get(i), pos.get(j)]);

  let guard = 0;
  for (;;) {
    if (++guard > all.length * 4) break;
    let grew = false;
    for (const v of all) {
      if (!pos.has(v)) continue;
      const pv = pos.get(v);
      for (const w of (adj.get(v) || [])) {
        if (pos.has(w)) continue;
        const used = (adj.get(v) || []).filter(x => pos.has(x))
          .map(x => Math.atan2(pos.get(x)[1]-pv[1], pos.get(x)[0]-pv[0]));

        /* Preferred directions first: 120° either side of each bond already at this atom. If the
           atom has nothing placed yet, the pose decides. Everything else is a fallback. */
        const prefer = [];
        for (const d of used) { prefer.push(d + TAU/3); prefer.push(d - TAU/3); }
        if (!used.length && projected.has(w) && projected.has(v)) {
          const q = projected.get(w), qv = projected.get(v);
          prefer.push(Math.atan2(q[1]-qv[1], q[0]-qv[0]));
        }
        const fallback = [];
        for (let k = 0; k < 24; k++) fallback.push(k * TAU / 24);

        const segs = segments();
        const wantDir = (projected.has(w) && projected.has(v))
          ? Math.atan2(projected.get(w)[1]-projected.get(v)[1],
                       projected.get(w)[0]-projected.get(v)[0]) : null;
        const evaluate = (th, bonusPreferred) => {
          const cand = [pv[0] + bondLen*Math.cos(th), pv[1] + bondLen*Math.sin(th)];
          let cross = 0;
          for (const [p, q] of segs) if (crosses(pv, cand, p, q)) cross++;
          let near = Infinity;
          for (const [, p] of pos) {
            const d = Math.hypot(p[0]-cand[0], p[1]-cand[1]);
            if (d > 1e-6) near = Math.min(near, d);
          }
          let apart = Infinity;
          for (const d of used) {
            let diff = Math.abs(th - d);
            if (diff > Math.PI) diff = TAU - diff;
            apart = Math.min(apart, diff);
          }
          let poseFit = 0;
          if (wantDir != null) {
            let diff = Math.abs(th - wantDir);
            if (diff > Math.PI) diff = TAU - diff;
            poseFit = (Math.PI - diff) / Math.PI;
          }
          const score = -cross * 100
            + Math.min(near / bondLen, 1.3) * 10
            + Math.min(apart, 2.1) * 4
            + poseFit * 2
            + bonusPreferred;
          return { score, cand };
        };

        let best = null;
        for (const th of prefer) {
          const r = evaluate(th, 6);
          if (!best || r.score > best.score) best = r;
        }
        for (const th of fallback) {
          const r = evaluate(th, 0);
          if (!best || r.score > best.score) best = r;
        }

        const sys = sysOf && sysOf.get(w);
        if (sys != null && placedSys && !placedSys.has(sys)) {
          const dir = norm(sub(best.cand, pv));
          layoutSystem(systems[sys], pos, bondLen, { idx: w, pos: best.cand, dir });
          placedSys.add(sys);
          if (!pos.has(w)) pos.set(w, best.cand);
        } else {
          pos.set(w, best.cand);
        }
        grew = true;
      }
    }
    if (!grew) break;
  }
  for (const v of all) if (!pos.has(v)) pos.set(v, [0, 0]);
}

/* How many pairs of bonds cross. Zero is the goal; it is also the number the tests watch. */
export function crossingCount(pos, bonds) {
  const segs = bonds.filter(([i, j]) => pos.has(i) && pos.has(j))
    .map(([i, j]) => [pos.get(i), pos.get(j)]);
  let n = 0;
  for (let i = 0; i < segs.length; i++)
    for (let j = i + 1; j < segs.length; j++)
      if (crosses(segs[i][0], segs[i][1], segs[j][0], segs[j][1])) n++;
  return n;
}

/* Rotate, reflect and translate the sketch onto the projected pose. Scale is deliberately not
   fitted: the whole point is that every bond ends up the same length. */
function alignToPose(pos, projected) {
  const keys = [...pos.keys()].filter(k => projected.has(k));
  if (keys.length < 2) return pos;
  const mean = src => {
    let x = 0, y = 0;
    for (const k of keys) { const p = src.get(k); x += p[0]; y += p[1]; }
    return [x / keys.length, y / keys.length];
  };
  const mp = mean(pos), mq = mean(projected);
  let best = null;
  for (const flip of [1, -1]) {
    let sxx = 0, sxy = 0;
    for (const k of keys) {
      const p = pos.get(k), q = projected.get(k);
      const px = (p[0]-mp[0]) * flip, py = p[1]-mp[1];
      sxx += px * (q[0]-mq[0]) + py * (q[1]-mq[1]);
      sxy += px * (q[1]-mq[1]) - py * (q[0]-mq[0]);
    }
    const th = Math.atan2(sxy, sxx);
    let err = 0;
    for (const k of keys) {
      const p = pos.get(k), q = projected.get(k);
      const px = (p[0]-mp[0]) * flip, py = p[1]-mp[1];
      const rx = px*Math.cos(th) - py*Math.sin(th) + mq[0];
      const ry = px*Math.sin(th) + py*Math.cos(th) + mq[1];
      err += (rx-q[0])**2 + (ry-q[1])**2;
    }
    if (!best || err < best.err) best = { err, th, flip };
  }
  const out = new Map();
  for (const [k, p] of pos) {
    const px = (p[0]-mp[0]) * best.flip, py = p[1]-mp[1];
    out.set(k, [px*Math.cos(best.th) - py*Math.sin(best.th) + mq[0],
                px*Math.sin(best.th) + py*Math.cos(best.th) + mq[1]]);
  }
  return out;
}

/* The sketch: regular rings, uniform bonds, oriented like the pose. */
export function depict(atoms, bonds, projected, bondLen) {
  const { rings, adj } = findRings(atoms, bonds);
  const systems = fuseSystems(rings);
  const sysOf = new Map();
  systems.forEach((sys, i) => sys.forEach(r => r.forEach(a => sysOf.set(a, i))));
  const size = i => new Set(systems[i].flat()).size;

  const pos = new Map();
  const placedSys = new Set();
  if (systems.length) {
    // The biggest ring system is the backbone of the picture, so it is laid down first and
    // everything else is positioned relative to it.
    let big = 0;
    for (let i = 1; i < systems.length; i++) if (size(i) > size(big)) big = i;
    layoutSystem(systems[big], pos, bondLen, null);
    placedSys.add(big);
  }
  layoutChains(atoms, adj, pos, bondLen, sysOf, systems, placedSys, bonds, projected);
  const aligned = alignToPose(pos, projected);
  return { pos: aligned, rings, systems: systems.length,
           crossings: crossingCount(aligned, bonds) };
}
