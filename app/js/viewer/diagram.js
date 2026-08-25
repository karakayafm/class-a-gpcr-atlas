/* A two-dimensional interaction diagram, drawn from the pose rather than from a depiction.
 *
 * The usual way to draw one of these is to lay the ligand out as a textbook structure — bonds at
 * 120°, rings regular — and then place the contacting residues around it by a layout algorithm that
 * has no knowledge of where they actually are. That needs a chemistry toolkit in the browser, and
 * it throws away the one thing this atlas has: the deposited coordinates.
 *
 * So this projects instead. The ligand's own heavy atoms define a plane by principal components,
 * and everything — the molecule, and the contacting residue of each contact — is projected onto it.
 * The molecule comes out looking like the pose seen down its own best axis rather than like a
 * ChemDraw figure, and in exchange every residue sits on the side it is really on. A ring viewed
 * edge-on will look flat, which is honest: it is flat from there.
 *
 * The output is one SVG panel per structure, side by side, so a superposition can be read as a
 * comparison. Nothing here is fetched; it is all read from the structures already on screen.
 */
import { genericShort, oneLetter } from "./viewer.js";
import { depict } from "./depict.js";

/* Segment colours, chosen against the segments that actually share a panel.
 *
 * The first version of this palette was picked by eye and two of its entries were the same grey:
 * TM5 and every ICL sat 2.9 CIE76 units apart, which is no distance at all, and TM4 against TM7 was
 * 13.7. So the choice was made a measurement instead. Counting segment co-occurrence over all 1300
 * observations in the atlas says which pairs ever have to be told apart: TM3, TM7, TM6, TM5 and
 * ECL2 appear in more than 85% of pockets, TM2 in 62%, TM4 in 44%, and the intracellular loops in
 * about 1%. Separation spent on ICL1-against-ICL3 is therefore wasted, and separation between TM3
 * and TM7 is not. These sixteen colours come from a search over an LCH grid that maximises the
 * worst separation among pairs co-occurring in at least 5% of pockets; that worst case is 25.9,
 * and the five pairs seen in over 85% of pockets all sit above that.
 *
 * N-TERM was missing from the hand-picked version and appears in 19% of pockets, so 251
 * observations were drawing an unnamed grey bubble. */
const SEGMENT_COLOUR = {
  TM1: "#04ccf4", TM2: "#d395a7", TM3: "#d6cbfc", TM4: "#8ae4b0",
  TM5: "#90e0db", TM6: "#d19c5e", TM7: "#d4d785", H8: "#e2c8f6",
  ECL1: "#ce91d3", ECL2: "#93ae82", ECL3: "#5aacf1",
  ICL1: "#f7a4bd", ICL2: "#e28e9a", ICL3: "#dab58e",
  "N-TERM": "#eb8d7b", "C-TERM": "#75ccad"
};
const DEFAULT_COLOUR = "#c8c8c8";

/* What kind of contact each line is.
 *
 * Until now every contact was the same red dash, so a salt bridge, a hydrogen bond and a passing
 * hydrophobic brush were indistinguishable — which is most of what a reader wants from a figure
 * like this. NGL computes the types; they are read back below.
 *
 * These are not the same greens and mustards the 3D view uses. Measured against white, the 3D
 * hydrogen-bond green (#7fe0a0) has a contrast ratio of 1.61:1 and the hydrophobic mustard
 * (#d8a531) 2.25:1, both far under the 3:1 a thin line needs to survive being printed. The hues are
 * kept so the two views still read as the same thing; the lightness is not. */
const INTERACTION = {
  hbond:       { colour: "#1f9d55", width: 1.5, dash: "5 3",   label: "hydrogen bond" },
  weak_hbond:  { colour: "#1f9d55", width: 0.9, dash: "2 3",   label: "weak hydrogen bond" },
  hydrophobic: { colour: "#a87a10", width: 1.4, dash: "1 3",   label: "hydrophobic" },
  ionic:       { colour: "#c2185b", width: 2.0, dash: "6 3",   label: "salt bridge" },
  pi_stacking: { colour: "#5548c8", width: 1.8, dash: "7 3",   label: "\u03c0-stacking" },
  cation_pi:   { colour: "#00707d", width: 1.8, dash: "7 3",   label: "cation-\u03c0" },
  halogen:     { colour: "#8a5a00", width: 1.5, dash: "5 3",   label: "halogen bond" },
  metal:       { colour: "#455a64", width: 1.8, dash: "5 3",   label: "metal coordination" },
  proximity:   { colour: "#8b9196", width: 0.8, dash: "2 4",   label: "close contact" }
};
/* NGL's own type names, grouped the way the 3D view groups them so the two agree on what counts as
   a hydrogen bond. `proximity` is not one of NGL's: it is what is left when a residue is in the
   contact shell but no interaction was detected, and saying so is better than drawing nothing. */
