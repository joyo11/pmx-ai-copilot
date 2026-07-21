import Link from "next/link";

// PMX AI landing — implemented from the Claude Design handoff (PMX AI.dc.html):
// warm rounded display type (Fredoka), navy + teal palette, animated reveals.
// "See a live demo" enters the real, API-wired app at /dashboard.

const TOKENS = `
#pmx-landing{
  --brand:#003A70; --brand-deep:#002A52;
  --bg:#071F3A; --surface:#0E2A4B; --surface-2:#143458; --surface-3:#1B3E63;
  --border:#1F4269; --border-strong:#2C5580;
  --text:#EAF2FB; --text-2:#A6BED7; --text-3:#6E88A2;
  --accent:#3B93F0; --accent-2:#63AAF6; --accent-soft:rgba(59,147,240,.16); --accent-border:rgba(59,147,240,.4); --on-accent:#fff;
  --teal:#2FE3C9; --teal-border:rgba(47,227,201,.4);
  --r-elevated:#F5893D; --r-elevated-soft:rgba(245,137,61,.15); --r-critical:#F65563; --r-healthy:#35C97F; --r-watch:#F2B233;
  --shadow:0 1px 2px rgba(0,10,25,.5), 0 10px 30px rgba(0,10,25,.35);
  --shadow-lg:0 30px 70px rgba(0,8,20,.6);
  --font-d:var(--font-display,'Fredoka',system-ui,sans-serif);
  --font-b:var(--font-body,'Nunito',system-ui,sans-serif);
  background:var(--bg); color:var(--text); font-family:var(--font-b); -webkit-font-smoothing:antialiased; min-height:100vh;
}
#pmx-landing a{ text-decoration:none; }
#pmx-landing .pmx-btn{ transition:transform .15s ease, filter .15s ease, background .15s ease; }
#pmx-landing .pmx-btn:hover{ filter:brightness(1.06); transform:translateY(-1px); }
#pmx-landing .pmx-card{ transition:transform .15s ease, border-color .15s ease; }
#pmx-landing .pmx-card:hover{ transform:translateY(-3px); border-color:var(--border-strong); }
@keyframes pmxUp{ from{opacity:0; transform:translateY(14px);} to{opacity:1; transform:none;} }
@media (max-width:860px){
  #pmx-landing .pmx-hero-grid, #pmx-landing .pmx-2col{ grid-template-columns:1fr !important; }
  #pmx-landing .pmx-3col{ grid-template-columns:1fr !important; }
  #pmx-landing h1{ font-size:42px !important; }
}
`;

const STEPS = [
  { n: "1", title: "Connect your docs", body: "Drop in schedules, budgets, RFI logs, and meeting notes. We ingest P6, MS Project, Excel, PDF, and DOCX exports, no migration required." },
  { n: "2", title: "AI scores & flags risk", body: "PMX AI computes a live health score and ranks the risks, budget overruns, schedule slips, overdue RFIs, each quantified in dollars and days." },
  { n: "3", title: "Ask anything, cited", body: "Ask in plain English. Every answer is grounded in your documents and cites the exact source page, so you can trust it and verify it." },
];

const STATS = [
  { label: "Health score", value: "43", color: "var(--r-elevated)", sub: "at risk" },
  { label: "Over budget", value: "10.4%", color: "var(--r-critical)", sub: "+$4.99M" },
  { label: "Schedule slip", value: "11 wks", color: "var(--r-critical)", sub: "$924K LD exposure" },
  { label: "Open risks", value: "8", color: "var(--r-watch)", sub: "3 critical" },
];

