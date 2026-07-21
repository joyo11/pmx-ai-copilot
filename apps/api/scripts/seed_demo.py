"""Seed a realistic hospital-expansion demo project into the owner's org.

Runs the REAL pipeline (extract -> embed -> risk scan -> health snapshot) so the
demo data is genuine app output: cited chat resolves to real pages, and risks are
produced by the actual rules + LLM engine, not hand-faked rows.

Idempotent: deletes any prior project with the same name (cascade) first.

Run:  uv run python scripts/seed_demo.py
Needs: DATABASE_URL, OPENAI_API_KEY, ANTHROPIC_API_KEY in .env (all present).
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import fitz  # PyMuPDF
from sqlalchemy import select

from pmx_api.config import get_settings
from pmx_api.db.models import (
    BudgetLine,
    ChangeOrder,
    Document,
    DocumentChunk,
    Meeting,
    Organization,
    Project,
    Rfi,
    Risk,
    ScheduleTask,
    User,
)
from pmx_api.db.session import get_async_sessionmaker
from pmx_api.pipeline.extract import extract_and_embed_document
from pmx_api.services import health as health_service
from pmx_api.services import risks as risks_service

PROJECT_NAME = "Northshore Medical Center - Bed Tower Expansion"
TODAY = datetime.now(UTC).date()


def d(days_ago: int) -> date:
    return TODAY - timedelta(days=days_ago)


# --------------------------------------------------------------------------- #
# Demo document content (dense, credible construction narrative)              #
# --------------------------------------------------------------------------- #

OAC_MINUTES = [
    # page 1
    """NORTHSHORE MEDICAL CENTER - BED TOWER EXPANSION
Owner-Architect-Contractor (OAC) Progress Meeting Minutes
Meeting No. 17 | Project No. NMC-2025-04 | Rockville, Maryland

Owner: Northshore Health System   Program Manager: Group PMX
Contract: GMP, $48.0M   Original Substantial Completion: 30-Jun-2027

ATTENDEES: Owner rep (Facilities Director), Group PMX PM and scheduler,
GC project executive and superintendent, MEP coordinator, architect of record,
structural EOR (by phone).

1. OVERALL STATUS
Project is 65% complete by cost, 61% complete by schedule. Overall health has
declined this period, driven primarily by structural steel delivery delays and
newly discovered subsurface rock in the north foundation zone. The GC has issued
a revised forecast substantial completion of 15-Sep-2027, a slip of roughly 11
weeks against the contract date. Group PMX has requested a formal Time Impact
Analysis (TIA) and a recovery plan by the next meeting.

2. SAFETY
Zero lost-time incidents this period. Total recordable incident rate remains
below 1.5. One near-miss reported during steel erection (unsecured load); the GC
re-briefed the crew and revised the lift plan. OSHA-required fall protection
audits are current.

3. SCHEDULE - CRITICAL PATH
The critical path now runs through structural steel erection (Levels 3-6),
Level 4 MEP rough-in, and permanent power energization. Steel erection is 21
calendar days behind due to a fabricator delivery shortfall on the Level 3-6
sequences. Level 4 MEP rough-in cannot start in full until the steel deck above
is complete, so the steel slip is cascading. Permanent power / switchgear
energization is tracking 18 days late pending utility coordination and RFI-051.
Curtain wall (east elevation) is 9 days behind but has float and is not yet on
the critical path.""",
    # page 2
    """4. STRUCTURAL / FOUNDATIONS
During mass excavation of the north foundation zone the GC encountered
competent rock roughly 4-6 feet above the anticipated elevation shown in the
geotechnical baseline. Additional drilling, hoe-ramming, and export were
required. This is the basis of Change Order CO-07 (unforeseen rock excavation).
The EOR confirmed footing designs are unaffected, but the added earthwork has
both cost and schedule impact and contributed to the north-zone slip.

