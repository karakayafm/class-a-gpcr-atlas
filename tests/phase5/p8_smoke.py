#!/usr/bin/env python3
"""Focused P8 browser smoke checks; expects atlas on 8791 and Chrome CDP on 9334."""
from __future__ import annotations
import json, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import cdp

def wait(c,expr,tries=80):
    for _ in range(tries):
        try:
            if c.eval(expr): return True
        except Exception: pass
        time.sleep(.25)
    return False

def main()->int:
    c=cdp.Chrome(9334); c.call("Page.enable"); c.call("Runtime.enable"); result={}
    for pdb in ("6MXT","9IJE"):
        c.goto(f"http://localhost:8791/index.html#family=ca-001-001&view=structures&pdb={pdb}")
        result[pdb+"_structure"]=wait(c,f"document.querySelector('.detail-title strong')?.textContent==='{pdb}'")
        c.eval("document.querySelector('.detail-section.sources button').click()",False)
        result[pdb+"_modal"]=wait(c,"!document.getElementById('source-modal').hidden && document.querySelectorAll('.source-modal-section').length===4")
        result[pdb+"_sections"]=c.eval("Array.from(document.querySelectorAll('.source-modal-section')).map(x=>x.textContent.trim().length>0)")
        c.eval("document.querySelector('.source-modal-close').click()",False)
    for pdb,slug in (("7XOX","ca-001-002"),("8ZFJ","ca-001-010")):
        c.goto(f"http://localhost:8791/index.html#family={slug}&view=structures&pdb={pdb}")
        result[pdb+"_visible"]=wait(c,f"document.querySelector('.detail-title strong')?.textContent==='{pdb}'")
        result[pdb+"_notice"]=wait(c,"!!document.querySelector('.superseded-notice')")
        result[pdb+"_holdings"]=c.eval("document.querySelector('.superseded-notice a')?.href.includes('/holdings/removed/') || false")
    root=Path(__file__).resolve().parents[2]
    structures=json.loads((root/"data/web/families/ca-001-001/structures.json").read_text())["structures"]
    c.goto("http://localhost:8791/index.html#family=ca-001-001&view=structures")
    result["panel_strip"]=wait(c,"document.querySelectorAll('.family-panel-tab').length>=2")
    expected_gs=sum("Gs" in row.get("transducer_panels",[]) for row in structures)
    c.eval("document.querySelector('.family-panel-tab[data-panel=\"Gs\"]').click()",False)
    result["transducer_filter"]=wait(c,f"document.querySelectorAll('.result-item').length==={expected_gs}")
    expected_b=sum("B" in row.get("pathway_evidence_tiers",[]) and
                   "Gs" in row.get("transducer_panels",[]) for row in structures)
    c.eval("const s=document.querySelectorAll('.filter-grid select')[6];s.value='B';s.dispatchEvent(new Event('change',{bubbles:true}))",False)
    result["evidence_filter"]=wait(c,f"document.querySelectorAll('.result-item').length==={expected_b}")
    result["errors"]=[x for x in c.logs if x.get("type") in ("error","exception")]
    print(json.dumps(result,ensure_ascii=False,indent=2))
    ok=all(v is True or (isinstance(v,list) and all(v)) for k,v in result.items() if k!="errors") and not result["errors"]
    return 0 if ok else 1
if __name__=="__main__": raise SystemExit(main())
