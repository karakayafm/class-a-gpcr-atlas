// Structure sources dialog. Heavy family references/evidence/xref payloads are fetched only
// after the reader asks for them; structure browsing itself stays compact.
import { t, getLang } from "../core/i18n.js";
import { el, clear } from "./dom.js";
import * as L from "../data/loader.js";

let opener = null;
export function button(slug, structure) { return el("button", { class:"btn", type:"button",
  text:t("source_open"), onclick:event=>open(slug,structure,event.currentTarget) }); }

/* Inline, grouped source links for the structure detail panel. The same family payloads the
   dialog uses are fetched here, but `loadFamilyFile` caches them, so opening the dialog
   afterwards costs nothing extra. Returns immediately with a placeholder and fills in. */
export function linkRow(slug,structure) {
  const box=el("div", { class:"source-groups" }, [el("p", { class:"muted small", text:t("loading") })]);
  (async ()=>{
    let refs,xrefs;
    try { [refs,xrefs]=await Promise.all([L.loadFamilyReferences(slug),L.loadLigandXrefs(slug)]); }
    catch (error) { clear(box); box.appendChild(el("p", { class:"muted small", text:L.errorMessage(error) })); return; }
    const reference=(refs.structure_sources||[]).find(row=>row.pdb_id===structure.pdb_id)||{};
    const citation=reference.primary_citation||{};
    const ccds=new Set((structure.observations||[]).flatMap(row=>row.ligand_components||[]));
    const ligands=(xrefs.records||[]).filter(row=>ccds.has(row.ccd));
    const groups=[
      [t("source_group_structure"),[
        [reference.rcsb_entry,"RCSB "+structure.pdb_id],
        [reference.pdb_doi,"PDB DOI"],
        [citation.doi?"https://doi.org/"+citation.doi:
          (citation.pubmed_id?"https://pubmed.ncbi.nlm.nih.gov/"+citation.pubmed_id+"/":null),
          t("source_primary_article")]]],
      [t("source_group_annotation"),[[reference.gpcrdb_structure,"GPCRdb "+structure.pdb_id]]],
      [t("source_group_pharmacology"),ligands.filter(row=>row.gtopdb)
        .map(row=>[row.gtopdb.url,"GtoPdb "+row.gtopdb.id+(row.gtopdb.approximate?" ≈":"")])],
      [t("source_group_chemistry"),ligands.flatMap(row=>[
        // The PDB chemical component page always exists for a CCD code, so it needs no xref.
        ["https://www.rcsb.org/ligand/"+row.ccd,t("source_ligand_page",{ ccd:row.ccd })],
        [row.chembl&&row.chembl.url,row.chembl?"CHEMBL"+String(row.chembl.id).replace(/^CHEMBL/,"")+
          (row.chembl.approximate?" ≈":""):null],
        [row.pubchem&&row.pubchem.url,row.pubchem?"PubChem "+row.pubchem.id+
          (row.pubchem.approximate?" ≈":""):null]])]
    ];
    clear(box);
    for (const [label,entries] of groups) {
      const live=entries.filter(([href,text])=>href&&text);
      if (!live.length) continue;
      box.appendChild(el("div", { class:"source-group" }, [
        el("span", { class:"source-group-label", text:label }),
        el("span", { class:"source-link-row" },
          live.map(([href,text])=>el("a", { class:"source-chip",href,target:"_blank",rel:"noopener",text })))
      ]));
    }
    box.appendChild(button(slug,structure));
  })();
  return box;
}