5. MEP COORDINATION
The MEP coordinator reported unresolved clashes between the Level 4 overhead
medical gas mains and the structural steel beam pockets at grid lines C and D.
This is the subject of RFI-058. Until routing is confirmed, the GC is holding
medical gas rough-in on Level 4, which is a near-critical predecessor to
interior wall close-in. Air handling unit (AHU-3) delivery is confirmed for next
month; no issue.

6. CHANGE ORDERS
Five change orders are pending owner execution totaling approximately $2.46M:
CO-07 unforeseen rock excavation ($840k), CO-09 owner-requested imaging suite
upgrade ($610k), CO-11 structural steel escalation ($520k), CO-12 added
emergency generator capacity ($305k), and CO-13 revised nurse-call system
($180k). Group PMX flagged that the volume of pending change orders is eroding
contingency and asked the Owner to expedite decisions to avoid further delay.

7. OPEN RFIs OF CONCERN
RFI-042 (embed plate conflict at grid C-4), RFI-051 (panel schedule LP-4
discrepancy), and RFI-058 (medical gas routing) are all open past their required
response dates and are impacting field work. See the RFI Log narrative.

8. ACTION ITEMS
(a) GC to submit TIA and recovery plan for the 11-week slip - due next meeting.
(b) Owner to execute or reject CO-07, CO-09, CO-11 within 10 days.
(c) EOR to respond to RFI-042 embed plate conflict this week.
(d) MEP coordinator to publish resolved Level 4 medical gas routing.
""",
]

COST_SCHEDULE_REPORT = [
    # page 1
    """NORTHSHORE MEDICAL CENTER - BED TOWER EXPANSION
Monthly Cost & Schedule Report | Period ending this month | Prepared by Group PMX

1. EARNED VALUE SUMMARY
Budget at Completion (BAC): $48.0M. Actual Cost of Work Performed (ACWP) to date
is tracking above the Budgeted Cost of Work Performed (BCWP). Cost Performance
Index (CPI) is approximately 0.90 and Schedule Performance Index (SPI) is
approximately 0.93 - both below 1.0, indicating the project is over budget and
behind schedule this period. The current Estimate at Completion (EAC) forecasts
a total near $50.8M against the $46.0M forecast baseline for these divisions,
about 10.4% over forecast, before pending change orders are executed.

2. BUDGET VARIANCE BY DIVISION (forecast vs. actual)
- Sitework / Earthwork: forecast $4.0M, actual $6.4M. Major overrun driven by
  unforeseen rock excavation in the north foundation zone (see CO-07). This is
  the single largest contributor to the cost variance.
- Structural Steel: forecast $6.4M, actual $7.6M. Mill price escalation plus
  expedited freight on the Level 3-6 sequences (see CO-11).
- Concrete: forecast $5.0M, actual $5.1M. On plan.
- Mechanical/Electrical/Plumbing: forecast $12.5M, actual $13.4M. Trending over
  on added generator capacity (CO-12) and medical gas rework exposure.
- Exterior Envelope / Curtain Wall: forecast $4.6M, actual $4.7M. On plan.
- Interiors / Finishes: forecast $8.0M, actual $8.2M. Slightly over.
- Medical Equipment: forecast $5.5M, actual $5.4M. On plan.
Aggregate: forecast $46.0M, actual $50.8M, an overrun of about 10.4%.""",
    # page 2
    """3. SCHEDULE / CRITICAL PATH ANALYSIS
The critical path runs: structural steel erection (Levels 3-6) -> Level 4 MEP
rough-in -> interior close-in -> permanent power energization -> commissioning.
Steel erection is 21 days behind plan; Level 4 MEP rough-in 14 days behind;
permanent power energization 18 days behind. Total forecast slip to substantial
completion is approximately 11 weeks (contract 30-Jun-2027, forecast
15-Sep-2027). Liquidated damages under the contract are $12,000 per calendar day
beyond substantial completion, so an 11-week slip represents roughly $924,000 of
exposure if not recovered.