const NGL_TYPES = {
  hbond:       ["hydrogenBond", "waterHydrogenBond", "backboneHydrogenBond"],
  weak_hbond:  ["weakHydrogenBond"],
  hydrophobic: ["hydrophobic"],
  ionic:       ["ionicInteraction"],
  pi_stacking: ["piStacking"],
  cation_pi:   ["cationPi"],
  halogen:     ["halogenBond"],
  metal:       ["metalCoordination"]
};
const ALL_NGL_TYPES = Object.values(NGL_TYPES).flat();
// Drawn in this order, so a salt bridge is not buried under the hydrophobic brush beside it.
const TYPE_ORDER = ["proximity", "hydrophobic", "weak_hbond", "hbond", "halogen", "metal",
                    "cation_pi", "pi_stacking", "ionic"];
const ELEMENT_COLOUR = { N: "#3050f8", O: "#ff0d0d", S: "#c8c832", P: "#ff8000",
  F: "#90e050", CL: "#1ff01f", BR: "#a62929", I: "#940094" };

/* Ångström-to-pixel, chosen once for the whole figure rather than per panel. Two panels drawn at
   two scales would put a big ligand and a small one at the same apparent size, which is the one
   thing a side-by-side comparison must not do. */
const PX_PER_ANGSTROM = 20;
/* One length for every bond in the sketch. A carbon-carbon single bond is about 1.5 A, and drawing
   them all at that length is the whole point: real bond lengths differ by a few percent and
   projection turns those few percent into a factor of two. */
const BOND_PX = 29;
const PAD = 30, HEADER = 74;
const RING_GAP = 22;            // clear space between the molecule and the nearest bubble

/* Two names for the same residue, and which one leads matters here.
 *
 * The deposited number is what a crystallographer looks for, but it is a property of the
 * deposition: β2-adrenoceptor Asp3x32 is 113 in 2RH1 and 3113 in 4LDE, because that construct
 * numbers its fusion partner into the receptor. Panels are placed side by side in order to be
 * compared, and a reader cannot compare ASP113 against ASP3113 at a glance. So the generic position
 * leads — the same label the 3D viewer puts on the residue, so the two views agree — and the
 * deposited name and number follow underneath for anyone who needs to find it in the file. */
function residueNames(d) {
  const three = String(d.residue_name || "").toUpperCase();
  const one = oneLetter(three);
  // The same two helpers the 3D labels use, so "D3x32" means the same glyphs in both views.
  const pos = genericShort(d.generic_position);
  const deposited = (three ? three[0] + three.slice(1).toLowerCase() : "?") + d.auth_seq_id;
  return { lead: pos ? one + pos : deposited, deposited };
}

function centroid(points) {
  const n = points.length;
  return [0, 1, 2].map(i => points.reduce((a, p) => a + p[i], 0) / n);
}

/* Two principal axes of the ligand's own atoms, by Jacobi on the 3x3 covariance. The molecule is
   drawn down its smallest axis, which is the direction in which it is flattest — for anything with
   a ring system that is close to the ring plane. */
function planeOf(points) {
  const c = centroid(points);
  const cov = [[0,0,0],[0,0,0],[0,0,0]];
  for (const p of points) {
    const d = [p[0]-c[0], p[1]-c[1], p[2]-c[2]];
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) cov[i][j] += d[i]*d[j];
  }
  let A = cov.map(r => r.slice());
  let V = [[1,0,0],[0,1,0],[0,0,1]];
  for (let sweep = 0; sweep < 60; sweep++) {
    let off = 0;
    for (let i = 0; i < 3; i++) for (let j = i+1; j < 3; j++) off += A[i][j]*A[i][j];
    if (off < 1e-12) break;
    for (let i = 0; i < 3; i++) for (let j = i+1; j < 3; j++) {
      if (Math.abs(A[i][j]) < 1e-15) continue;
      const th = (A[j][j] - A[i][i]) / (2*A[i][j]);
      const tt = Math.sign(th || 1) / (Math.abs(th) + Math.sqrt(th*th + 1));
      const cs = 1/Math.sqrt(tt*tt + 1), sn = tt*cs;
      const R = [[1,0,0],[0,1,0],[0,0,1]];
      R[i][i]=cs; R[j][j]=cs; R[i][j]=sn; R[j][i]=-sn;
      const mul = (X, Y) => X.map((row, a) => Y[0].map((_, b) =>
        row.reduce((s, v, k) => s + v * Y[k][b], 0)));
      const Rt = R[0].map((_, a) => R.map(row => row[a]));
      A = mul(mul(Rt, A), R);
      V = mul(V, R);
    }
  }
  const order = [0,1,2].sort((a,b) => A[b][b] - A[a][a]);
  const axis = k => [V[0][order[k]], V[1][order[k]], V[2][order[k]]];
  return { origin: c, u: axis(0), v: axis(1) };
}
const project = (p, pl) => [
  (p[0]-pl.origin[0])*pl.u[0] + (p[1]-pl.origin[1])*pl.u[1] + (p[2]-pl.origin[2])*pl.u[2],
  (p[0]-pl.origin[0])*pl.v[0] + (p[1]-pl.origin[1])*pl.v[1] + (p[2]-pl.origin[2])*pl.v[2]];

