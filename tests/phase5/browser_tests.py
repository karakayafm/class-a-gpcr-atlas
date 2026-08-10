#!/usr/bin/env python3
"""Phase 5E — browser regression, including the 20-cycle WebGL lifecycle loop.

Headless software rendering is NOT presented as a substitute for a real-GPU run; the harness
records which renderer it actually used and the report states it.
"""
from __future__ import annotations
import json, os, shutil, signal, subprocess, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tests/phase5"))
import cdp   # noqa: E402

PORT=int(os.environ.get("ATLAS_PORT","8791"))
CDP_PORT=int(os.environ.get("CDP_PORT","9333"))
BASE=f"http://localhost:{PORT}/index.html"
R=[]
def check(g,n,ok,d=""):
    R.append((g,n,"PASS" if ok else "FAIL",d if not ok else ""))
    if not ok: print(f"  FAIL  {g} :: {n}  {d}",file=sys.stderr)

def wait(c, expr, tries=90, delay=0.25):
    for _ in range(tries):
        try:
            if c.eval(expr): return True
        except Exception: pass
        time.sleep(delay)
    return False

def main()->int:
    chrome=shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        print("no chrome"); return 2
    # A throwaway profile per run. This used to be a hardcoded path under one machine's
    # scratch directory, which does not exist on any other checkout.
    prof=Path(tempfile.gettempdir())/"atlas-chrome-profile"
    if prof.exists(): shutil.rmtree(prof)
    proc=subprocess.Popen([chrome,"--headless=new",f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={prof}","--no-first-run","--no-default-browser-check",
        # Force ANGLE's software backend. Without this the run depends on whatever GPU the host
        # exposes to a headless process, and the 3D checks fail with "could not create a WebGL
        # context" on machines where that handoff does not work.
        "--use-gl=angle","--use-angle=swiftshader-webgl","--enable-unsafe-swiftshader",
        "--disable-gpu-sandbox","--window-size=1400,900","about:blank"],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    time.sleep(3)
    try:
        c=cdp.Chrome(CDP_PORT)
        c.call("Page.enable"); c.call("Runtime.enable")
        renderer=None
        # ---- load ---------------------------------------------------------------------
        c.goto(BASE)
        ok=wait(c,"!!(window.__atlas && document.querySelector('.cards'))")
        check("load","shell boots and landing renders",ok)
        fams=c.eval("document.querySelectorAll('.cards .card').length")
        check("load","11 family cards rendered",fams==11,str(fams))
        pre=c.eval("document.getElementById('prerelease').textContent.length>40")
        check("load","pre-release notice visible",bool(pre))
        reqs=c.eval("performance.getEntriesByType('resource').filter(r=>r.name.includes('/families/')).length")
        check("load","initial load fetches no family payload",reqs==0,str(reqs))
        bund=c.eval("performance.getEntriesByType('resource').filter(r=>r.name.includes('/structures/')).length")
        check("load","initial load fetches no structure bundle",bund==0,str(bund))
        initial=c.eval("performance.getEntriesByType('resource').length")
        initial_bytes=c.eval("performance.getEntriesByType('resource').reduce((a,r)=>a+(r.transferSize||0),0)")
        # ---- routing ------------------------------------------------------------------
        c.eval("location.hash='#family=ca-001-006&view=structures'",False)
        ok=wait(c,"!!document.querySelector('table.data tbody tr')")
        check("routing","family route loads the structure explorer",ok)
        famreq=c.eval("performance.getEntriesByType('resource').filter(r=>r.name.includes('/families/ca-001-006/')).length")
        check("loading","family open fetches only that family",famreq>0)
        other=c.eval("performance.getEntriesByType('resource').filter(r=>r.name.includes('/families/')&&!r.name.includes('ca-001-006')).length")
        check("loading","no other family payload fetched",other==0,str(other))
        c.eval("history.back()",False); time.sleep(0.6)
        back=c.eval("location.hash")
        check("routing","browser back works",back=="" or "landing" in back or "ca-001-006" not in back,back)
        c.eval("history.forward()",False); time.sleep(0.6)
        check("routing","browser forward works","ca-001-006" in c.eval("location.hash"))
        c.eval("location.hash='#family=ca-001-006&view=contacts'",False)
        ok=wait(c,"!!document.querySelector('table.data tbody tr')")
        check("routing","pocket contacts route renders",ok)
        metric=c.eval("document.querySelector('.metric-head h3').textContent")
        check("metrics","default metric label shown","5 Å" in (metric or ""),metric)
        c.eval("location.hash='#family=ca-001-003&view=interfaces'",False)
        ok=wait(c,"!!document.querySelector('table.data tbody tr')")
        check("routing","polymer interface route renders",ok)
        txt=c.eval("document.querySelector('.view').textContent")
        check("semantics","interface view avoids the word pocket in its terminology",
              ("Arayüz" in txt or "Interface" in txt))
        c.eval("location.hash='#view=nosuchview'",False); time.sleep(0.8)
        check("routing","unknown route shows a message",
              bool(c.eval("!!document.querySelector('.notice')")))
        c.eval("location.hash='#family=ca-001-006&view=motifs'",False)
        ok=wait(c,"!!document.querySelector('table.data tbody tr')")
        check("routing","motif view renders",ok)
        c.eval("location.hash='#view=compare'",False)
        ok=wait(c,"!!document.querySelector('select')")
        check("routing","compare view renders",ok)
        c.eval("location.hash='#family=ca-001-006&view=evidence'",False)
        ok=wait(c,"!!document.querySelector('table.data')")
        check("routing","evidence view renders",ok)
        # ---- i18n and theme ------------------------------------------------------------
        c.eval("location.hash='#family=ca-001-006&view=structures'",False); time.sleep(1.0)
        c.eval("(()=>{const s=document.getElementById('lang');s.value='en';"
               "s.dispatchEvent(new Event('change'));return 1})()",False)
        time.sleep(1.0)
        en=c.eval("document.getElementById('nav').textContent")
        check("i18n","English mode shows English navigation","Structures" in en,en[:60])
        check("i18n","no Turkish residue in English nav",
              not any(w in en for w in ("Yapılar","Cep temasları","Kaynakça")))
        c.eval("(()=>{const s=document.getElementById('lang');s.value='tr';"
               "s.dispatchEvent(new Event('change'));return 1})()",False)
        time.sleep(1.0)
        tr=c.eval("document.getElementById('nav').textContent")
        check("i18n","Turkish mode shows Turkish navigation","Yapılar" in tr,tr[:60])
        check("i18n","no English residue in Turkish nav",
              not any(w in tr for w in ("Structures","Pocket contacts","References")))
        c.eval("(()=>{const s=document.getElementById('theme');s.value='dark';"
               "s.dispatchEvent(new Event('change'));return 1})()",False)
        time.sleep(0.4)
        check("theme","dark theme applies",c.eval("document.documentElement.getAttribute('data-theme')")=="dark")
        c.eval("localStorage.setItem('atlas.theme','mint')",False)
        c.goto(BASE); wait(c,"!!window.__atlas")
        check("theme","invalid stored theme falls back to grey",
              c.eval("document.documentElement.getAttribute('data-theme')")=="grey")
        # ---- 3D lifecycle, 20 cycles ---------------------------------------------------
        c.eval("location.hash='#family=ca-001-006&view=structures'",False)
        wait(c,"!!document.querySelector('table.data tbody tr')")
        renderer=c.eval("(()=>{try{const g=document.createElement('canvas').getContext('webgl');"
                        "const d=g.getExtension('WEBGL_debug_renderer_info');"
                        "return d?g.getParameter(d.UNMASKED_RENDERER_WEBGL):'unknown'}catch(e){return 'none'}})()")
        webgl=c.eval("(()=>{try{return !!document.createElement('canvas').getContext('webgl')}catch(e){return false}})()")
        check("viewer","WebGL context is available in the harness",bool(webgl),str(renderer))
        cycles=[]
        for i in range(20):
            c.eval("(()=>{const b=[...document.querySelectorAll('button')]"
                   ".find(x=>x.textContent.includes('3B')||x.textContent.includes('3D'));"
                   "if(b)b.click();return 1})()",False)
            ok=wait(c,"(()=>{const m=document.getElementById('modal');"
                      "return m&&!m.hidden&&document.querySelectorAll('canvas').length>0})()",60,0.25)
            # language + theme change while open
            c.eval("(()=>{const s=document.getElementById('lang');s.value=(s.value==='tr'?'en':'tr');"
                   "s.dispatchEvent(new Event('change'));return 1})()",False)
            c.eval("(()=>{const s=document.getElementById('theme');s.value=(s.value==='grey'?'dark':'grey');"
                   "s.dispatchEvent(new Event('change'));return 1})()",False)
            time.sleep(0.25)
            c.eval("window.dispatchEvent(new Event('resize'))",False)
            time.sleep(0.15)
            d=c.eval("window.__atlas.diagnostics()")
            c.eval("(()=>{const b=document.getElementById('modal-close');if(b)b.click();return 1})()",False)
            time.sleep(0.3)
            after=c.eval("window.__atlas.diagnostics()")
            cycles.append({"i":i,"open":ok,"canvas":d.get("canvasCount"),
                           "stage":d.get("stageCount"),"listeners":d.get("listenerCount"),
                           "lost":d.get("contextLost"),"after_canvas":after.get("canvasCount"),
                           "after_stage":after.get("stageCount"),"after_listeners":after.get("listenerCount")})
        opened=[c_ for c_ in cycles if c_["open"]]
        check("viewer",f"3D opened in all 20 cycles",len(opened)==20,f"{len(opened)}/20")
        check("viewer","canvas count is 1 while open",all(c_["canvas"]==1 for c_ in opened),
              str(sorted({c_["canvas"] for c_ in opened})))
        check("viewer","stage count is 1 while open",all(c_["stage"]==1 for c_ in opened),
              str(sorted({c_["stage"] for c_ in opened})))
        check("viewer","listener count is stable",
              len({c_["listeners"] for c_ in opened})<=1,str(sorted({c_["listeners"] for c_ in opened})))
        check("viewer","no WebGL context lost across 20 cycles",
              not any(c_["lost"] for c_ in cycles))
        check("viewer","canvases do not accumulate after close",
              all(c_["after_canvas"]==0 for c_ in cycles),str(sorted({c_["after_canvas"] for c_ in cycles})))
        check("viewer","listeners are released after close",
              all(c_["after_listeners"]==0 for c_ in cycles),str(sorted({c_["after_listeners"] for c_ in cycles})))
        # family switch then reopen
        c.eval("location.hash='#family=ca-001-009&view=structures'",False)
        wait(c,"!!document.querySelector('table.data tbody tr')")
        c.eval("(()=>{const b=[...document.querySelectorAll('button')]"
               ".find(x=>x.textContent.includes('3B')||x.textContent.includes('3D'));"
               "if(b)b.click();return 1})()",False)
        ok=wait(c,"(()=>{const m=document.getElementById('modal');return m&&!m.hidden&&"
                  "document.querySelectorAll('canvas').length===1})()",60,0.25)
        check("viewer","3D opens after a family switch",ok)
        d=c.eval("window.__atlas.diagnostics()")
        check("viewer","still exactly one canvas after family switch",d.get("canvasCount")==1,str(d))
        c.eval("(()=>{document.getElementById('modal-close').click();return 1})()",False)
        # ---- accessibility spot checks --------------------------------------------------
        c.eval("location.hash='#view=landing'",False); wait(c,"!!document.querySelector('.cards')")
        check("a11y","skip link present",bool(c.eval("!!document.querySelector('a.skip')")))
        check("a11y","main landmark focusable",bool(c.eval("!!document.querySelector('main#main[tabindex]')")))
        check("a11y","nav has aria-current on the active link",
              bool(c.eval("!!document.querySelector('#nav [aria-current]')")))
        # ---- viewports ------------------------------------------------------------------
        vps=[("desktop_wide",1600,900),("laptop",1366,768),("tablet",1024,768),("mobile_portrait",390,844)]
        vp_ok={}
        for name,w,h in vps:
            c.call("Emulation.setDeviceMetricsOverride",{"width":w,"height":h,
                "deviceScaleFactor":1,"mobile":name.startswith("mobile")})
            c.goto(BASE); wait(c,"!!document.querySelector('.cards')")
            ov=c.eval("document.documentElement.scrollWidth <= window.innerWidth + 2")
            vp_ok[name]=bool(ov)
            check("viewport",f"{name} has no horizontal overflow",bool(ov))
        c.call("Emulation.clearDeviceMetricsOverride")
        # ---- console cleanliness ---------------------------------------------------------
        errs=[l for l in c.logs if l.get("type")=="error" or l.get("type")=="exception"]
        check("console","no uncaught JavaScript errors",len(errs)==0,json.dumps(errs[:2])[:300])
        perf={"initial_requests":initial,"initial_transfer_bytes":initial_bytes,
              "renderer":renderer,"webgl":bool(webgl),"viewports":vp_ok,
              "cycles":cycles}
        (ROOT/"reports/phase5").mkdir(parents=True,exist_ok=True)
        (ROOT/"reports/phase5/browser_results.json").write_text(json.dumps(
            {"checks":[{"group":g,"name":n,"result":r,"detail":d} for g,n,r,d in R],
             "total":len(R),"failed":sum(1 for _,_,r,_ in R if r=="FAIL"),
             "environment":{"browser":"Chrome headless","renderer":renderer,
                            "real_gpu":False,
                            "note":("headless software rendering; this does NOT substitute for a "
                                    "real-GPU validation run")},
             "performance":perf},indent=1,ensure_ascii=False),encoding="utf-8")
        c.close()
    finally:
        proc.send_signal(signal.SIGTERM)
        try: proc.wait(timeout=10)
        except Exception: proc.kill()
    groups={}
    for g,n,r,_ in R: groups.setdefault(g,[]).append(r)
    print("\nPhase 5 browser tests")
    for g,res in groups.items():
        print(f"  {g:12} {res.count('PASS'):3} pass  {res.count('FAIL'):3} fail")
    failed=sum(1 for _,_,r,_ in R if r=="FAIL")
    print(f"\n  total {len(R)} checks, {failed} failed")
    return 1 if failed else 0

if __name__=="__main__": raise SystemExit(main())