4. RECOVERY OPTIONS
Group PMX and the GC are evaluating: (a) adding a second steel erection crew and
a Saturday shift to claw back 2-3 weeks; (b) re-sequencing Level 4 MEP to start
in the completed south bays while the north steel finishes; (c) expediting the
RFI-051 utility coordination to protect the energization date. Option (b) has no
added cost and is recommended for immediate implementation.

5. CASH FLOW & CONTINGENCY
Remaining GMP contingency is $1.1M. The five pending change orders total $2.46M,
which exceeds remaining contingency by $1.36M. Group PMX recommends the Owner
prioritize CO-07 and CO-11 (schedule-linked) and defer CO-09 imaging upgrade to
a separate funding source to preserve contingency for construction risk.

6. RISK OUTLOOK
Top risks this period: (1) cost overrun driven by sitework and steel; (2) the
11-week schedule slip and associated LD exposure; (3) overdue RFIs blocking field
work; (4) pending change-order volume exceeding contingency.""",
]

RFI_LOG = [
    # page 1
    """NORTHSHORE MEDICAL CENTER - BED TOWER EXPANSION
RFI Log Narrative | Prepared by Group PMX

The following Requests for Information are open past their contractual response
period (10 business days) and are actively impacting field work.

RFI-042 - Embed Plate Conflict at Grid C-4 (Structural)
Submitted 45 days ago; response was due 28 days ago; still OPEN.
The GC identified a conflict between the structural embed plate detail and the
poured-in-place shear wall reinforcement at grid C-4. Field cannot set the
Level 3 beam connection until the EOR confirms a revised embed. Every week this
stays open pushes the Level 3-6 steel sequence, which is on the critical path.
AI delay risk: HIGH.

RFI-051 - Panel Schedule LP-4 Discrepancy (Electrical)
Submitted 38 days ago; response was due 21 days ago; still OPEN.
The electrical panel schedule for LP-4 does not match the single-line diagram
for the permanent power feeders. The utility will not schedule energization
until the discrepancy is resolved. This directly threatens the permanent power
energization milestone, currently 18 days late. AI delay risk: HIGH.

RFI-058 - Medical Gas Rough-in Routing, Level 4 (Mechanical/Plumbing)
Submitted 30 days ago; response was due 16 days ago; still OPEN.
Overhead medical gas mains clash with structural steel beam pockets at grid
lines C and D on Level 4. Medical gas rough-in is on hold pending resolved
routing. This is a near-critical predecessor to interior close-in.
AI delay risk: MEDIUM-HIGH.""",
    # page 2
    """CLOSED / ANSWERED RFIs (for reference)
RFI-039 - Door hardware group at ICU suite (Architectural): ANSWERED on time.
RFI-047 - Roof drain overflow sizing (Plumbing): ANSWERED, no schedule impact.

IMPACT ANALYSIS
The three open RFIs above share a common theme: each blocks a critical or
near-critical path activity, and each has aged well past the 10-day contractual
response window. RFI-042 and RFI-051 are the most urgent because they sit
directly on the steel-erection and permanent-power critical paths. The aggregate
effect of these overdue RFIs is an estimated 2-3 weeks of avoidable schedule
erosion if they are not closed within the week.

RECOMMENDATIONS
1. Escalate RFI-042 to the EOR for a same-week response; the embed plate
   conflict is the single highest-leverage open item.
2. Convene a short utility-coordination call to resolve RFI-051 and protect the
   energization date.
3. Hold a focused MEP coordination session to finalize Level 4 medical gas
   routing (RFI-058) so rough-in can resume.
4. Institute a weekly RFI aging review; no RFI on the critical path should be
   allowed to exceed the 10-day response window without escalation.
