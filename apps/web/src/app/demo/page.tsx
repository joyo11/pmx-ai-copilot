"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  getDemoBundle,
  postDemoChat,
  type DemoBundle,
  type DemoChatCitation,
} from "@/lib/demo-api";

// Public, no-login demo of the seeded Northshore project. Deliberately does NOT
// use Clerk/useAuth — it lives outside the (app) themed layout, so it inlines
// the navy design tokens itself.

const TOKENS = `
#pmx-demo{
  --bg:#071F3A; --card:#0E2A4B; --surface-2:#143458; --surface-3:#1B3E63;
  --border:#1F4269; --border-strong:#2C5580;
  --text:#EAF2FB; --muted:#A6BED7; --text-3:#6E88A2;
  --accent:#3B93F0; --accent-2:#63AAF6; --accent-soft:rgba(59,147,240,.16); --accent-border:rgba(59,147,240,.4);
  --teal:#2FE3C9; --teal-soft:rgba(47,227,201,.14); --teal-border:rgba(47,227,201,.4);
  --r-healthy:#35C97F; --r-watch:#F2B233; --r-elevated:#F5893D; --r-critical:#F65563;
  --shadow:0 1px 2px rgba(0,10,25,.5), 0 10px 30px rgba(0,10,25,.35);
  --font-d:var(--font-display,'Fredoka',system-ui,sans-serif);
  --font-b:var(--font-body,'Nunito',system-ui,sans-serif);
  background:var(--bg); color:var(--text); font-family:var(--font-b);
  -webkit-font-smoothing:antialiased; min-height:100vh;
}
#pmx-demo a{ text-decoration:none; }
#pmx-demo .pmx-btn{ transition:transform .15s ease, filter .15s ease; }
#pmx-demo .pmx-btn:hover{ filter:brightness(1.07); transform:translateY(-1px); }
#pmx-demo .pmx-card{ transition:border-color .15s ease, transform .15s ease; }
#pmx-demo input::placeholder{ color:var(--text-3); }
@keyframes pmxUp{ from{opacity:0; transform:translateY(12px);} to{opacity:1; transform:none;} }
@keyframes pmxPulse{ 0%,100%{opacity:.4;} 50%{opacity:1;} }
@media (max-width:900px){
  #pmx-demo .pmx-2col{ grid-template-columns:1fr !important; }
  #pmx-demo .pmx-stats{ flex-wrap:wrap !important; }
}
@media (max-width:640px){
  #pmx-demo .pmx-topbar-inner{ padding:12px 16px !important; gap:10px !important; }
  #pmx-demo .pmx-page{ padding:24px 16px 56px !important; }
  #pmx-demo .pmx-h1{ font-size:28px !important; }
  #pmx-demo .pmx-back{ display:none !important; }
  #pmx-demo .pmx-card{ padding:18px !important; }
}
`;

const SEVERITY = {
  5: { color: "var(--r-critical)", label: "Critical" },
  4: { color: "var(--r-elevated)", label: "Elevated" },
  3: { color: "var(--r-watch)", label: "Watch" },
  2: { color: "var(--r-healthy)", label: "Low" },
  1: { color: "var(--r-healthy)", label: "Low" },
} as const;

function sev(severity: number) {
  return SEVERITY[(severity as 1 | 2 | 3 | 4 | 5)] ?? SEVERITY[3];
}

function usd(cents: number | null | undefined): string {
  if (cents == null) return "—";
  const m = cents / 100 / 1_000_000;
  return `$${m.toFixed(1)}M`;
}

function weeksBetween(a: string | null, b: string | null): number | null {
  if (!a || !b) return null;
  const da = new Date(a).getTime();
  const db = new Date(b).getTime();
  if (Number.isNaN(da) || Number.isNaN(db)) return null;
  return Math.round((db - da) / (1000 * 60 * 60 * 24 * 7));
}

interface ChatTurn {
  role: "user" | "assistant";
  text: string;
  citations?: DemoChatCitation[];
}