export default function Landing() {
  return (
    <div id="pmx-landing">
      <style dangerouslySetInnerHTML={{ __html: TOKENS }} />

      {/* nav */}
      <div style={{ position: "sticky", top: 0, zIndex: 40, background: "var(--brand)", borderBottom: "1px solid rgba(255,255,255,.08)" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "16px 28px", display: "flex", alignItems: "center", gap: 30 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 11, color: "#fff" }}>
            <Logo />
            <div style={{ fontFamily: "var(--font-d)", fontWeight: 700, fontSize: 20, letterSpacing: "-0.01em" }}>PMX<span style={{ color: "#2FE3C9" }}>AI</span></div>
          </div>
          <div style={{ display: "flex", gap: 26, marginLeft: 6, color: "rgba(255,255,255,.82)", fontSize: 14.5, fontWeight: 500, fontFamily: "var(--font-d)" }} className="pmx-nav-links">
            <a href="#how" style={{ color: "inherit" }}>How it works</a>
            <a href="#preview" style={{ color: "inherit" }}>Sample project</a>
            <a href="#trust" style={{ color: "inherit" }}>Integrations</a>
          </div>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 14 }}>
            <Link href="/dashboard" className="pmx-btn" style={{ padding: "11px 20px", borderRadius: 999, background: "var(--accent)", color: "var(--on-accent)", fontWeight: 700, fontSize: 14.5, fontFamily: "var(--font-d)" }}>See a live demo</Link>
          </div>
        </div>
      </div>

      {/* hero */}
      <div style={{ background: "var(--brand)", color: "#fff", position: "relative", overflow: "hidden" }}>
        <svg viewBox="0 0 600 600" preserveAspectRatio="none" style={{ position: "absolute", right: -60, top: -40, width: 640, height: 680, opacity: 0.5 }}>
          <path d="M120 60 320 300 120 540" fill="none" stroke="#2FE3C9" strokeWidth="3" />
          <path d="M300 60 500 300 300 540" fill="none" stroke="rgba(59,147,240,.7)" strokeWidth="3" />
        </svg>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "78px 28px 90px", display: "grid", gridTemplateColumns: "1.05fr .95fr", gap: 52, alignItems: "center", position: "relative" }} className="pmx-hero-grid">
          <div style={{ animation: "pmxUp .6s ease both" }}>
            <div style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "6px 13px", borderRadius: 999, background: "rgba(47,227,201,.14)", border: "1px solid var(--teal-border)", color: "#2FE3C9", fontSize: 12.5, fontWeight: 600, marginBottom: 22, fontFamily: "var(--font-d)" }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#2FE3C9" }} /> Built for construction project managers
            </div>
            <h1 style={{ fontFamily: "var(--font-d)", fontWeight: 700, fontSize: 60, lineHeight: 1.03, letterSpacing: "-0.02em", margin: "0 0 20px" }}>See risk before it <span style={{ color: "#4BA3F5" }}>costs you.</span></h1>
            <p style={{ fontSize: 18, lineHeight: 1.55, color: "rgba(255,255,255,.8)", margin: "0 0 32px", maxWidth: 490 }}>PMX AI reads your schedules, budgets, RFIs, and meeting notes, then tells you which projects are slipping, why, and what to do next. Grounded in your documents. <span style={{ color: "#fff", fontWeight: 600 }}>Cited every time.</span></p>
            <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
              <Link href="/dashboard" className="pmx-btn" style={{ padding: "15px 26px", borderRadius: 999, background: "var(--accent)", color: "var(--on-accent)", fontWeight: 700, fontSize: 15.5, fontFamily: "var(--font-d)", display: "inline-flex", alignItems: "center", gap: 9 }}>See a live demo <span style={{ fontWeight: 800 }}>→</span></Link>
              <a href="#how" className="pmx-btn" style={{ padding: "15px 24px", borderRadius: 999, background: "rgba(255,255,255,.08)", border: "1px solid rgba(255,255,255,.22)", color: "#fff", fontWeight: 600, fontSize: 15.5, fontFamily: "var(--font-d)" }}>Watch how it works</a>
            </div>
            <div style={{ marginTop: 28, display: "flex", alignItems: "center", gap: 9, color: "rgba(255,255,255,.62)", fontSize: 13 }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none"><path d="M20 6 9 17l-5-5" stroke="#2FE3C9" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
              No black-box scores, every number traces back to a source page.
            </div>
          </div>

          {/* product card */}
          <div style={{ animation: "pmxUp .7s ease .1s both" }}>
            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 20, padding: 22, boxShadow: "var(--shadow-lg)", color: "var(--text)" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
                <div>
                  <div style={{ fontSize: 11.5, color: "var(--text-3)", fontWeight: 700, letterSpacing: ".04em", textTransform: "uppercase" }}>Project health</div>
                  <div style={{ fontFamily: "var(--font-d)", fontWeight: 700, fontSize: 15, marginTop: 3 }}>Northshore Medical Center</div>
                </div>
                <div style={{ padding: "5px 12px", borderRadius: 999, background: "var(--r-elevated-soft)", color: "var(--r-elevated)", fontSize: 12, fontWeight: 700 }}>At risk</div>
              </div>
              <div style={{ display: "flex", gap: 20, alignItems: "center" }}>
                <div style={{ position: "relative", width: 120, height: 120, flex: "none" }}>
                  <svg width="120" height="120" viewBox="0 0 120 120" style={{ transform: "rotate(-90deg)" }}>
                    <circle cx="60" cy="60" r="50" fill="none" stroke="var(--surface-3)" strokeWidth="11" />
                    <circle cx="60" cy="60" r="50" fill="none" stroke="var(--r-elevated)" strokeWidth="11" strokeLinecap="round" strokeDasharray="314.16" strokeDashoffset="179" />
                  </svg>
                  <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                    <div style={{ fontFamily: "var(--font-d)", fontWeight: 700, fontSize: 38, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>43</div>
                    <div style={{ fontSize: 11, color: "var(--text-3)", fontWeight: 600 }}>/ 100</div>
                  </div>
                </div>
                <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 9 }}>
                  {[
                    { c: "var(--r-critical)", t: "$924K liquidated-damages exposure" },
                    { c: "var(--r-critical)", t: "10.4% over budget (+$4.99M)" },
                    { c: "var(--r-elevated)", t: "7 RFIs overdue > 21 days" },
                  ].map((r, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 9, padding: "9px 11px", borderRadius: 10, background: "var(--surface-2)", border: "1px solid var(--border)" }}>
                      <span style={{ width: 7, height: 7, borderRadius: "50%", background: r.c, flex: "none" }} />
                      <span style={{ fontSize: 12.5, fontWeight: 500 }}>{r.t}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div style={{ marginTop: 16, padding: "12px 14px", borderRadius: 12, background: "var(--accent-soft)", border: "1px solid var(--accent-border)", display: "flex", gap: 10 }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" style={{ flex: "none", marginTop: 1 }}><path d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z" stroke="var(--accent)" strokeWidth="1.6" /><path d="M12 8v5M12 16h.01" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" /></svg>
                <div style={{ fontSize: 12.5, lineHeight: 1.5, color: "var(--text-2)" }}><span style={{ color: "var(--text)", fontWeight: 600 }}>AI summary:</span> Schedule slip is the dominant driver. File a time-impact analysis this week to protect the LD position.</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* trust strip */}
      <div id="trust" style={{ maxWidth: 1200, margin: "0 auto", padding: "22px 28px", display: "flex", alignItems: "center", gap: 28, flexWrap: "wrap", borderBottom: "1px solid var(--border)" }}>
        <span style={{ fontSize: 13, color: "var(--text-3)", fontWeight: 600 }}>Works with what you already use</span>
        <div style={{ display: "flex", gap: 26, flexWrap: "wrap", color: "var(--text-2)", fontWeight: 600, fontSize: 14.5, fontFamily: "var(--font-d)" }}>
          {["Primavera P6", "Microsoft Project", "Excel", "PDF", "DOCX", "Procore"].map((x) => <span key={x}>{x}</span>)}
        </div>
      </div>

      {/* how it works */}
      <div id="how" style={{ maxWidth: 1200, margin: "0 auto", padding: "82px 28px 34px" }}>
        <div style={{ textAlign: "center", marginBottom: 46 }}>
          <div style={{ fontSize: 13, color: "var(--accent)", fontWeight: 700, letterSpacing: ".05em", textTransform: "uppercase", marginBottom: 12 }}><span style={{ color: "var(--teal)" }}>→</span> How it works</div>
          <h2 style={{ fontFamily: "var(--font-d)", fontWeight: 700, fontSize: 38, letterSpacing: "-0.02em", margin: 0 }}>From messy documents to a decision, in three steps</h2>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 22 }} className="pmx-3col">
          {STEPS.map((s) => (
            <div key={s.n} className="pmx-card" style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 18, padding: 26, boxShadow: "var(--shadow)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 15 }}>
                <div style={{ width: 36, height: 36, borderRadius: 10, background: "var(--accent-soft)", border: "1px solid var(--accent-border)", color: "var(--accent)", fontFamily: "var(--font-d)", fontWeight: 700, fontSize: 16, display: "flex", alignItems: "center", justifyContent: "center" }}>{s.n}</div>
                <div style={{ fontFamily: "var(--font-d)", fontWeight: 700, fontSize: 19, letterSpacing: "-0.01em" }}>{s.title}</div>
              </div>
              <p style={{ margin: 0, color: "var(--text-2)", fontSize: 14.5, lineHeight: 1.6 }}>{s.body}</p>
            </div>
          ))}
        </div>
      </div>

      {/* sample preview */}
      <div id="preview" style={{ maxWidth: 1200, margin: "0 auto", padding: "56px 28px 30px" }}>
        <div style={{ background: "linear-gradient(160deg, var(--surface), var(--surface-2))", border: "1px solid var(--border)", borderRadius: 22, padding: 38, display: "grid", gridTemplateColumns: ".9fr 1.1fr", gap: 40, alignItems: "center", boxShadow: "var(--shadow)" }} className="pmx-2col">
          <div>
            <div style={{ fontSize: 13, color: "var(--accent)", fontWeight: 700, letterSpacing: ".04em", textTransform: "uppercase", marginBottom: 14 }}><span style={{ color: "var(--teal)" }}>→</span> See it on real work</div>
            <h3 style={{ fontFamily: "var(--font-d)", fontWeight: 700, fontSize: 29, letterSpacing: "-0.02em", margin: "0 0 14px" }}>A $48M hospital, read in seconds</h3>
            <p style={{ margin: "0 0 22px", color: "var(--text-2)", fontSize: 15, lineHeight: 1.6 }}>Northshore Medical Center&apos;s bed-tower expansion is 11 weeks behind and 10.4% over. PMX AI ranked the risks, quantified the exposure, and cited every claim to a source page.</p>
            <Link href="/dashboard" className="pmx-btn" style={{ display: "inline-block", padding: "13px 22px", borderRadius: 999, background: "var(--accent)", color: "var(--on-accent)", fontWeight: 600, fontSize: 15, fontFamily: "var(--font-d)", boxShadow: "0 8px 22px var(--accent-soft)" }}>Open the seeded demo →</Link>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2,1fr)", gap: 14 }}>
            {STATS.map((p) => (
              <div key={p.label} style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 14, padding: "16px 18px" }}>
                <div style={{ fontSize: 12, color: "var(--text-3)", fontWeight: 600, marginBottom: 8 }}>{p.label}</div>
                <div style={{ fontFamily: "var(--font-d)", fontWeight: 700, fontSize: 26, fontVariantNumeric: "tabular-nums", color: p.color }}>{p.value}</div>
                <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 4 }}>{p.sub}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* quote */}
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "46px 28px" }}>
        <div style={{ border: "1px solid var(--border)", borderRadius: 20, padding: "38px 40px", background: "var(--surface)", textAlign: "center", boxShadow: "var(--shadow)" }}>
          <div style={{ fontFamily: "var(--font-d)", fontWeight: 600, fontSize: 24, lineHeight: 1.45, letterSpacing: "-0.01em", maxWidth: 760, margin: "0 auto 20px" }}>&ldquo;I used to find out a project was slipping in the monthly OAC. Now I know the morning it happens, with the receipts already attached.&rdquo;</div>
          <div style={{ color: "var(--text-2)", fontSize: 14 }}>Director of Project Controls · regional healthcare GC</div>
        </div>
      </div>

      {/* CTA band */}
      <div style={{ maxWidth: 1200, margin: "0 auto 24px", padding: "0 28px" }}>
        <div style={{ borderRadius: 24, padding: "56px 40px", textAlign: "center", background: "linear-gradient(140deg, var(--brand-deep), var(--brand) 55%, #0B5AA8)", color: "#fff", position: "relative", overflow: "hidden", boxShadow: "var(--shadow-lg)" }}>
          <svg viewBox="0 0 400 400" preserveAspectRatio="none" style={{ position: "absolute", left: -30, top: -20, width: 360, height: 440, opacity: 0.35 }}><path d="M80 40 240 200 80 360" fill="none" stroke="#2FE3C9" strokeWidth="3" /></svg>
          <h2 style={{ position: "relative", fontFamily: "var(--font-d)", fontWeight: 700, fontSize: 40, letterSpacing: "-0.02em", margin: "0 0 14px" }}>Ready to see risk before it costs you?</h2>
          <p style={{ position: "relative", margin: "0 auto 26px", fontSize: 16, opacity: 0.85, maxWidth: 520 }}>Drop into a fully seeded demo project, no setup required.</p>
          <Link href="/dashboard" className="pmx-btn" style={{ position: "relative", display: "inline-block", padding: "15px 30px", borderRadius: 999, background: "var(--accent)", color: "var(--on-accent)", fontWeight: 700, fontSize: 16, fontFamily: "var(--font-d)", boxShadow: "0 12px 30px rgba(0,0,0,.28)" }}>See a live demo →</Link>
        </div>
      </div>

      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "26px 28px 46px", color: "var(--text-3)", fontSize: 12.5, display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <span>PMX AI · Project Risk Copilot</span>
        <span>Portfolio demo · brand styling inspired by Group PMX · not affiliated</span>
      </div>
    </div>
  );
}

function Logo() {
  return (
    <div style={{ width: 34, height: 34, borderRadius: 10, background: "linear-gradient(150deg,#1E7FE0,#0B4E9E)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="m7 5 7 7-7 7" stroke="#2FE3C9" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /><path d="m13 5 4 4-1 3" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </div>
  );
}