""",
]

DOCS = [
    {"kind": "meeting_notes", "filename": "OAC_Meeting_Minutes_No17.pdf", "pages": OAC_MINUTES},
    {"kind": "pdf_generic", "filename": "Monthly_Cost_and_Schedule_Report.pdf", "pages": COST_SCHEDULE_REPORT},
    {"kind": "rfi_log", "filename": "RFI_Log_Narrative.pdf", "pages": RFI_LOG},
]


def make_pdf(pages: list[str], path: Path) -> None:
    doc = fitz.open()
    for page_text in pages:
        page = doc.new_page(width=612, height=792)  # US Letter
        rect = fitz.Rect(54, 54, 558, 738)
        page.insert_textbox(rect, page_text, fontsize=9, fontname="helv", align=0)
    doc.save(str(path))
    doc.close()


async def main() -> None:
    settings = get_settings()
    Session = get_async_sessionmaker()

    async with Session() as db:
        org = (await db.execute(select(Organization))).scalars().first()
        if org is None:
            print("No organization found - sign in to the app once first.", file=sys.stderr)
            return
        user = (await db.execute(select(User).where(User.org_id == org.id))).scalars().first()
        print(f"Seeding into org={org.name} ({org.id}) as user={user.email}")

        # Idempotent: drop any prior copy of this demo project, and remove the
        # empty "Assignment" test stub so the dashboard lands cleanly on the
        # hospital project (it holds no documents/risks — pure scaffolding).
        prior = (
            await db.execute(
                select(Project).where(
                    Project.org_id == org.id,
                    Project.name.in_([PROJECT_NAME, "Assignment"]),
                )
            )
        ).scalars().all()
        for p in prior:
            await db.delete(p)
        await db.commit()

        # Project.
        proj = Project(
            org_id=org.id,
            name=PROJECT_NAME,
            client="Northshore Health System",
            sector="Healthcare",
            location="Rockville, Maryland",
            start_date=date(2025, 3, 3),
            planned_end_date=date(2027, 6, 30),
            forecast_end_date=date(2027, 9, 15),
            budget_total_cents=4_800_000_000,
            budget_spent_cents=3_120_000_000,
            status="active",
            metadata_={"demo": True},
        )
        db.add(proj)
        await db.commit()
        await db.refresh(proj)
        print(f"Created project {proj.id}")

        # Documents -> real ingest (chunk + embed).
        doc_ids: dict[str, object] = {}
        storage = Path(settings.storage_dir)
        storage.mkdir(parents=True, exist_ok=True)
        for spec in DOCS:
            doc = Document(
                project_id=proj.id,
                uploaded_by=user.id,
                kind=spec["kind"],
                filename=spec["filename"],
                storage_uri="pending",
                status="uploaded",
                metadata_={"demo": True},
            )
            db.add(doc)
            await db.commit()
            await db.refresh(doc)
            pdf_path = storage / f"{doc.id}.pdf"
            make_pdf(spec["pages"], pdf_path)
            doc.storage_uri = f"file://{pdf_path.resolve()}"
            await db.commit()
            n = await extract_and_embed_document(
                db=db,
                document_id=doc.id,
                project_id=proj.id,
                pdf_path=pdf_path,
                settings=settings,
            )
            doc_ids[spec["kind"]] = doc.id
            print(f"  ingested {spec['filename']}: {n} chunks embedded")

        rfi_doc = doc_ids.get("rfi_log")
        cost_doc = doc_ids.get("pdf_generic")

        # Structured data - tuned to trigger the rules engine.
        # Budget: aggregate actual ($50.8M) / forecast ($46.0M) = 1.104 -> severity 3.
        budget = [
            ("Sitework / Earthwork", 380, 400, 640),
            ("Structural Steel", 620, 640, 760),
            ("Concrete", 500, 500, 510),
            ("Mechanical/Electrical/Plumbing", 1200, 1250, 1340),
            ("Exterior Envelope / Curtain Wall", 450, 460, 470),
            ("Interiors / Finishes", 800, 800, 820),
            ("Medical Equipment", 550, 550, 540),
        ]
        for cat, bud, fc, act in budget:
            db.add(
                BudgetLine(
                    project_id=proj.id,
                    source_doc_id=cost_doc,
                    category=cat,
                    budgeted_cents=bud * 10_000_00,
                    forecast_cents=fc * 10_000_00,
                    actual_cents=act * 10_000_00,
                    period=d(15),
                )
            )

        # Schedule: several tasks slipping > 7 days, some on the critical path.
        tasks = [
            ("Structural steel erection - Levels 3-6", 21, True, 55),
            ("Level 4 MEP rough-in", 14, True, 20),
            ("Permanent power / switchgear energization", 18, True, 0),
            ("Curtain wall installation - East elevation", 9, False, 40),
            ("Foundations - North zone (rock)", 12, False, 95),
            ("Elevator installation", 3, False, 30),
            ("Level 2 interior framing", 0, False, 70),
        ]
        for name, slip, crit, pct in tasks:
            db.add(
                ScheduleTask(
                    project_id=proj.id,
                    source_doc_id=cost_doc,
                    name=name,
                    planned_start=d(120),
                    planned_finish=d(-40),
                    percent_done=pct,
                    is_critical=crit,
                    slip_days=slip,
                )
            )

        # RFIs: three open well past the 14-day window (+ two answered).
        rfis = [
            ("RFI-042", "Embed plate conflict at grid C-4", "structural", 45, 28, None, "open", 0.85),
            ("RFI-051", "Panel schedule LP-4 discrepancy", "electrical", 38, 21, None, "open", 0.80),
            ("RFI-058", "Medical gas rough-in routing, Level 4", "mechanical", 30, 16, None, "open", 0.70),
            ("RFI-039", "Door hardware group at ICU suite", "architectural", 60, 50, 48, "answered", 0.10),
            ("RFI-047", "Roof drain overflow sizing", "plumbing", 55, 45, 44, "answered", 0.05),
        ]
        for num, subj, disc, sub_ago, due_ago, ans_ago, status, risk in rfis:
            db.add(
                Rfi(
                    project_id=proj.id,
                    source_doc_id=rfi_doc,
                    number=num,
                    subject=subj,
                    discipline=disc,
                    submitted_date=d(sub_ago),
                    due_date=d(due_ago),
                    answered_date=d(ans_ago) if ans_ago else None,
                    status=status,
                    ai_delay_risk=risk,
                )
            )

        # Change orders: five pending (> limit of 3) + two approved.
        cos = [
            ("CO-07", "Unforeseen rock excavation - north foundation zone", 840, "pending"),
            ("CO-09", "Owner-requested imaging suite upgrade", 610, "pending"),
            ("CO-11", "Structural steel price escalation", 520, "pending"),
            ("CO-12", "Added emergency generator capacity", 305, "pending"),
            ("CO-13", "Revised nurse-call system", 180, "pending"),
            ("CO-05", "ICU headwall revision", 95, "approved"),
            ("CO-06", "Added roof screen wall", 60, "approved"),
        ]
        for num, desc, amt_k, status in cos:
            db.add(
                ChangeOrder(
                    project_id=proj.id,
                    source_doc_id=cost_doc,
                    number=num,
                    description=desc,
                    amount_cents=amt_k * 1_000_00,
                    submitted_date=d(20),
                    status=status,
                )
            )

        # A meeting record (populates the Meetings tab).
        db.add(
            Meeting(
                project_id=proj.id,
                source_doc_id=doc_ids.get("meeting_notes"),
                meeting_date=d(3),
                summary=(
                    "OAC Meeting No. 17: project 65% complete by cost. Structural steel "
                    "delivery delay and unforeseen north-zone rock have pushed forecast "
                    "substantial completion to 15-Sep-2027 (~11-week slip). Five change "
                    "orders pending; three critical RFIs overdue."
                ),
                decisions=[
                    {"text": "Implement Level 4 MEP south-bay re-sequence (no added cost)."},
                    {"text": "Prioritize CO-07 and CO-11 for owner execution."},
                ],
                action_items=[
                    {"owner": "GC", "text": "Submit Time Impact Analysis + recovery plan", "due": str(d(-7))},
                    {"owner": "EOR", "text": "Respond to RFI-042 embed plate conflict", "due": str(d(-3))},
                    {"owner": "Owner", "text": "Execute CO-07, CO-09, CO-11 within 10 days", "due": str(d(-10))},
                ],
            )
        )
        await db.commit()
        print("Inserted structured data (budget, schedule, RFIs, change orders, meeting)")

        # Run the REAL risk engine (rules + LLM w/ citations).
        written = await risks_service.scan_project(db, proj.id, settings)
        print(f"Risk scan wrote/updated {len(written)} risks")

        # Two analyst-level risks the rules engine can't compute, each grounded
        # in a real chunk so the Risks tab visibly shows citations too. We cite
        # the cost-report page-2 chunk (liquidated damages + contingency text).
        cost_doc_id = doc_ids.get("pdf_generic")
        cost_p2 = (
            await db.execute(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == cost_doc_id, DocumentChunk.page == 2)
                .limit(1)
            )
        ).scalars().first()
        if cost_p2 is not None:
            cite = [{"document_id": str(cost_doc_id), "chunk_id": str(cost_p2.id), "page": 2}]
            db.add(
                Risk(
                    project_id=proj.id,
                    category="schedule",
                    title="Liquidated damages exposure ~$924K from forecast 11-week slip",
                    description=(
                        "At $12,000/day of liquidated damages, the forecast 11-week slip to "
                        "substantial completion (30-Jun-2027 -> 15-Sep-2027) represents roughly "
                        "$924,000 of LD exposure if the schedule is not recovered."
                    ),
                    severity=4,
                    likelihood=0.7,
                    business_impact="Direct contractual penalty against margin; owner-relationship risk.",
                    recommended_action=(
                        "Adopt the no-cost Level 4 MEP south-bay re-sequence now and pursue the "
                        "second steel crew; require a Time Impact Analysis before next owner meeting."
                    ),
                    confidence=0.82,
                    status="open",
                    detected_at=datetime.now(UTC),
                    citations=cite,
                    metadata_={"source": "llm", "rule_key": "seed_ld_exposure"},
                )
            )
            db.add(
                Risk(
                    project_id=proj.id,
                    category="budget",
                    title="Pending change orders exceed remaining contingency by ~$1.36M",
                    description=(
                        "Five pending change orders total ~$2.46M against ~$1.1M of remaining GMP "
                        "contingency, a ~$1.36M shortfall. Executing all pending COs without added "
                        "funding would exhaust contingency with ~35% of work remaining."
                    ),
                    severity=3,
                    likelihood=0.8,
                    business_impact="Contingency exhaustion leaves no buffer for remaining construction risk.",
                    recommended_action=(
                        "Prioritize schedule-linked CO-07 and CO-11; move the CO-09 imaging upgrade "
                        "to a separate owner funding source to preserve contingency."
                    ),
                    confidence=0.8,
                    status="open",
                    detected_at=datetime.now(UTC),
                    citations=cite,
                    metadata_={"source": "llm", "rule_key": "seed_contingency_shortfall"},
                )
            )
            await db.commit()
            print("Added 2 cited analyst risks (LD exposure, contingency shortfall)")

        # Health snapshot + set the project card score.
        snap = await health_service.snapshot_project_health(db, proj.id)
        proj.health_score = snap.score
        proj.health_computed_at = snap.computed_at
        await db.commit()
        print(f"Health score: {snap.score}")
        print(f"\nDONE. Project {proj.id} seeded and ready.")


if __name__ == "__main__":
    asyncio.run(main())
