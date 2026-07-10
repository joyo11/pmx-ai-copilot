"use client";

import Link from "next/link";
import {
  SignInButton,
  SignUpButton,
  SignedIn,
  SignedOut,
} from "@clerk/nextjs";

const NAVY = "#0D2A5C";
const MINT = "#5EE9C1";
const MINT_HOVER = "#7cf0d1";
const BLUE = "#2D7EFF";

export default function Home() {
  return (
    <>
      <style>{`
        .pmx-nav-link:hover { border-color: rgba(255,255,255,0.2) !important; color: #ffffff !important; }
        .pmx-pill-mint:hover { background: ${MINT_HOVER} !important; }
        .pmx-pill-ghost:hover { border-color: rgba(255,255,255,0.4) !important; background: rgba(255,255,255,0.05) !important; }
        .pmx-footer-link:hover { color: #ffffff !important; }
        button.pmx-nav-link, button.pmx-pill-mint, button.pmx-pill-ghost { font-family: inherit; cursor: pointer; }
      `}</style>

      <div
        style={{
          minHeight: "100vh",
          background: NAVY,
          color: "#ffffff",
          fontFamily: "'Geist', ui-sans-serif, system-ui, sans-serif",
          fontVariantNumeric: "tabular-nums",
          WebkitFontSmoothing: "antialiased",
          lineHeight: 1.5,
        }}
      >
        {/* Header */}
        <header
          style={{
            position: "sticky",
            top: 0,
            zIndex: 50,
            height: 64,
            background: NAVY,
            borderBottom: "1px solid rgba(255,255,255,0.12)",
          }}
        >
          <div
            style={{
              maxWidth: 1120,
              margin: "0 auto",
              height: 64,
              padding: "0 24px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <Link
              href="/"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                color: "#ffffff",
                textDecoration: "none",
              }}
            >
              <div
                style={{
                  position: "relative",
                  width: 28,
                  height: 28,
                  borderRadius: 7,
                  background: "rgba(255,255,255,0.08)",
                  border: "1px solid rgba(255,255,255,0.18)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <svg
                  width="15"
                  height="15"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="#ffffff"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
                </svg>
                <span
                  style={{
                    position: "absolute",
                    top: -3,
                    right: -3,
                    width: 9,
                    height: 9,
                    borderRadius: "50%",
                    background: MINT,
                    border: `2px solid ${NAVY}`,
                  }}
                />
              </div>
              <span
                style={{
                  fontSize: 15,
                  fontWeight: 600,
                  letterSpacing: "-0.01em",
                  color: "#ffffff",
                }}
              >
                PMX AI
              </span>
            </Link>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <SignedOut>
                <SignInButton mode="modal" forceRedirectUrl="/dashboard">
                  <button
                    type="button"
                    className="pmx-nav-link"
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      height: 36,
                      padding: "0 14px",
                      borderRadius: 8,
                      fontSize: 14,
                      fontWeight: 500,
                      color: "rgba(255,255,255,0.85)",
                      border: "1px solid transparent",
                      background: "transparent",
                      transition: "border-color .15s, color .15s",
                    }}
                  >
                    Sign in
                  </button>
                </SignInButton>
                <SignUpButton mode="modal" forceRedirectUrl="/dashboard">
                  <button
                    type="button"
                    className="pmx-pill-mint"
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 7,
                      height: 38,
                      padding: "0 18px",
                      borderRadius: 999,
                      fontSize: 14,
                      fontWeight: 600,
                      background: MINT,
                      color: NAVY,
                      border: "none",
                      transition: "background .15s",
                    }}
                  >
                    Get started
                    <ArrowSvg small />
                  </button>
                </SignUpButton>
              </SignedOut>
              <SignedIn>
                <Link
                  href="/dashboard"
                  className="pmx-pill-mint"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 7,
                    height: 38,
                    padding: "0 18px",
                    borderRadius: 999,
                    fontSize: 14,
                    fontWeight: 600,
                    background: MINT,
                    color: NAVY,
                    textDecoration: "none",
                    transition: "background .15s",
                  }}
                >
                  Open dashboard
                  <ArrowSvg small />
                </Link>
              </SignedIn>
            </div>
          </div>
        </header>

        {/* Hero */}
        <section
          style={{
            position: "relative",
            overflow: "hidden",
            background: NAVY,
          }}
        >
          <svg
            aria-hidden="true"
            width="640"
            height="760"
            viewBox="0 0 640 760"
            fill="none"
            style={{
              position: "absolute",
              top: "50%",
              left: -120,
              transform: "translateY(-50%) rotate(-8deg)",
              opacity: 0.4,
              pointerEvents: "none",
            }}
          >
            <polyline
              points="120,120 400,380 120,640"
              stroke={MINT}
              strokeWidth="1.5"
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <polyline
              points="300,120 580,380 300,640"
              stroke={MINT}
              strokeWidth="1.5"
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <div
            style={{
              position: "relative",
              zIndex: 1,
              maxWidth: 1120,
              margin: "0 auto",
              padding: "128px 24px 132px",
              textAlign: "center",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
            }}
          >
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                padding: "5px 12px 5px 10px",
                border: "1px solid rgba(255,255,255,0.2)",
                borderRadius: 999,
                background: "rgba(255,255,255,0.05)",
                fontSize: 12.5,
                color: "rgba(255,255,255,0.72)",
                fontWeight: 500,
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: MINT,
                }}
              />
              Built for construction project managers
            </div>
            <h1
              style={{
                margin: "28px 0 0",
                fontSize: "clamp(40px, 6.2vw, 68px)",
                lineHeight: 1.03,
                fontWeight: 600,
                letterSpacing: "-0.02em",
                textWrap: "balance",
                maxWidth: "15ch",
              }}
            >
              <span style={{ color: BLUE }}>Project Risk Copilot</span>
              <br />
              <span style={{ color: "#ffffff" }}>
                for the people who ship buildings.
              </span>
            </h1>
            <p
              style={{
                margin: "26px 0 0",
                maxWidth: 640,
                fontSize: 18,
                lineHeight: 1.6,
                color: "rgba(255,255,255,0.72)",
                textWrap: "pretty",
              }}
            >
              PMX AI reads your schedules, budgets, RFIs, and meeting notes,
              then tells you which projects are slipping, why, and what to do
              next. Grounded in your documents. Cited every time.
            </p>
            <div
              style={{
                marginTop: 34,
                display: "flex",
                flexWrap: "wrap",
                gap: 12,
                justifyContent: "center",
              }}
            >
              <SignedOut>
                <SignUpButton mode="modal" forceRedirectUrl="/dashboard">
                  <button
                    type="button"
                    className="pmx-pill-mint"
                    style={heroPillMint}
                  >
                    Open dashboard
                    <ArrowSvg />
                  </button>
                </SignUpButton>
                <SignInButton mode="modal" forceRedirectUrl="/projects">
                  <button
                    type="button"
                    className="pmx-pill-ghost"
                    style={heroPillGhost}
                  >
                    Ask a question
                  </button>
                </SignInButton>
              </SignedOut>
              <SignedIn>
                <Link
                  href="/dashboard"
                  className="pmx-pill-mint"
                  style={{ ...heroPillMint, textDecoration: "none" }}
                >
                  Open dashboard
                  <ArrowSvg />
                </Link>
                <Link
                  href="/projects"
                  className="pmx-pill-ghost"
                  style={{ ...heroPillGhost, textDecoration: "none" }}
                >
                  Ask a question
                </Link>
              </SignedIn>
            </div>
          </div>
        </section>

        {/* Feature cards */}
        <section style={{ background: NAVY, padding: "88px 24px 96px" }}>
          <div
            style={{
              maxWidth: 1120,
              margin: "0 auto",
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
              gap: 20,
            }}
          >
            <FeatureCard
              icon={
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
              }
              title="Health scores that explain themselves"
              body="Every project gets a 0-100 score with the factors, weights, and reasoning. No black box."
            />
            <FeatureCard
              icon={
                <>
                  <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
                  <path d="M12 8v4" />
                  <path d="M12 16h.01" />
                </>
              }
              title="Risk engine, not a keyword search"
              body="Schedule, budget, operational, communication, and compliance risks with severity, likelihood, and recommended action."
            />
            <FeatureCard
              icon={
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              }
              title="Chat with your project"
              body='Ask "what is delaying Bravo?" and get an answer with citations back to the specific PDF page.'
            />
          </div>
        </section>

        {/* How it works */}
        <section style={{ background: NAVY, padding: "8px 24px 88px" }}>
          <div style={{ maxWidth: 1120, margin: "0 auto" }}>
            <p
              style={{
                margin: "0 0 40px",
                textAlign: "center",
                fontFamily:
                  "'Geist Mono', ui-monospace, monospace",
                fontSize: 12,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                color: "rgba(255,255,255,0.5)",
              }}
            >
              How it works
            </p>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(3, 1fr)",
                gap: 0,
                alignItems: "start",
              }}
            >
              <Step n={1} text="Upload your documents." withConnector />
              <Step n={2} text="Watch risks surface." withConnector />
              <Step n={3} text="Ask questions with citations." />
            </div>
          </div>
        </section>

        {/* Proof strip */}
        <section
          style={{
            background: NAVY,
            padding: "40px 24px 88px",
            borderTop: "1px solid rgba(255,255,255,0.1)",
          }}
        >
          <div style={{ maxWidth: 1120, margin: "0 auto" }}>
            <p
              style={{
                margin: "0 0 22px",
                textAlign: "center",
                fontSize: 13,
                color: "rgba(255,255,255,0.5)",
              }}
            >
              Works with what you already use
            </p>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                justifyContent: "center",
                gap: "14px 28px",
                fontFamily: "'Geist Mono', ui-monospace, monospace",
                fontSize: 13,
                color: "rgba(255,255,255,0.55)",
                letterSpacing: "0.01em",
              }}
            >
              <span>Primavera P6</span>
              <Dot />
              <span>Microsoft Project</span>
              <Dot />
              <span>Excel</span>
              <Dot />
              <span>PDF</span>
              <Dot />
              <span>DOCX</span>
            </div>
          </div>
        </section>

        {/* Closing CTA */}
        <section style={{ background: NAVY, padding: "88px 24px" }}>
          <div
            style={{
              maxWidth: 1120,
              margin: "0 auto",
              textAlign: "center",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
            }}
          >
            <h2
              style={{
                margin: 0,
                fontSize: "clamp(26px, 3.4vw, 40px)",
                fontWeight: 600,
                letterSpacing: "-0.02em",
                textWrap: "balance",
                maxWidth: "20ch",
                color: "#ffffff",
              }}
            >
              Ready to see risk before it costs you
            </h2>
            <SignedOut>
              <SignUpButton mode="modal" forceRedirectUrl="/dashboard">
                <button
                  type="button"
                  className="pmx-pill-mint"
                  style={{ ...heroPillMint, marginTop: 30 }}
                >
                  Open dashboard
                  <ArrowSvg />
                </button>
              </SignUpButton>
            </SignedOut>
            <SignedIn>
              <Link
                href="/dashboard"
                className="pmx-pill-mint"
                style={{
                  ...heroPillMint,
                  marginTop: 30,
                  textDecoration: "none",
                }}
              >
                Open dashboard
                <ArrowSvg />
              </Link>
            </SignedIn>
          </div>
        </section>

        {/* Footer */}
        <footer
          style={{
            background: NAVY,
            borderTop: "1px solid rgba(255,255,255,0.12)",
            padding: "28px 24px",
          }}
        >
          <p
            style={{
              margin: 0,
              textAlign: "center",
              fontSize: 12,
              color: "rgba(255,255,255,0.5)",
            }}
          >
            Portfolio project built for firms like{" "}
            <a
              href="https://grouppmx.com"
              target="_blank"
              rel="noopener noreferrer"
              className="pmx-footer-link"
              style={{
                textDecoration: "underline",
                textUnderlineOffset: "2px",
                color: "rgba(255,255,255,0.72)",
              }}
            >
              Group PMX
            </a>
            . Not affiliated.
          </p>
        </footer>
      </div>
    </>
  );
}