async function open(slug,structure,sourceButton) {
  const modal=ensureModal(); opener=sourceButton; modal.hidden=false;
  const body=modal.querySelector(".source-modal-body"); clear(body);
  body.appendChild(el("p", { class:"muted", text:t("loading") }));
  modal.querySelector("h2").textContent=t("source_title")+" — "+structure.pdb_id;
  try {
    const [refs,evidence,xrefs]=await Promise.all([L.loadFamilyReferences(slug),
      L.loadFamilyEvidence(slug),L.loadLigandXrefs(slug)]);
    render(body,structure,refs,evidence,xrefs);
  } catch (error) { clear(body); body.appendChild(el("p", { class:"notice", text:L.errorMessage(error) })); }
  modal.querySelector(".source-modal-close").focus();
}
function ensureModal() {
  let modal=document.getElementById("source-modal"); if (modal) return modal;
  modal=el("div", { id:"source-modal", class:"modal source-modal", hidden:true, role:"dialog",
    "aria-modal":"true", "aria-labelledby":"source-modal-title" }, [el("div", { class:"source-modal-inner" }, [
      el("header", { class:"modal-head" }, [el("h2", { id:"source-modal-title", text:t("source_title") }),
        el("button", { class:"btn close source-modal-close", "aria-label":t("close"), text:"✕" })]),
      el("div", { class:"source-modal-body" })])]);
  document.body.appendChild(modal);
  const close=()=>{ modal.hidden=true; if (opener) opener.focus(); opener=null; };
  modal.querySelector(".source-modal-close").addEventListener("click",close);
  modal.addEventListener("click",event=>{ if (event.target===modal) close(); });
  modal.addEventListener("keydown",event=>{ if (event.key==="Escape") { event.preventDefault(); close(); } });
  return modal;
}
function render(root,structure,refs,evidence,xrefs) {
  clear(root);
  const reference=(refs.structure_sources||[]).find(row=>row.pdb_id===structure.pdb_id);
  const rows=(evidence.records||[]).filter(row=>row.pdb_id===structure.pdb_id);
  const ccds=new Set((structure.observations||[]).flatMap(row=>row.ligand_components||[]));
  const ligands=(xrefs.records||[]).filter(row=>ccds.has(row.ccd));
  root.appendChild(section(t("source_primary_citation"),reference?citation(reference):none()));
  root.appendChild(section(t("source_pathway_evidence"),evidenceTable(rows)));
  root.appendChild(section(t("source_ligand_xrefs"),ligandTable(ligands)));
  root.appendChild(section(t("source_database_links"),el("div", { class:"source-link-row" }, [
    sourceLink(reference&&reference.rcsb_entry,"RCSB PDB"),
    sourceLink(reference&&reference.gpcrdb_structure,"GPCRdb"),sourceLink(reference&&reference.pdb_doi,"PDB DOI")])));
}
function section(title,content) { return el("section", { class:"source-modal-section" }, [el("h3", { text:title }),content]); }
function none() { return el("p", { class:"muted", text:t("source_none") }); }
function sourceLink(href,label) { return href?el("a", { class:"btn", href,target:"_blank",rel:"noopener",text:label }):el("span"); }
function citation(reference) {
  const c=reference.primary_citation||{}, box=el("div", { class:"source-citation" }, [
    el("strong", { text:c.title||reference.title||reference.pdb_id }),el("p", { text:(c.authors||[]).join(", ") }),
    el("p", { class:"muted", text:[c.journal,c.year,c.volume,c.pages].filter(Boolean).join(" · ") })]);
  if (c.doi) box.appendChild(sourceLink("https://doi.org/"+c.doi,"DOI"));
  if (c.pubmed_id) box.appendChild(sourceLink("https://pubmed.ncbi.nlm.nih.gov/"+c.pubmed_id+"/","PubMed"));
  return box;
}
function evidenceTable(rows) {
  if (!rows.length) return none(); const table=el("table", { class:"data compact" });
  table.appendChild(el("thead", {}, el("tr", {}, [t("evidence_tier"),t("transducer"),t("evidence_result"),
    t("evidence_rationale")].map(x=>el("th", { text:x })))));
  table.appendChild(el("tbody", {}, rows.map(row=>el("tr", {}, [el("td", { text:row.tier }),
    el("td", { text:row.panel }),el("td", { text:row.result }),
    el("td", { text:row["rationale_"+getLang()]||row.rationale_en })])))); return table;
}
function ligandTable(rows) {
  if (!rows.length) return none(); const list=el("div", { class:"source-ligand-list" });
  for (const row of rows) { const links=[row.chembl,row.gtopdb,row.pubchem].filter(Boolean);
    list.appendChild(el("div", { class:"source-ligand-row" }, [el("strong", { text:row.ccd+" — "+(row.name||"") }),
      el("span", { class:"source-link-row" }, links.map(x=>sourceLink(x.url,(x.label||x.id)+(x.approximate?" ≈":""))))])); }
  return list;
}
