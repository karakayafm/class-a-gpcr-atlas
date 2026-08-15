// Display names. Payload names carry markup the PDB uses for subscripts, and family names are
// the one place the release's English is translated rather than passed through; both are needed
// by more than one view, so they sit here rather than in whichever view happened to need them
// first.
import { getLang } from "../core/i18n.js";

export function plainName(value) {
  const node = document.createElement("span");
  node.innerHTML = String(value || "").replace(/<sub>(.*?)<\/sub>/gi, "$1");
  return (node.textContent || "").replace(/\s+/g, " ").trim();
}
export function familyDisplayName(value) {
  const clean = plainName(value);
  if (getLang() !== "tr") return clean;
  return ({ "Aminergic receptors": "Aminergik reseptörler", "Peptide receptors": "Peptit reseptörleri",
    "Lipid receptors": "Lipit reseptörleri", "Orphan receptors": "Yetim reseptörler",
    "Nucleotide receptors": "Nükleotit reseptörleri", "Protein receptors": "Protein reseptörleri",
    "Sensory receptors": "Duyusal reseptörler", "Melatonin receptors": "Melatonin reseptörleri",
    "Steroid receptors": "Steroit reseptörleri",
    "Alicarboxylic acid receptors": "Alikarboksilik asit reseptörleri",
    "Other": "Diğer" })[clean] || clean;
}