export default function DemoPage() {
  const [bundle, setBundle] = useState<DemoBundle | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [sending, setSending] = useState(false);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    getDemoBundle(ctrl.signal)
      .then(setBundle)
      .catch((e) => {
        if (ctrl.signal.aborted) return;
        setLoadError(
          "The demo backend is waking up (free tier can take ~30s). Refresh in a moment."
        );
        console.error(e);
      });
    return () => ctrl.abort();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, sending]);

  const slipWeeks = useMemo(
    () =>
      bundle?.project
        ? weeksBetween(
            bundle.project.planned_end_date,
            bundle.project.forecast_end_date
          )
        : null,
    [bundle]
  );

  async function ask(question: string) {
    const q = question.trim();
    if (!q || sending) return;
    setInput("");
    setTurns((t) => [...t, { role: "user", text: q }]);
    setSending(true);
    try {
      const res = await postDemoChat(q);
      setTurns((t) => [
        ...t,
        { role: "assistant", text: res.answer, citations: res.citations },
      ]);
    } catch (e) {
      console.error(e);
      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          text: "Something went wrong reaching the assistant. Please try again in a moment.",
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  const project = bundle?.project ?? null;
  const health = bundle?.health ?? null;
  const risks = bundle?.risks ?? [];
  const documents = bundle?.documents ?? [];
  const score = health?.score ?? project?.health_score ?? 43;

  return (
    <div id="pmx-demo">
      <style dangerouslySetInnerHTML={{ __html: TOKENS }} />

      {/* top bar */}
      <div
        style={{
          position: "sticky",
          top: 0,
          zIndex: 40,
          background: "#003A70",
          borderBottom: "1px solid rgba(255,255,255,.08)",
        }}
      >
        <div
          className="pmx-topbar-inner"
          style={{
            maxWidth: 1160,
            margin: "0 auto",
            padding: "14px 26px",
            display: "flex",
            alignItems: "center",
            gap: 14,
          }}
        >
          <Link
            href="/"
            style={{ display: "flex", alignItems: "center", gap: 11, color: "#fff" }}
          >
            <Logo />
            <div
              style={{
                fontFamily: "var(--font-d)",
                fontWeight: 700,
                fontSize: 19,
                letterSpacing: "-0.01em",
              }}
            >
              PMX<span style={{ color: "var(--teal)" }}>AI</span>
            </div>
          </Link>
          <div
            style={{
              padding: "4px 11px",
              borderRadius: 999,
              background: "var(--teal-soft)",
              border: "1px solid var(--teal-border)",
              color: "var(--teal)",
              fontSize: 12,
              fontWeight: 700,
              fontFamily: "var(--font-d)",
            }}
          >
            Live demo
          </div>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
            <Link
              href="/"
              className="pmx-back"
              style={{ color: "rgba(255,255,255,.78)", fontSize: 14, fontWeight: 600, fontFamily: "var(--font-d)" }}
            >
              Back to home
            </Link>
            <Link
              href="/dashboard"
              className="pmx-btn"
              style={{
                padding: "9px 17px",
                borderRadius: 999,
                background: "var(--accent)",
                color: "#fff",
                fontWeight: 700,
                fontSize: 14,
                fontFamily: "var(--font-d)",
              }}
            >
              Sign up
            </Link>
          </div>
        </div>
      </div>

      <div className="pmx-page" style={{ maxWidth: 1160, margin: "0 auto", padding: "34px 26px 70px" }}>
        {loadError && !project && (
          <div
            style={{
              background: "var(--card)",
              border: "1px solid var(--border)",
              borderRadius: 16,
              padding: "40px 28px",
              textAlign: "center",
              color: "var(--muted)",
              fontSize: 15,
            }}
          >
            {loadError}
          </div>
        )}

        {!bundle && !loadError && (
          <div
            style={{
              padding: "80px 0",
              textAlign: "center",
              color: "var(--text-3)",
              fontFamily: "var(--font-d)",
              fontWeight: 600,
              animation: "pmxPulse 1.4s ease-in-out infinite",
            }}
          >
            Loading the seeded project…
          </div>
        )}

        {project && (
          <div style={{ animation: "pmxUp .5s ease both" }}>
            {/* project header */}
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 13px",
                borderRadius: 999,
                background: "rgba(245,137,61,.15)",
                border: "1px solid rgba(245,137,61,.4)",
                color: "var(--r-elevated)",
                fontSize: 12.5,
                fontWeight: 700,
                fontFamily: "var(--font-d)",
                marginBottom: 16,
              }}
            >
              <span
                style={{
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
                  background: "var(--r-elevated)",
                }}
              />
              At risk · Health {score}
            </div>

            <div
              style={{
                fontSize: 13.5,
                color: "var(--muted)",
                fontWeight: 600,
                marginBottom: 8,
                textTransform: "capitalize",
              }}
            >
              {(project.sector ?? "construction")} · {project.client ?? "Owner"}
            </div>
            <h1
              className="pmx-h1"
              style={{
                fontFamily: "var(--font-d)",
                fontWeight: 700,
                fontSize: 40,
                lineHeight: 1.08,
                letterSpacing: "-0.02em",
                margin: "0 0 22px",
                maxWidth: 780,
              }}
            >
              {project.name}
            </h1>

            {/* stat row */}
            <div
              style={{ display: "flex", gap: 14, marginBottom: 30, flexWrap: "wrap" }}
              className="pmx-stats"
            >
              <Stat
                label="Contract value"
                value={usd(project.budget_total_cents)}
                sub={`${usd(project.budget_spent_cents)} spent`}
                color="var(--text)"
              />
              <Stat
                label="Schedule slip"
                value={slipWeeks != null ? `${slipWeeks} wks` : "—"}
                sub={slipWeeks != null && slipWeeks > 0 ? "behind plan" : "on track"}
                color={slipWeeks != null && slipWeeks > 0 ? "var(--r-critical)" : "var(--r-healthy)"}
              />
              <Stat
                label="Open risks"
                value={String(risks.filter((r) => r.status === "open").length || risks.length)}
                sub={`${risks.filter((r) => r.severity >= 5).length} critical`}
                color="var(--r-watch)"
              />
              <Stat
                label="Documents"
                value={String(documents.length)}
                sub="indexed & cited"
                color="var(--accent-2)"
              />
            </div>

            {/* 2-col: health + risks */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(0, .82fr) minmax(0, 1.18fr)",
                gap: 20,
                marginBottom: 20,
              }}
              className="pmx-2col"
            >
              {/* health gauge */}
              <div
                className="pmx-card"
                style={{
                  background: "var(--card)",
                  border: "1px solid var(--border)",
                  borderRadius: 18,
                  padding: 24,
                  boxShadow: "var(--shadow)",
                }}
              >
                <div
                  style={{
                    fontSize: 11.5,
                    color: "var(--text-3)",
                    fontWeight: 700,
                    letterSpacing: ".04em",
                    textTransform: "uppercase",
                    marginBottom: 4,
                  }}
                >
                  Project health
                </div>
                <div
                  style={{
                    fontFamily: "var(--font-d)",
                    fontWeight: 700,
                    fontSize: 17,
                    marginBottom: 16,
                  }}
                >
                  Overall score
                </div>
                <Gauge score={score} />
                <div style={{ marginTop: 22, display: "flex", flexDirection: "column", gap: 12 }}>
                  <div
                    style={{
                      fontSize: 12,
                      color: "var(--text-3)",
                      fontWeight: 700,
                      letterSpacing: ".03em",
                      textTransform: "uppercase",
                    }}
                  >
                    Contributing factors
                  </div>
                  {(health?.factors ?? []).length === 0 && (
                    <div style={{ color: "var(--text-3)", fontSize: 13 }}>
                      No factor breakdown available.
                    </div>
                  )}
                  {(health?.factors ?? []).map((f) => (
                    <FactorBar key={f.key} label={f.label} score={f.score} />
                  ))}
                </div>
              </div>

              {/* risks list */}
              <div
                className="pmx-card"
                style={{
                  background: "var(--card)",
                  border: "1px solid var(--border)",
                  borderRadius: 18,
                  padding: 24,
                  boxShadow: "var(--shadow)",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "baseline",
                    justifyContent: "space-between",
                    marginBottom: 16,
                  }}
                >
                  <div>
                    <div
                      style={{
                        fontSize: 11.5,
                        color: "var(--text-3)",
                        fontWeight: 700,
                        letterSpacing: ".04em",
                        textTransform: "uppercase",
                      }}
                    >
                      Ranked risks
                    </div>
                    <div style={{ fontFamily: "var(--font-d)", fontWeight: 700, fontSize: 17 }}>
                      {risks.length} flagged, worst first
                    </div>
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
                  {risks.map((r) => {
                    const s = sev(r.severity);
                    return (
                      <div
                        key={r.id}
                        style={{
                          borderRadius: 13,
                          border: "1px solid var(--border)",
                          background: "var(--surface-2)",
                          padding: "13px 15px",
                          borderLeft: `3px solid ${s.color}`,
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 9,
                            marginBottom: 5,
                          }}
                        >
                          <span
                            style={{
                              padding: "2px 9px",
                              borderRadius: 999,
                              background: `color-mix(in srgb, ${s.color} 16%, transparent)`,
                              color: s.color,
                              fontSize: 11,
                              fontWeight: 700,
                              fontFamily: "var(--font-d)",
                            }}
                          >
                            {s.label}
                          </span>
                          <span
                            style={{
                              fontSize: 11.5,
                              color: "var(--text-3)",
                              fontWeight: 600,
                              textTransform: "capitalize",
                            }}
                          >
                            {r.category}
                          </span>
                          {r.citations && r.citations.length > 0 && (
                            <span style={{ fontSize: 11, color: "var(--text-3)", marginLeft: "auto" }}>
                              {r.citations.length} source
                              {r.citations.length > 1 ? "s" : ""}
                            </span>
                          )}
                        </div>
                        <div
                          style={{
                            fontFamily: "var(--font-d)",
                            fontWeight: 600,
                            fontSize: 15,
                            marginBottom: 4,
                          }}
                        >
                          {r.title}
                        </div>
                        {r.business_impact && (
                          <div
                            style={{
                              fontSize: 13,
                              color: "var(--muted)",
                              lineHeight: 1.5,
                            }}
                          >
                            {r.business_impact}
                          </div>
                        )}
                        {r.recommended_action && (
                          <div
                            style={{
                              marginTop: 8,
                              fontSize: 12.5,
                              color: "var(--text)",
                              lineHeight: 1.5,
                            }}
                          >
                            <span style={{ color: "var(--teal)", fontWeight: 700 }}>
                              Recommended:{" "}
                            </span>
                            {r.recommended_action}
                          </div>
                        )}
                      </div>
                    );
                  })}
                  {risks.length === 0 && (
                    <div style={{ color: "var(--text-3)", fontSize: 13 }}>
                      No risks flagged for this project.
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* chat box */}
            <div
              style={{
                background: "linear-gradient(160deg, var(--card), var(--surface-2))",
                border: "1px solid var(--border)",
                borderRadius: 18,
                padding: 24,
                boxShadow: "var(--shadow)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 9,
                  marginBottom: 4,
                }}
              >
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: "var(--teal)",
                  }}
                />
                <div
                  style={{
                    fontSize: 11.5,
                    color: "var(--teal)",
                    fontWeight: 700,
                    letterSpacing: ".04em",
                    textTransform: "uppercase",
                  }}
                >
                  Ask the copilot
                </div>
              </div>
              <div
                style={{
                  fontFamily: "var(--font-d)",
                  fontWeight: 700,
                  fontSize: 19,
                  marginBottom: 16,
                }}
              >
                Every answer is grounded in the project documents, cited by page.
              </div>

              {/* transcript */}
              {turns.length > 0 && (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 12,
                    marginBottom: 16,
                    maxHeight: 420,
                    overflowY: "auto",
                    paddingRight: 4,
                  }}
                >
                  {turns.map((t, i) => (
                    <div
                      key={i}
                      style={{
                        alignSelf: t.role === "user" ? "flex-end" : "flex-start",
                        maxWidth: "88%",
                      }}
                    >
                      <div
                        style={{
                          padding: "11px 15px",
                          borderRadius: 14,
                          background:
                            t.role === "user" ? "var(--accent)" : "var(--surface-3)",
                          border:
                            t.role === "user"
                              ? "none"
                              : "1px solid var(--border)",
                          color: t.role === "user" ? "#fff" : "var(--text)",
                          fontSize: 14,
                          lineHeight: 1.6,
                          whiteSpace: "pre-wrap",
                        }}
                      >
                        {t.text}
                      </div>
                      {t.citations && t.citations.length > 0 && (
                        <div
                          style={{
                            display: "flex",
                            gap: 6,
                            flexWrap: "wrap",
                            marginTop: 7,
                          }}
                        >
                          {t.citations.map((c, ci) => (
                            <span
                              key={ci}
                              style={{
                                padding: "3px 10px",
                                borderRadius: 999,
                                background: "var(--accent-soft)",
                                border: "1px solid var(--accent-border)",
                                color: "var(--accent-2)",
                                fontSize: 11.5,
                                fontWeight: 600,
                              }}
                            >
                              p.{c.page ?? "?"}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                  {sending && (
                    <div
                      style={{
                        alignSelf: "flex-start",
                        color: "var(--text-3)",
                        fontSize: 13,
                        fontStyle: "italic",
                        animation: "pmxPulse 1.2s ease-in-out infinite",
                      }}
                    >
                      Reading the documents…
                    </div>
                  )}
                  <div ref={chatEndRef} />
                </div>
              )}

              {/* suggestions */}
              {turns.length === 0 && (
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
                  {[
                    "Why is this project behind schedule?",
                    "What's driving the budget overrun?",
                    "Which RFIs are overdue?",
                  ].map((q) => (
                    <button
                      key={q}
                      onClick={() => ask(q)}
                      className="pmx-btn"
                      style={{
                        padding: "8px 14px",
                        borderRadius: 999,
                        background: "var(--surface-3)",
                        border: "1px solid var(--border)",
                        color: "var(--muted)",
                        fontSize: 13,
                        fontWeight: 600,
                        cursor: "pointer",
                        fontFamily: "var(--font-b)",
                      }}
                    >
                      {q}
                    </button>
                  ))}
                </div>
              )}

              {/* input */}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  ask(input);
                }}
                style={{ display: "flex", gap: 10 }}
              >
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask about schedule, budget, RFIs, or risks…"
                  disabled={sending}
                  style={{
                    flex: 1,
                    padding: "13px 16px",
                    borderRadius: 12,
                    background: "var(--bg)",
                    border: "1px solid var(--border-strong)",
                    color: "var(--text)",
                    fontSize: 14.5,
                    fontFamily: "var(--font-b)",
                    outline: "none",
                  }}
                />
                <button
                  type="submit"
                  disabled={sending || !input.trim()}
                  className="pmx-btn"
                  style={{
                    padding: "13px 24px",
                    borderRadius: 12,
                    background: sending || !input.trim() ? "var(--surface-3)" : "var(--accent)",
                    color: "#fff",
                    fontWeight: 700,
                    fontSize: 14.5,
                    fontFamily: "var(--font-d)",
                    border: "none",
                    cursor: sending || !input.trim() ? "default" : "pointer",
                  }}
                >
                  {sending ? "…" : "Send"}
                </button>
              </form>
            </div>

            <div
              style={{
                marginTop: 26,
                color: "var(--text-3)",
                fontSize: 12.5,
                textAlign: "center",
              }}
            >
              Public demo · seeded data · brand styling inspired by Group PMX · not affiliated
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string;
  sub: string;
  color: string;
}) {
  return (
    <div
      style={{
        flex: "1 1 180px",
        background: "var(--card)",
        border: "1px solid var(--border)",
        borderRadius: 14,
        padding: "15px 18px",
      }}
    >
      <div style={{ fontSize: 12, color: "var(--text-3)", fontWeight: 600, marginBottom: 7 }}>
        {label}
      </div>
      <div
        style={{
          fontFamily: "var(--font-d)",
          fontWeight: 700,
          fontSize: 26,
          fontVariantNumeric: "tabular-nums",
          color,
        }}
      >
        {value}
      </div>
      <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 4 }}>{sub}</div>
    </div>
  );
}

function Gauge({ score }: { score: number }) {
  const size = 240;
  const stroke = 18;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, score)) / 100;
  const offset = circ * (1 - pct);
  const color =
    score >= 70
      ? "var(--r-healthy)"
      : score >= 50
        ? "var(--r-watch)"
        : score >= 35
          ? "var(--r-elevated)"
          : "var(--r-critical)";
  return (
    <div style={{ position: "relative", width: size, height: size, margin: "0 auto" }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--surface-3)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset .9s cubic-bezier(.4,0,.2,1)" }}
        />
      </svg>
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            fontFamily: "var(--font-d)",
            fontWeight: 700,
            fontSize: 66,
            lineHeight: 1,
            fontVariantNumeric: "tabular-nums",
            color: "var(--text)",
          }}
        >
          {score}
        </div>
        <div style={{ fontSize: 13, color: "var(--text-3)", fontWeight: 600, marginTop: 2 }}>
          / 100
        </div>
      </div>
    </div>
  );
}

function FactorBar({ label, score }: { label: string; score: number }) {
  const color =
    score >= 70
      ? "var(--r-healthy)"
      : score >= 50
        ? "var(--r-watch)"
        : score >= 35
          ? "var(--r-elevated)"
          : "var(--r-critical)";
  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: 5,
          fontSize: 13,
        }}
      >
        <span style={{ color: "var(--muted)", fontWeight: 600 }}>{label}</span>
        <span
          style={{
            fontFamily: "var(--font-d)",
            fontWeight: 700,
            color,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {score}
        </span>
      </div>
      <div
        style={{
          height: 7,
          borderRadius: 999,
          background: "var(--surface-3)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${Math.max(0, Math.min(100, score))}%`,
            height: "100%",
            borderRadius: 999,
            background: color,
            transition: "width .8s ease",
          }}
        />
      </div>
    </div>
  );
}

function Logo() {
  return (
    <div
      style={{
        width: 32,
        height: 32,
        borderRadius: 9,
        background: "linear-gradient(150deg,#1E7FE0,#0B4E9E)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none">
        <path
          d="m7 5 7 7-7 7"
          stroke="#2FE3C9"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="m13 5 4 4-1 3"
          stroke="#fff"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}