/* Residue bubbles are pushed out along the direction they already lie in, far enough to clear the
   molecule, then separated from each other. Their angle around the ligand is the real one; only the
   radius is invented, and it is invented because two things at different depths can project onto
   the same point and a diagram that overlaps them says less than one that does not.

   Everything here is already in pixels. Doing the push in Ångströms and adding a pixel clearance —
   which is what the first version did — throws the bubbles several molecule-widths out and leaves
   the ligand a dot in the middle once the panel is fitted around them.

   Separation is by bounding box, not by circle. A bubble is a circle with two lines of text under
   it, and "Val117 · 4.0 Å" is far wider than the circle it belongs to; separating the circles alone
   leaves those lines lying on top of each other, which is exactly what the first version did. */
const CHAR_W = 4.9;             // mean advance of the 8.5px label font, measured on the output
function extent(b) {
  const textW = Math.max(String(b.label).length * 5.6, String(b.sub || "").length * CHAR_W + 30);
  return { hw: Math.max(b.r, textW / 2) + 3, hh: b.r + 13 };
}

function placeBubbles(items, ligand2d) {
  const rMol = Math.max(...ligand2d.map(a => Math.hypot(a.x, a.y)), 1);
  // A ring has to be big enough to seat every bubble without crowding, so the count sets a floor.
  const perimeter = items.reduce((a, b) => a + 2 * extent(b).hw + 4, 0);
  const ring = Math.max(rMol + RING_GAP, perimeter / (2 * Math.PI));
  for (const it of items) {
    const d = Math.hypot(it.x, it.y) || 1e-6;
    const want = ring + it.r;
    it.x *= want / d; it.y *= want / d;
  }
  const box = items.map(extent);
  for (let pass = 0; pass < 600; pass++) {
    let moved = false;
    for (let i = 0; i < items.length; i++)
      for (let j = i+1; j < items.length; j++) {
        const a = items[i], b = items[j], ea = box[i], eb = box[j];
        const dx = b.x - a.x, dy = b.y - a.y;
        const ox = ea.hw + eb.hw - Math.abs(dx);      // overlap along each axis
        const oy = ea.hh + eb.hh - Math.abs(dy);
        if (ox <= 0 || oy <= 0) continue;             // boxes already clear
        // Push apart along whichever axis needs the smaller correction — the shortest way out.
        if (ox < oy) {
          const k = (dx >= 0 ? 1 : -1) * ox / 2;
          a.x -= k; b.x += k;
        } else {
          const k = (dy >= 0 ? 1 : -1) * oy / 2;
          a.y -= k; b.y += k;
        }
        moved = true;
      }
    // Separating two bubbles can walk one back over the molecule, so the clearance is re-imposed.
    for (const it of items) {
      const d = Math.hypot(it.x, it.y) || 1e-6;
      const min = rMol + RING_GAP + it.r;
      if (d < min) { it.x *= min/d; it.y *= min/d; moved = true; }
    }
    if (!moved) break;
  }
  return items;
}

/* The interaction types NGL finds between the ligand and the rest of the structure.
 *
 * NGL computes contacts but does not keep them: the representation consumes them into a geometry
 * buffer and the typed list is gone. What survives is the geometry, and that is enough — one
 * representation is built per type group with only that type enabled, and its line endpoints are
 * read back out. The endpoints are world coordinates, so they can be matched against atoms.
 *
 * The representation is created hidden and removed immediately. Nothing is patched in NGL, which
 * is vendored byte-identical and must stay that way. */