function FeatureCard({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <div
      style={{
        border: "1px solid rgba(255,255,255,0.12)",
        borderRadius: 14,
        background: "rgba(255,255,255,0.04)",
        padding: "26px 24px 28px",
      }}
    >
      <svg
        width="22"
        height="22"
        viewBox="0 0 24 24"
        fill="none"
        stroke="rgba(255,255,255,0.6)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {icon}
      </svg>
      <h3
        style={{
          margin: "20px 0 8px",
          fontSize: 16.5,
          fontWeight: 600,
          letterSpacing: "-0.01em",
          color: "#ffffff",
        }}
      >
        {title}
      </h3>
      <p
        style={{
          margin: 0,
          fontSize: 14.5,
          lineHeight: 1.6,
          color: "rgba(255,255,255,0.72)",
        }}
      >
        {body}
      </p>
    </div>
  );
}

function Step({
  n,
  text,
  withConnector,
}: {
  n: number;
  text: string;
  withConnector?: boolean;
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        textAlign: "center",
        padding: "0 16px",
        position: "relative",
      }}
    >
      <div
        style={{
          width: 40,
          height: 40,
          borderRadius: 10,
          border: "1px solid rgba(255,255,255,0.12)",
          background: "rgba(255,255,255,0.04)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "'Geist Mono', monospace",
          fontSize: 15,
          color: "#ffffff",
        }}
      >
        {n}
      </div>
      <p
        style={{
          margin: "18px 0 0",
          fontSize: 15,
          fontWeight: 500,
          color: "#ffffff",
        }}
      >
        {text}
      </p>
      {withConnector ? (
        <span
          style={{
            position: "absolute",
            top: 20,
            left: "calc(50% + 32px)",
            right: -16,
            borderTop: "1px dashed rgba(255,255,255,0.25)",
          }}
        />
      ) : null}
    </div>
  );
}

function Dot() {
  return (
    <span
      style={{
        width: 3,
        height: 3,
        borderRadius: "50%",
        background: "rgba(255,255,255,0.25)",
      }}
    />
  );
}

const heroPillMint: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 8,
  height: 46,
  padding: "0 24px",
  borderRadius: 999,
  fontSize: 15,
  fontWeight: 600,
  background: MINT,
  color: NAVY,
  border: "none",
  transition: "background .15s",
};

const heroPillGhost: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  height: 46,
  padding: "0 22px",
  border: "1px solid rgba(255,255,255,0.18)",
  borderRadius: 999,
  fontSize: 15,
  fontWeight: 500,
  color: "#ffffff",
  background: "transparent",
  transition: "border-color .15s, background .15s",
};

function ArrowSvg({ small }: { small?: boolean }) {
  const size = small ? 15 : 16;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </svg>
  );
}