function typedContacts(comp, ligSele, recSele) {
  const out = [];
  for (const [key, types] of Object.entries(NGL_TYPES)) {
    const params = { filterSele: [ligSele, recSele], visible: false };
    for (const t of ALL_NGL_TYPES) params[t] = types.indexOf(t) >= 0;
    let rep = null;
    try {
      rep = comp.addRepresentation("contact", params);
      const data = rep.repr && rep.repr.dataList && rep.repr.dataList[0];
      const geom = data && data.bufferList && data.bufferList[0] && data.bufferList[0].geometry;
      const a1 = geom && geom.attributes && geom.attributes.position1;
      const a2 = geom && geom.attributes && geom.attributes.position2;
      if (a1 && a2) {
        // One contact becomes many vertices, so identical endpoint pairs collapse to one line.
        const seen = new Set();
        for (let i = 0; i < a1.count; i++) {
          const p1 = [a1.getX(i), a1.getY(i), a1.getZ(i)];
          const p2 = [a2.getX(i), a2.getY(i), a2.getZ(i)];
          const k = p1.concat(p2).map(v => v.toFixed(2)).join(",");
          if (seen.has(k)) continue;
          seen.add(k);
          out.push({ type: key, p1, p2 });
        }
      }
    } catch (e) {
      // A build without this interaction type simply contributes nothing.
    }
    if (rep) { try { comp.removeRepresentation(rep); } catch (e) {} }
  }
  return out;
}

const dist2 = (a, b) => (a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2;

/* Each contact line, resolved to the ligand atom at one end and the residue at the other.
 *
 * The endpoints are usually atom centres, but for pi-stacking and cation-pi NGL puts them at ring
 * centroids, which belong to no atom. So this takes the nearest of each rather than an exact match,
 * and drops anything whose nearest ligand atom is further than a ring radius away — that is the
 * only case in which the endpoint is not describing the ligand at all. */
function resolveContacts(raw, atoms, residueAtoms) {
  const out = [];
  for (const c of raw) {
    for (const [lend, rend] of [[c.p1, c.p2], [c.p2, c.p1]]) {
      let la = null, lb = Infinity;
      for (const a of atoms) { const d = dist2(a.p, lend); if (d < lb) { lb = d; la = a; } }
      let rk = null, rb = Infinity;
      for (const r of residueAtoms) { const d = dist2(r.p, rend); if (d < rb) { rb = d; rk = r; } }
      if (!la || !rk || lb > 9 || rb > 9) continue;    // 3 A: past a ring radius, not this ligand
      out.push({ type: c.type, ligIndex: la.index, key: rk.key,
                 distance: Math.sqrt(dist2(lend, rend)) });
      break;                                            // the other orientation is the same contact
    }
  }
  return out;
}

/* Everything one panel needs, read off a loaded structure. `spec` names the ligand residues and the
   contacts; the coordinates come from the component. */
function panelData(spec) {
  const { comp, meta, observation } = spec;
  const NGL = window.NGL;
  if (!comp || !NGL) return null;
  const obs = (meta.observations || []).find(o => o.observation_id === observation) ||
              (meta.observations || []).find(o => o.ligand_selection) || null;
  if (!obs || !obs.ligand_selection) return null;
  const want = new Set((obs.ligand_selection.residues || []).map(r => r[0] + ":" + r[1]));
  if (!want.size) return null;

  const atoms = [], byIndex = new Map();
  comp.structure.eachAtom(a => {
    if (a.element === "H" || a.number === 1) return;
    if (!want.has(a.chainname + ":" + a.resno)) return;
    const rec = { index: a.index, el: (a.element || "C").toUpperCase(),
                  p: [a.x, a.y, a.z], name: a.atomname };
    atoms.push(rec); byIndex.set(a.index, rec);
  });
  if (atoms.length < 2) return null;

  const bonds = [];
  try {
    comp.structure.eachBond(b => {
      if (byIndex.has(b.atomIndex1) && byIndex.has(b.atomIndex2))
        bonds.push([b.atomIndex1, b.atomIndex2, b.bondOrder || 1]);
    });
  } catch (e) { /* fall through to distance-based bonds below */ }
  if (!bonds.length)
    for (let i = 0; i < atoms.length; i++)
      for (let j = i+1; j < atoms.length; j++) {
        const d = Math.hypot(...[0,1,2].map(k => atoms[i].p[k]-atoms[j].p[k]));
        if (d < 1.75) bonds.push([atoms[i].index, atoms[j].index, 1]);
      }

  /* Each contacting residue, with the ligand atom it is nearest to — that atom is where the dashed
     line has to start, and it is also what makes the contact readable as chemistry. Every heavy atom
     of the residue is kept as well, because an interaction NGL reports may land on a different one
     than the closest approach does. */
  const residues = [];
  const residueAtoms = [];
  for (const d of obs.contact_receptor_details || []) {
    const key = d.auth_asym_id + ":" + d.auth_seq_id;
    let best = null;
    comp.structure.eachAtom(a => {
      if (a.element === "H" || a.number === 1) return;
      residueAtoms.push({ key, p: [a.x, a.y, a.z] });
      for (const la of atoms) {
        const q = Math.hypot(a.x-la.p[0], a.y-la.p[1], a.z-la.p[2]);
        if (!best || q < best.d) best = { d: q, r: [a.x, a.y, a.z], lig: la };
      }
    }, new NGL.Selection(d.auth_seq_id + ":" + d.auth_asym_id + " and not hydrogen"));
    if (!best) continue;
    const seg = String(d.segment || "").toUpperCase();
    const n = residueNames(d);
    residues.push({ key, label: n.lead, sub: n.deposited, segment: seg,
                    distance: Number(d.min_distance_angstrom),
                    p: best.r, ligIndex: best.lig.index, links: [] });
  }

  /* The typed interactions, hung on the residues they belong to. A residue can hold more than one —
     a salt bridge from its carboxylate and a hydrophobic brush from its CB are two different facts
     about the same residue — and each is drawn from the ligand atom it actually involves. Residues
     that come back with nothing typed keep a single faint line to their closest approach, which is
     all the payload's distance ever claimed. */
  const byKey = new Map(residues.map(r => [r.key, r]));
  const ligSele = "(" + (obs.ligand_selection.residues || [])
    .map(r => r[1] + ":" + r[0]).join(" or ") + ")";
  const recSele = "not " + ligSele;
  try {
    const seen = new Set();
    for (const c of resolveContacts(typedContacts(comp, ligSele, recSele), atoms, residueAtoms)) {
      const r = byKey.get(c.key);
      if (!r) continue;                       // outside the contact shell the payload recorded
      const k = c.key + "|" + c.type + "|" + c.ligIndex;
      if (seen.has(k)) continue;
      seen.add(k);
      r.links.push({ type: c.type, ligIndex: c.ligIndex, distance: c.distance });
    }
  } catch (e) {
    // No typed contacts available: every residue falls back to the proximity line below.
  }
  for (const r of residues)
    if (!r.links.length)
      r.links.push({ type: "proximity", ligIndex: r.ligIndex, distance: r.distance });
  /* The three-letter chemical component code, which is how a ligand is actually looked up in a
     deposition, sits at the end of the entity id: "3SN6:LE:np:P0G". */
  const ccd = String(obs.ligand_entity_id || "").split(":").pop();
  return { pdb: meta.pdb_id, receptor: plain(meta.receptor_name || spec.name || ""),
           state: meta.structural_state || "", mode: obs.binding_mode || "",
           ligand: obs.ligand_name || "", ccd: ccd && ccd !== meta.pdb_id ? ccd : "",
           atoms, bonds, residues };
}

/* Receptor names in the payload carry HTML — "&beta;<sub>2</sub>-adrenoceptor" — because every other
   surface in the atlas renders them into a page. SVG has no <sub>, so the markup is flattened here
   rather than escaped, which would print the tags. */
function plain(html) {
  return String(html || "")
    .replace(/<[^>]*>/g, "")
    .replace(/&beta;/g, "β").replace(/&alpha;/g, "α").replace(/&gamma;/g, "γ")
    .replace(/&kappa;/g, "κ").replace(/&mu;/g, "μ").replace(/&delta;/g, "δ")
    .replace(/&amp;/g, "&").replace(/&nbsp;/g, " ").trim();
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g,
    c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;" }[c]));
}

/* Layout, separated from drawing so that every panel can be measured before any of them is sized.
   Coordinates come out in pixels, centred on the ligand. */
function layoutPanel(data, axes) {
  /* Orientation is shared across the row, position is not.
   *
   * Superposition has already put every structure in one coordinate frame, so the same viewing
   * plane can be used for all of them — and it has to be, or D3x32 lands top-left in one panel and
   * top-centre in the next and the row cannot be read across. Each ligand is still centred in its
   * own panel: what the row is for is comparing which residues reach which part of each ligand, not
   * how far apart two ligands sit, and a panel drawn around an off-centre molecule wastes the space
   * the labels need. Without overlays there is nothing to share and the ligand defines its own.
   *
   * Centring per panel is what stops the agreement from being exact. A bubble's angle is measured
   * from its own panel's ligand centre, so a residue lying between two ligands that sit a few
   * Ångströms apart can come out on opposite sides of the two. Measured over 2RH1/3SN6/4LDE the
   * median shared position agrees to 19°, with one outlier near 160°. Centring every panel on the
   * base ligand instead would fix the angles and push the other ligands off their own panels,
   * which is the worse trade. */
  const own = planeOf(data.atoms.map(a => a.p));
  const pl = axes ? { origin: own.origin, u: axes.u, v: axes.v } : own;
  /* The pose, projected. This is no longer what gets drawn — it is the target the sketch is
     oriented against, and it is what the residue bubbles are placed from. */
  const projected = new Map();
  for (const a of data.atoms) {
    const [x, y] = project(a.p, pl);
    projected.set(a.index, [x * PX_PER_ANGSTROM, y * PX_PER_ANGSTROM]);
  }
  const sketch = depict(data.atoms, data.bonds, projected, BOND_PX);
  const pos = new Map();
  for (const [k, v] of sketch.pos) pos.set(k, { x: v[0], y: v[1] });
  const bubbles = data.residues.map(r => {
    const [x, y] = project(r.p, pl);
    // Radius carries the distance: a close contact is a big circle, which is the convention the
    // published figures of this kind use and the first thing the eye sorts on.
    const rr = Math.max(15, 31 - (isFinite(r.distance) ? r.distance : 4) * 3.2);
    return { ...r, x: x * PX_PER_ANGSTROM, y: y * PX_PER_ANGSTROM, r: rr };
  });
  placeBubbles(bubbles, [...pos.values()]);
  let half = 1;
  for (const p of pos.values()) half = Math.max(half, Math.abs(p.x), Math.abs(p.y));
  for (const b of bubbles) {
    const e = extent(b);
    half = Math.max(half, Math.abs(b.x) + e.hw, Math.abs(b.y) + e.hh);
  }
  return { data, pos, bubbles, half };
}

/* How many columns to break the panels into.
 *
 * A single row is right for two or three structures and wrong for six: laid out straight across,
 * six panels are four thousand pixels wide, and whatever the figure is scaled down to fit means the
 * labels are unreadable. Panels are square, so a grid roughly half again as wide as it is tall puts
 * the figure at the proportions of a screen or a page.
 *
 * The trailing loop drops a column whenever doing so costs no extra row, which is what turns 4 into
 * 2x2 rather than 3+1 and 9 into 3x3 rather than 4+4+1. */
export function gridShape(n) {
  let cols = Math.ceil(Math.sqrt(n * 1.5));
  const rows = Math.ceil(n / cols);
  while (cols > 1 && Math.ceil(n / (cols - 1)) === rows) cols--;
  return { cols, rows: Math.ceil(n / cols) };
}

function renderPanel(layout, xOffset, yOffset, panelW, panelH) {
  const { data, pos, bubbles } = layout;
  const cx = xOffset + panelW / 2, cy = yOffset + HEADER + (panelH - HEADER) / 2;
  const tx = p => cx + p.x, ty = p => cy - p.y;      // y up, as in the projection

  const out = [];
  /* Which structure, then what it is. The binding mode is the reason a reader put three panels next
     to each other in the first place, so it goes in the header rather than in a legend. */
  const ligLine = [data.ligand, data.ccd].filter(Boolean).join(" · ");
  const stateLine = [data.receptor, data.mode || data.state].filter(Boolean).join(" · ");
  out.push(`<text x="${xOffset + PAD}" y="${yOffset + 30}" class="d-title">${esc(data.pdb)}</text>`);
  if (stateLine)
    out.push(`<text x="${xOffset + PAD}" y="${yOffset + 48}" class="d-sub">${esc(stateLine)}</text>`);
  if (ligLine)
    out.push(`<text x="${xOffset + PAD}" y="${yOffset + 64}" class="d-sub">${esc(ligLine)}</text>`);

  /* Contact lines, weakest first, so a salt bridge is drawn over the hydrophobic brush beside it
     rather than under it. */
  const drawn = [];
  for (const b of bubbles)
    for (const l of b.links || []) drawn.push({ b, l });
  drawn.sort((p, q) => TYPE_ORDER.indexOf(p.l.type) - TYPE_ORDER.indexOf(q.l.type));
  for (const { b, l } of drawn) {
    const a = pos.get(l.ligIndex);
    if (!a) continue;
    const style = INTERACTION[l.type] || INTERACTION.proximity;
    out.push(`<line x1="${tx(a).toFixed(1)}" y1="${ty(a).toFixed(1)}" x2="${tx(b).toFixed(1)}" ` +
      `y2="${ty(b).toFixed(1)}" stroke="${style.colour}" stroke-width="${style.width}" ` +
      `stroke-dasharray="${style.dash}" fill="none"/>`);
  }
  for (const [i, j, order] of data.bonds) {
    const a = pos.get(i), b = pos.get(j);
    if (!a || !b) continue;
    const x1 = tx(a), y1 = ty(a), x2 = tx(b), y2 = ty(b);
    if (order >= 2) {
      // A double bond as two parallel lines, offset perpendicular to the bond.
      const dx = x2-x1, dy = y2-y1, len = Math.hypot(dx, dy) || 1;
      const ox = -dy/len * 2.2, oy = dx/len * 2.2;
      for (const k of [1, -1])
        out.push(`<line x1="${(x1+ox*k).toFixed(1)}" y1="${(y1+oy*k).toFixed(1)}" ` +
          `x2="${(x2+ox*k).toFixed(1)}" y2="${(y2+oy*k).toFixed(1)}" class="d-bond"/>`);
    } else {
      out.push(`<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" ` +
        `y2="${y2.toFixed(1)}" class="d-bond"/>`);
    }
  }
  for (const a of data.atoms) {
    if (a.el === "C") continue;                 // carbon is implied, as in any structure drawing
    const p = pos.get(a.index);
    out.push(`<circle cx="${tx(p).toFixed(1)}" cy="${ty(p).toFixed(1)}" r="7.5" class="d-atom-bg"/>`);
    out.push(`<text x="${tx(p).toFixed(1)}" y="${(ty(p)+3.8).toFixed(1)}" class="d-atom" ` +
      `fill="${ELEMENT_COLOUR[a.el] || "#444"}">${esc(a.el)}</text>`);
  }
  for (const b of bubbles) {
    const fill = SEGMENT_COLOUR[b.segment] || DEFAULT_COLOUR;
    const bx = tx(b).toFixed(1), by = ty(b);
    // Opaque, because the palette was chosen by measuring these colours; drawing them at 60% over
    // white would wash out the separation the search was optimising for.
    out.push(`<circle cx="${bx}" cy="${by.toFixed(1)}" r="${b.r.toFixed(1)}" ` +
      `fill="${fill}" stroke="#00000022" stroke-width="1"/>`);
    const dist = isFinite(b.distance) ? b.distance.toFixed(1) + " Å" : "";
    out.push(`<text x="${bx}" y="${(by-5).toFixed(1)}" class="d-seg">${esc(b.segment)}</text>`);
    out.push(`<text x="${bx}" y="${(by+6).toFixed(1)}" class="d-res">${esc(b.label)}</text>`);
    out.push(`<text x="${bx}" y="${(by+16).toFixed(1)}" class="d-dist">` +
      `${esc(b.sub)}${dist ? " · " + dist : ""}</text>`);
  }
  return out.join("\n");
}

const STYLE = `
.d-title{font:600 15px system-ui,sans-serif;fill:#111}
.d-sub{font:12px system-ui,sans-serif;fill:#555}
.d-bond{stroke:#222;stroke-width:1.8;stroke-linecap:round}
.d-link{stroke:#b03030;stroke-width:1.2;stroke-dasharray:4 3}
.d-atom{font:600 10px system-ui,sans-serif;text-anchor:middle}
.d-atom-bg{fill:#fff}
.d-seg{font:600 9px system-ui,sans-serif;text-anchor:middle;fill:#333}
.d-res{font:600 10.5px system-ui,sans-serif;text-anchor:middle;fill:#111}
.d-dist{font:8.5px system-ui,sans-serif;text-anchor:middle;fill:#444}
/* Labels wider than their own circle sit over the dashed contact lines, so each is given a white
   outline drawn underneath the glyphs. */
.d-seg,.d-res,.d-dist{paint-order:stroke;stroke:#fff;stroke-width:2.4px;stroke-linejoin:round}
.d-frame{fill:none;stroke:#ddd;stroke-width:1}
.d-rule{fill:none;stroke:#ddd;stroke-width:1}
.d-legend{font:11px system-ui,sans-serif;fill:#333;dominant-baseline:middle}
`;

/* One SVG holding one panel per structure, in the order they were given — the base structure first
   and each superposed one after it, so the file reads as the comparison it was asked for. */
/* A key for the line colours, listing only the interaction types the figure actually contains.
   A fixed legend would claim halogen bonds in a figure that has none.

   It wraps: a single panel is only ~600 px wide and the five types a typical aminergic pocket shows
   do not fit on one line, which the first version silently ran off the edge of. */
const LEGEND_ROW = 22;
function legend(panels, width, top) {
  const present = new Set();
  for (const p of panels)
    for (const b of p.bubbles)
      for (const l of b.links || []) present.add(l.type);
  const keys = TYPE_ORDER.filter(k => present.has(k)).reverse();
  if (!keys.length) return { svg: "", height: 0 };

  const items = keys.map(k => ({ s: INTERACTION[k],
                                 w: 30 + INTERACTION[k].label.length * 6.3 + 18 }));
  const usable = width - 2 * PAD;
  const rows = [[]];
  let used = 0;
  for (const it of items) {
    if (used + it.w > usable && rows[rows.length - 1].length) { rows.push([]); used = 0; }
    rows[rows.length - 1].push(it);
    used += it.w;
  }
  const out = [`<line x1="${PAD}" y1="${top}" x2="${width - PAD}" y2="${top}" class="d-rule"/>`];
  rows.forEach((row, ri) => {
    const total = row.reduce((a, b) => a + b.w, 0);
    let x = Math.max(PAD, (width - total) / 2);
    const y = top + 18 + ri * LEGEND_ROW;
    for (const it of row) {
      out.push(`<line x1="${x.toFixed(0)}" y1="${y}" x2="${(x + 26).toFixed(0)}" y2="${y}" ` +
        `stroke="${it.s.colour}" stroke-width="${it.s.width}" stroke-dasharray="${it.s.dash}"/>`);
      out.push(`<text x="${(x + 32).toFixed(0)}" y="${y}" class="d-legend">${esc(it.s.label)}</text>`);
      x += it.w;
    }
  });
  return { svg: out.join("\n"), height: 18 + rows.length * LEGEND_ROW + 8 };
}

export function buildSVG(specs) {
  const data = specs.map(panelData).filter(Boolean);
  if (!data.length) return null;
  // The first structure is the one on screen, so the row is oriented the way it is being looked at.
  const shared = data.length > 1 ? planeOf(data[0].atoms.map(a => a.p)) : null;
  const panels = data.map(d => layoutPanel(d, shared));
  /* One box for every panel, sized by the widest of them. Panels of different sizes would be read
     as ligands of different sizes, and the point of the row is that they are not. */
  const half = Math.max(...panels.map(p => p.half));
  const panelW = Math.ceil(2 * half + 2 * PAD);
  const panelH = Math.ceil(2 * half + 2 * PAD + HEADER);
  const { cols, rows } = gridShape(panels.length);
  const width = panelW * cols, gridH = panelH * rows;
  const key = legend(panels, width, gridH + 6);
  const height = gridH + key.height;
  const rules = [];
  for (let c = 1; c < cols; c++)
    rules.push(`<line x1="${panelW*c}" y1="12" x2="${panelW*c}" y2="${gridH-12}" class="d-frame"/>`);
  for (let r = 1; r < rows; r++)
    rules.push(`<line x1="12" y1="${panelH*r}" x2="${width-12}" y2="${panelH*r}" class="d-frame"/>`);
  const body = rules.join("\n") + "\n" + panels.map((p, i) =>
    renderPanel(p, panelW * (i % cols), panelH * Math.floor(i / cols), panelW, panelH)
  ).join("\n") + "\n" + key.svg;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" ` +
    `viewBox="0 0 ${width} ${height}"><style>${STYLE}</style>` +
    `<rect width="${width}" height="${height}" fill="#ffffff"/>${body}</svg>`;
}

export function downloadSVG(specs, filename) {
  const svg = buildSVG(specs);
  if (!svg) return false;
  const blob = new Blob([svg], { type: "image/svg+xml" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename + ".svg";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return true;
}

/* PNG by way of the same SVG, so the two downloads cannot drift apart. Drawn at twice the size
   because these are read at figure scale and the labels are small. */
export function downloadPNG(specs, filename) {
  const svg = buildSVG(specs);
  if (!svg) return false;
  const blob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const img = new Image();
  img.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = img.width * 2; canvas.height = img.height * 2;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    URL.revokeObjectURL(url);
    canvas.toBlob(b => {
      const u = URL.createObjectURL(b);
      const a = document.createElement("a");
      a.href = u; a.download = filename + ".png";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(u), 1000);
    }, "image/png");
  };
  img.onerror = () => URL.revokeObjectURL(url);
  img.src = url;
  return true;
}
