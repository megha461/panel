"""Generate the Panel documentation PDF.

Carries the app's own design language into print: ink cover, paper body, one
amber accent used only where evidence or emphasis is being marked, and the same
three type roles — serif for statements, sans for prose, mono for the record.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

OUT = Path("/Users/megha/panel-documentation.pdf")
FONTS = Path("/System/Library/Fonts/Supplemental")

# ---------------------------------------------------------------- design tokens

INK = colors.HexColor("#11151C")
SLATE = colors.HexColor("#1A202A")
PAPER = colors.HexColor("#FFFFFF")
PANEL = colors.HexColor("#F2F3F5")
GRAPHITE = colors.HexColor("#2A313D")
BODY = colors.HexColor("#3A424F")
AMBER = colors.HexColor("#C98A2B")
MUTE = colors.HexColor("#7A8494")
RULE = colors.HexColor("#D8DBE0")

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm


def register_fonts() -> None:
    faces = {
        "Doc-Serif": "Georgia.ttf",
        "Doc-Serif-Bold": "Georgia Bold.ttf",
        "Doc-Serif-Italic": "Georgia Italic.ttf",
        "Doc-Sans": "Arial.ttf",
        "Doc-Sans-Bold": "Arial Bold.ttf",
        "Doc-Sans-Italic": "Arial Italic.ttf",
        "Doc-Mono": "Andale Mono.ttf",
    }
    for name, filename in faces.items():
        pdfmetrics.registerFont(TTFont(name, str(FONTS / filename)))
    pdfmetrics.registerFontFamily(
        "Doc-Sans", normal="Doc-Sans", bold="Doc-Sans-Bold", italic="Doc-Sans-Italic"
    )
    pdfmetrics.registerFontFamily(
        "Doc-Serif", normal="Doc-Serif", bold="Doc-Serif-Bold", italic="Doc-Serif-Italic"
    )


# --------------------------------------------------------------------- styles


def build_styles() -> dict[str, ParagraphStyle]:
    s: dict[str, ParagraphStyle] = {}

    s["cover_title"] = ParagraphStyle(
        "cover_title", fontName="Doc-Serif", fontSize=54, leading=58,
        textColor=colors.HexColor("#F2F3F5"), alignment=TA_LEFT,
    )
    s["cover_sub"] = ParagraphStyle(
        "cover_sub", fontName="Doc-Serif-Italic", fontSize=17, leading=25,
        textColor=colors.HexColor("#B9C1CD"),
    )
    s["cover_meta"] = ParagraphStyle(
        "cover_meta", fontName="Doc-Mono", fontSize=8.5, leading=15,
        textColor=MUTE,
    )
    s["part"] = ParagraphStyle(
        "part", fontName="Doc-Mono", fontSize=8.5, leading=12, textColor=AMBER,
        spaceAfter=5,
    )
    s["h1"] = ParagraphStyle(
        "h1", fontName="Doc-Serif", fontSize=27, leading=32, textColor=GRAPHITE,
        spaceAfter=11,
    )
    s["h2"] = ParagraphStyle(
        "h2", fontName="Doc-Sans-Bold", fontSize=12.5, leading=17, textColor=GRAPHITE,
        spaceBefore=15, spaceAfter=6,
    )
    s["h3"] = ParagraphStyle(
        "h3", fontName="Doc-Mono", fontSize=8, leading=12, textColor=MUTE,
        spaceBefore=13, spaceAfter=5,
    )
    s["body"] = ParagraphStyle(
        "body", fontName="Doc-Sans", fontSize=9.7, leading=15.2, textColor=BODY,
        spaceAfter=8,
    )
    s["lede"] = ParagraphStyle(
        "lede", fontName="Doc-Serif", fontSize=12.5, leading=19, textColor=GRAPHITE,
        spaceAfter=11,
    )
    s["bullet"] = ParagraphStyle(
        "bullet", parent=s["body"], leftIndent=13, bulletIndent=3, spaceAfter=5,
    )
    s["mono"] = ParagraphStyle(
        "mono", fontName="Doc-Mono", fontSize=8.2, leading=12.4,
        textColor=GRAPHITE, spaceAfter=7,
    )
    s["caption"] = ParagraphStyle(
        "caption", fontName="Doc-Sans", fontSize=8.2, leading=12.4, textColor=MUTE,
        spaceAfter=9,
    )
    s["pull"] = ParagraphStyle(
        "pull", fontName="Doc-Serif-Italic", fontSize=12.5, leading=19,
        textColor=GRAPHITE, leftIndent=11, spaceBefore=5, spaceAfter=5,
    )
    s["cell"] = ParagraphStyle(
        "cell", fontName="Doc-Sans", fontSize=8.4, leading=12, textColor=BODY,
    )
    s["cell_mono"] = ParagraphStyle(
        "cell_mono", fontName="Doc-Mono", fontSize=7.6, leading=11.6, textColor=GRAPHITE,
    )
    s["cell_head"] = ParagraphStyle(
        "cell_head", fontName="Doc-Mono", fontSize=7.2, leading=10.5, textColor=MUTE,
    )
    s["toc"] = ParagraphStyle(
        "toc", fontName="Doc-Sans", fontSize=10, leading=20, textColor=BODY,
    )
    s["stat_num"] = ParagraphStyle(
        "stat_num", fontName="Doc-Serif", fontSize=25, leading=28, textColor=GRAPHITE,
    )
    s["stat_key"] = ParagraphStyle(
        "stat_key", fontName="Doc-Mono", fontSize=7, leading=11, textColor=MUTE,
    )
    return s


S = None  # populated in main()


# ------------------------------------------------------------------ helpers


def para(text, style="body"):
    return Paragraph(text, S[style])


def bullets(items, style="bullet"):
    return [Paragraph(t, S[style], bulletText="—") for t in items]


def rule(space_before=5, space_after=9, colour=RULE, width=0.6):
    t = Table([[""]], colWidths=[PAGE_W - 2 * MARGIN], rowHeights=[0.1])
    t.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), width, colour),
        ("TOPPADDING", (0, 0), (-1, -1), space_before),
        ("BOTTOMPADDING", (0, 0), (-1, -1), space_after),
    ]))
    return t


def data_table(rows, widths, header=True, mono_cols=(), align_right=()):
    body_rows = []
    for r_i, row in enumerate(rows):
        out = []
        for c_i, cell in enumerate(row):
            if r_i == 0 and header:
                out.append(Paragraph(str(cell), S["cell_head"]))
            else:
                style = "cell_mono" if c_i in mono_cols else "cell"
                out.append(Paragraph(str(cell), S[style]))
        body_rows.append(out)

    t = Table(body_rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
    ]
    if header:
        style += [
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, GRAPHITE),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ]
    for c in align_right:
        style.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    return t


def callout(title, text, colour=AMBER):
    inner = [
        [Paragraph(title, ParagraphStyle("ct", fontName="Doc-Mono", fontSize=7.4,
                                          leading=11, textColor=colour))],
        [Paragraph(text, ParagraphStyle("cb", fontName="Doc-Sans", fontSize=9.2,
                                         leading=14.5, textColor=GRAPHITE))],
    ]
    t = Table(inner, colWidths=[PAGE_W - 2 * MARGIN - 14])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("LINEBEFORE", (0, 0), (0, -1), 2.2, colour),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 11),
        ("TOPPADDING", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 10),
    ]))
    return t


def code_block(lines):
    text = "<br/>".join(
        line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace(" ", "&nbsp;")
        for line in lines
    )
    p = Paragraph(text, ParagraphStyle("code", fontName="Doc-Mono", fontSize=7.6,
                                        leading=11.6, textColor=GRAPHITE))
    t = Table([[p]], colWidths=[PAGE_W - 2 * MARGIN])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return t


def stat_strip(pairs):
    """A row of big numbers with mono labels."""
    cells = []
    for value, key in pairs:
        cells.append([Paragraph(value, S["stat_num"]), Paragraph(key, S["stat_key"])])
    table_rows = [[c[0] for c in cells], [c[1] for c in cells]]
    width = (PAGE_W - 2 * MARGIN) / len(pairs)
    t = Table(table_rows, colWidths=[width] * len(pairs))
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, 0), 4),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, GRAPHITE),
        ("LINEBELOW", (0, 1), (-1, 1), 0.6, RULE),
    ]))
    return t


def section(number, title, lede=None):
    out = [para(number, "part"), Paragraph(title, S["h1"])]
    if lede:
        out.append(Paragraph(lede, S["lede"]))
    out.append(rule(space_before=2, space_after=12))
    return out


# ------------------------------------------------------------- page painting


def paint_cover(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(INK)
    canvas.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
    # A single amber rule: the one accent, spent once.
    canvas.setStrokeColor(AMBER)
    canvas.setLineWidth(2.4)
    canvas.line(MARGIN, PAGE_H - 62 * mm, MARGIN + 46 * mm, PAGE_H - 62 * mm)
    canvas.restoreState()


def paint_body(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)

    canvas.setFont("Doc-Mono", 7)
    canvas.setFillColor(MUTE)
    canvas.drawString(MARGIN, PAGE_H - 13 * mm, "PANEL — TECHNICAL DOCUMENTATION")
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - 13 * mm, "RUBRIC-GROUNDED INTERVIEW ENGINE")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, PAGE_H - 15.5 * mm, PAGE_W - MARGIN, PAGE_H - 15.5 * mm)

    canvas.line(MARGIN, 15 * mm, PAGE_W - MARGIN, 15 * mm)
    canvas.setFont("Doc-Mono", 7)
    canvas.drawString(MARGIN, 10.5 * mm, "PANEL v0.1.0")
    canvas.drawRightString(PAGE_W - MARGIN, 10.5 * mm, f"{doc.page}")
    canvas.restoreState()


def build_doc():
    doc = BaseDocTemplate(
        str(OUT), pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title="Panel — Technical Documentation",
        author="Panel",
        subject="AI interview engine: architecture, files, statistics and status",
    )
    cover_frame = Frame(MARGIN, MARGIN, PAGE_W - 2 * MARGIN, PAGE_H - 2 * MARGIN,
                        id="cover", leftPadding=0, rightPadding=0,
                        topPadding=0, bottomPadding=0)
    body_frame = Frame(MARGIN, 18 * mm, PAGE_W - 2 * MARGIN, PAGE_H - 38 * mm,
                       id="body", leftPadding=0, rightPadding=0,
                       topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], onPage=paint_cover),
        PageTemplate(id="body", frames=[body_frame], onPage=paint_body),
    ])
    return doc


# ==========================================================================
# CONTENT
# ==========================================================================


def cover():
    return [
        Spacer(1, 74 * mm),
        Paragraph("Panel", S["cover_title"]),
        Spacer(1, 7 * mm),
        Paragraph(
            "An interview engine where every score has to cite the transcript, "
            "and the criteria are frozen before a single question is asked.",
            S["cover_sub"],
        ),
        Spacer(1, 52 * mm),
        Paragraph(
            "TECHNICAL DOCUMENTATION<br/>"
            "VERSION 0.1.0 &nbsp;·&nbsp; 19 AUGUST 2026<br/><br/>"
            "5,901 LINES &nbsp;·&nbsp; 47 SOURCE FILES &nbsp;·&nbsp; 81 TESTS<br/>"
            "PYTHON 3.12 &nbsp;·&nbsp; REACT 18 &nbsp;·&nbsp; SQLITE",
            S["cover_meta"],
        ),
        NextPageTemplate("body"),
        PageBreak(),
    ]


def contents():
    entries = [
        ("01", "What Panel is", "The two modes, and the one engine underneath"),
        ("02", "Why it works this way", "The research that set the design"),
        ("03", "The three rules", "Frozen criteria, cited scores, honest gaps"),
        ("04", "Architecture", "Transport-agnostic core, replaceable edges"),
        ("05", "The numbers", "Size, tests, coverage, dependencies"),
        ("06", "Every file explained", "All 47 source files, and why each exists"),
        ("07", "The rubric library", "9 competencies, 36 behavioural anchors"),
        ("08", "The data model", "Where the rules are enforced by types"),
        ("09", "The HTTP API", "9 routes, and what each guarantees"),
        ("10", "The web interface", "Design decisions and what they encode"),
        ("11", "Testing", "What 81 tests actually assert"),
        ("12", "Bugs found while building", "Four real defects, and how each surfaced"),
        ("13", "Status", "Verified, scaffolded, and not built"),
        ("14", "Running it", "Install, commands, ports, keys"),
        ("15", "Appendix", "Commit history and glossary"),
    ]
    rows = [[n, f"<b>{t}</b><br/>{d}"] for n, t, d in entries]
    out = section("CONTENTS", "What is in this document")
    out.append(data_table(rows, [16 * mm, PAGE_W - 2 * MARGIN - 16 * mm],
                          header=False, mono_cols=(0,)))
    out.append(PageBreak())
    return out


def part_one():
    out = section(
        "01",
        "What Panel is",
        "Panel conducts a structured interview, then produces a score in which "
        "every judgement points at the words that produced it.",
    )
    out += [
        para(
            "It runs in two modes over one engine. In <b>practice mode</b> you are the "
            "candidate: you answer, and the output is coaching that tells you what a "
            "stronger answer would have contained. In <b>screening mode</b> somebody "
            "else is the candidate and the output is a scorecard, with each score "
            "attached to the quotes that justify it."
        ),
        para(
            "The two modes are not two products. They share the plan compiler, the "
            "conductor, the evidence extractor and the scorer; they differ only in the "
            "final rendering. That is deliberate — the moment coaching and screening "
            "have separate scoring paths, they start disagreeing about what a level 3 "
            "answer looks like."
        ),
        Paragraph("The thing that makes it different", S["h2"]),
        para(
            "There is no shortage of AI interview tools. Nearly all of them share a "
            "weakness: a model reads an answer and emits a number, and nobody can say "
            "afterwards what the number was based on. If you disagree with a 2 out of "
            "4, there is nothing to inspect."
        ),
        para(
            "Panel is built so that question cannot be dodged. Criteria are compiled "
            "and content-hashed <i>before</i> the interview starts, so the interviewer "
            "cannot drift onto easier ground mid-conversation. A score without a "
            "supporting quote is rejected by the type system, not discouraged by a "
            "prompt. And a competency the interview never reached is recorded as "
            "<i>not observed</i>, kept out of the average entirely, rather than quietly "
            "counted as a zero."
        ),
        callout(
            "THE SHAPE OF IT",
            "Compile a frozen plan from the role, résumé and job description. Conduct "
            "the interview inside that plan, probing where answers are thin. Extract "
            "evidence as you go, tying every claim to a transcript span. Score against "
            "behavioural anchors afterwards, citing that evidence. Render it two ways.",
        ),
        Spacer(1, 5 * mm),
        Paragraph("Who it is for", S["h2"]),
        para(
            "This is a personal tool, built for one person to practise interviews and "
            "occasionally screen someone. It is not a hiring platform. That scope is "
            "load-bearing: it is why sessions live in memory, why there is no "
            "multi-tenancy, and why the compliance posture is <i>build the audit "
            "surface in now because retrofitting it is painful</i> rather than <i>ship "
            "a compliance product</i>."
        ),
        PageBreak(),
    ]
    return out


def part_two():
    out = section(
        "02",
        "Why it works this way",
        "One published finding shaped almost every structural decision in this "
        "codebase.",
    )
    out += [
        para(
            "Before writing any code, the question worth answering was: what actually "
            "makes an LLM's judgement of an interview answer reliable? The literature "
            "on LLM-as-judge scoring is unusually clear about this, and the answer is "
            "not the model."
        ),
        data_table(
            [
                ["SCORING SETUP", "AGREEMENT WITH HUMAN EXPERTS"],
                ["Unanchored — “rate this 1 to 5”", "r ≈ 0.20 — effectively noise"],
                ["Behaviourally-anchored rubric", "r ≈ 0.63"],
                ["Anchors plus annotated critical points",
                 "&gt; 0.89 agreement, even from cheaper judge models"],
            ],
            [78 * mm, PAGE_W - 2 * MARGIN - 78 * mm],
        ),
        Spacer(1, 4 * mm),
        para(
            "The jump from 0.20 to 0.63 comes from replacing adjectives with "
            "observable behaviour. “Shows good judgement” cannot be checked against a "
            "transcript; “names the tradeoff they accepted and what it cost” can. The "
            "jump to 0.89 comes from telling the judge, in advance, what a strong "
            "answer contains."
        ),
        Paragraph(
            "So quality lives in the rubric layer, not the model. Everything else "
            "follows from taking that seriously.",
            S["pull"],
        ),
        Paragraph("What that bought", S["h2"]),
        para(
            "Because the rubric is where the quality is, it made sense to make the "
            "rubric a first-class, versioned object rather than prompt text. That one "
            "decision produced the content hash, which produced comparability between "
            "runs, which is what later made progress tracking meaningful. None of that "
            "was planned up front; it fell out of putting the rubric at the centre."
        ),
        Paragraph("The market", S["h2"]),
        para(
            "The candidate-practice space is crowded — Final Round AI, OphyAI, "
            "Pramp/Exponent, Interviewing.io — but almost entirely closed SaaS. There "
            "is no strong open reference implementation, which made building one "
            "worthwhile rather than redundant."
        ),
        Paragraph("The legal picture", S["h2"]),
        para(
            "Personal use sits outside both regimes, but they shaped the design anyway. "
            "The EU AI Act classes recruitment and screening AI as <b>high-risk</b>, "
            "with obligations applying from 2 December 2027. New York City Local Law "
            "144 already requires an independent annual bias audit, a public summary, "
            "and ten business days' notice to candidates, with enforcement tightened "
            "during 2026."
        ),
        callout(
            "ONE FEATURE DELIBERATELY EXCLUDED",
            "No webcam affect, emotion, or body-language scoring. It is the "
            "weakest-evidence part of commercial AI interviewing, and the EU AI Act "
            "bans emotion recognition in the workplace. Video in Panel exists for "
            "realism and self-review; it is never an input to a score. The camera "
            "stream never leaves the browser.",
        ),
        PageBreak(),
    ]
    return out


def part_three():
    out = section(
        "03",
        "The three rules",
        "Each is enforced by structure — a type, a schema, a hash — rather than "
        "requested politely in a prompt.",
    )
    out += [
        Paragraph("Rule one — criteria are frozen before the interview", S["h2"]),
        para(
            "The plan compiler turns a role, an interview type, and optionally a résumé "
            "and job description into an <b>InterviewPlan</b>: competencies, their "
            "rubric anchors, the critical points a strong answer contains, and the "
            "planned questions. That object is then content-hashed."
        ),
        code_block([
            "plan_hash = sha256(role + type + competencies + questions)[:16]",
            "           → '70bc65ce6c91efcb'",
        ]),
        para(
            "During the interview the conductor may choose <i>which</i> planned "
            "question to ask and <i>how deep</i> to probe. It cannot add a competency, "
            "invent a question, or edit an anchor. Adaptivity happens inside a fixed "
            "frame. Two interviews carrying the same hash were assessed against "
            "byte-identical criteria — which is what makes their scores comparable at "
            "all."
        ),
        Paragraph("Rule two — no citation, no score", S["h2"]),
        para(
            "A <b>CompetencyScore</b> with a numeric level and no supporting evidence "
            "raises a validation error. It is not possible to construct one. When the "
            "LLM path returns evidence, each quote is checked against the transcript "
            "and dropped if it is not found verbatim."
        ),
        callout(
            "WHY VERIFY THE QUOTES",
            "A fabricated citation is worse than no citation. A missing quote is "
            "visibly missing; an invented one makes an unsupported score look "
            "auditable. The check is cheap, so it runs on every piece of evidence.",
            colour=colors.HexColor("#A8452F"),
        ),
        Spacer(1, 4 * mm),
        Paragraph("Rule three — not observed is not zero", S["h2"]),
        para(
            "If the interview never gathered evidence for a competency, its level is "
            "<b>None</b>. It is excluded from the overall average rather than counted "
            "as zero, reported separately in both renderings, and coverage is always "
            "shown alongside the score."
        ),
        para(
            "The distinction matters because the two things have opposite meanings. A "
            "low score says the candidate answered badly. Not observed says <i>the "
            "interview failed to ask</i>. Averaging them together blames the candidate "
            "for the interviewer's omission."
        ),
        para(
            "This rule holds all the way down. In the SQLite schema the level column is "
            "nullable, so <b>AVG()</b> skips it. The domain model refuses to average an "
            "unobserved competency as zero; the database refuses too. The rule is not "
            "re-argued at each layer."
        ),
        PageBreak(),
    ]
    return out


def part_four():
    out = section(
        "04",
        "Architecture",
        "The valuable part is transport-agnostic. Audio, video and avatars wrap it; "
        "they never leak inward.",
    )
    out += [
        para(
            "The engine consumes a string of candidate speech and returns a string for "
            "the interviewer to say, plus the decision behind it. It knows nothing "
            "about sockets, audio or browsers. Everything else is an adapter."
        ),
        code_block([
            "  résumé + job description + role",
            "         │",
            "         ▼",
            "  [ PlanCompiler ] ─────▶  InterviewPlan   (hashed, FROZEN)",
            "                                  │",
            "  candidate turn ─▶ [ Conductor ] ┴─▶ interviewer turn",
            "                          │           + ASK│PROBE│ADVANCE│CLOSE",
            "                          ▼",
            "                   [ Transcript ]",
            "                          │",
            "                          ▼",
            "                   [ BarsScorer ] ─────▶  cited CompetencyScores",
            "                          │",
            "            ┌─────────────┴─────────────┐",
            "            ▼                           ▼",
            "     CoachingReport              ScreeningReport",
            "       (practice)                  (screening)",
        ]),
        Paragraph("Why this shape", S["h2"]),
        *bullets([
            "The whole engine is testable with no audio, no network and no API key — "
            "the suite runs in under two seconds.",
            "Rubric iteration, which sets the quality ceiling, costs nothing.",
            "Cheap by default: the text path bills nothing, and the avatar is an "
            "explicit opt-in rather than a default.",
            "A live-coding interview later becomes a new plan type, not a rewrite.",
        ]),
        Spacer(1, 3 * mm),
        Paragraph("Three transports, one engine", S["h2"]),
        data_table(
            [
                ["TRANSPORT", "STATUS", "WHAT IT DOES"],
                ["Text", "Verified",
                 "Terminal interview. Nine lines of loop, because the engine does the work."],
                ["HTTP", "Verified",
                 "FastAPI session API behind the browser UI. Holds sessions, moves text."],
                ["Realtime", "Scaffolded",
                 "LiveKit voice with optional avatar. Never run against a live room."],
            ],
            [26 * mm, 24 * mm, PAGE_W - 2 * MARGIN - 50 * mm],
        ),
        Paragraph("The four decisions", S["h2"]),
        para(
            "After every candidate answer the conductor returns exactly one of these. "
            "The set is deliberately small — a state machine with four moves is one you "
            "can reason about, and every move stays inside the frozen plan."
        ),
        data_table(
            [
                ["DECISION", "WHEN", "WHAT IT MEANS"],
                ["ASK", "The answer covered its critical points, or probing is spent",
                 "Move to the next planned question in the same competency"],
                ["PROBE", "Points are missing and the probe cap is not reached",
                 "Follow up on this answer, targeting the most valuable gap"],
                ["ADVANCE", "This competency's questions or time share are done",
                 "Cross into the next competency"],
                ["CLOSE", "The plan is exhausted or the global budget is spent",
                 "End the interview and score it"],
            ],
            [22 * mm, 58 * mm, PAGE_W - 2 * MARGIN - 80 * mm],
            mono_cols=(0,),
        ),
        Spacer(1, 4 * mm),
        callout(
            "THE REALTIME DESIGN DECISION",
            "LiveKit's standard pattern is speech-to-text → LLM → text-to-speech, with "
            "the model deciding what to say. That is exactly wrong here: the conductor "
            "has already decided, from a frozen plan, and a model in the loop would "
            "improvise questions outside it. AgentSession takes the LLM as optional, so "
            "the wiring is STT → Conductor → TTS. The reasoner still runs — for judging "
            "and scoring — just off the speech path where its latency cannot stall the "
            "conversation.",
        ),
        PageBreak(),
    ]
    return out


def part_five():
    out = section("05", "The numbers", "Everything below was measured, not estimated.")
    out += [
        stat_strip([
            ("5,901", "TOTAL LINES"),
            ("47", "SOURCE FILES"),
            ("81", "TESTS"),
            ("1.3s", "SUITE RUNTIME"),
            ("4", "COMMITS"),
        ]),
        Spacer(1, 3 * mm),
        Paragraph("Where the code lives", S["h3"]),
        data_table(
            [
                ["AREA", "FILES", "LINES", "WHAT IT IS"],
                ["Python engine", "24", "3,297",
                 "Models, rubric library, compiler, conductor, scoring, storage, transports, CLI, API"],
                ["Tests", "6", "1,148",
                 "81 tests across models, engine, scoring, API, storage, realtime gate"],
                ["Web app", "9", "1,456",
                 "React video-call UI, history view, stylesheet"],
                ["<b>Total</b>", "<b>39</b>", "<b>5,901</b>",
                 "Plus configuration: pyproject, package.json, launch.json, dev.sh, README, design spec"],
            ],
            [30 * mm, 15 * mm, 17 * mm, PAGE_W - 2 * MARGIN - 62 * mm],
            align_right=(1, 2),
        ),
        Paragraph("The rubric library in numbers", S["h3"]),
        stat_strip([
            ("9", "COMPETENCIES"),
            ("36", "BEHAVIOURAL ANCHORS"),
            ("36", "CRITICAL POINTS"),
            ("18", "BANK QUESTIONS"),
        ]),
        Spacer(1, 2 * mm),
        para(
            "Five behavioural competencies — ownership, handling disagreement, "
            "structured problem solving, learning from failure, communication. Four "
            "technical — systems design tradeoffs, debugging methodology, depth of "
            "fundamentals, code quality judgement. Each carries four anchors and four "
            "critical points.",
            "caption",
        ),
        Paragraph("Dependencies", S["h3"]),
        data_table(
            [
                ["GROUP", "PACKAGES", "NEEDED FOR"],
                ["runtime", "pydantic, anthropic, rich", "The engine and terminal interface"],
                ["api", "fastapi, uvicorn", "The HTTP transport and web UI"],
                ["dev", "pytest, httpx", "The test suite"],
                ["realtime", "livekit-agents and three plugins", "Voice — optional, never required"],
            ],
            [22 * mm, 62 * mm, PAGE_W - 2 * MARGIN - 84 * mm],
            mono_cols=(0, 1),
        ),
        Spacer(1, 3 * mm),
        para(
            "The runtime set is deliberately small. Nothing in the realtime or API "
            "groups is needed to run an interview in the terminal or to run the tests.",
            "caption",
        ),

        PageBreak(),
        Paragraph("Every source file by size", S["h3"]),
        para(
            "The full Python engine, largest first. The rubric library leads because "
            "that is where the quality ceiling is set, not because it is complicated.",
            "caption",
        ),
        data_table(
            [
                ["FILE", "LINES", "ROLE"],
                ["panel/planning/library.py", "368", "The rubric library — 9 competencies, 36 anchors"],
                ["panel/api/app.py", "327", "HTTP transport, 9 routes, session store"],
                ["panel/llm/heuristic.py", "315", "Keyless reasoner — signal detection"],
                ["panel/models.py", "292", "Domain model; two rules enforced as types"],
                ["panel/llm/anthropic.py", "289", "Claude-backed reasoner with quote verification"],
                ["panel/engine/conductor.py", "265", "The interview state machine"],
                ["panel/cli.py", "233", "Terminal interface, five commands"],
                ["panel/scoring/report.py", "230", "One report object, several renderings"],
                ["panel/storage/db.py", "220", "Append-only SQLite store"],
                ["panel/transports/realtime.py", "217", "LiveKit voice transport (unverified)"],
                ["panel/demo_answers.py", "128", "Scripted answers, keyed by competency"],
                ["panel/planning/compiler.py", "100", "Builds and freezes the plan"],
                ["panel/llm/base.py", "76", "The Reasoner protocol"],
                ["panel/scoring/scorer.py", "74", "Scores against anchors, cites evidence"],
                ["panel/transports/text.py", "44", "Terminal transport — nine lines of loop"],
                ["panel/config.py", "34", "Settings; demo mode when no key is present"],
                ["seven __init__.py files", "62", "Public surfaces for each package"],
            ],
            [52 * mm, 14 * mm, PAGE_W - 2 * MARGIN - 66 * mm],
            mono_cols=(0,), align_right=(1,),
        ),
        PageBreak(),
    ]
    return out


def part_six():
    out = section(
        "06",
        "Every file explained",
        "All 47 source files, grouped by package, with what each does and why it "
        "exists rather than being folded into something else.",
    )

    groups = [
        (
            "panel/ — the root",
            "Configuration and the domain model everything else depends on.",
            [
                ("models.py", "292",
                 "The domain model, and where two of the three rules become "
                 "unbreakable. <b>CompetencyScore</b> raises if given a level with no "
                 "supporting evidence. <b>Competency</b> raises unless it carries "
                 "exactly four anchors. <b>InterviewPlan.plan_hash</b> content-hashes "
                 "the criteria, excluding id and timestamp so identical criteria hash "
                 "identically. Also holds Transcript, Turn, Evidence and the "
                 "ScoredInterview aggregate whose overall() excludes unobserved "
                 "competencies rather than zeroing them."),
                ("config.py", "34",
                 "Settings from the environment. The important line is "
                 "<b>demo_mode</b>: no API key means the heuristic reasoner runs and "
                 "everything still works. max_tokens defaults high because thinking is "
                 "on by default on Opus 5 and the budget covers thinking plus output."),
                ("cli.py", "233",
                 "Five commands — practice, screen, demo, history — over the same "
                 "engine. Renders reports with rich, records finished interviews, and "
                 "tells you when a run is comparable to earlier ones."),
                ("demo_answers.py", "128",
                 "Seventeen scripted answers across nine competencies, keyed by "
                 "competency rather than held in a list. A positional script drifts out "
                 "of alignment the moment a probe fires. Deliberately uneven — strong "
                 "answers, thin ones, and one genuine non-answer — so a demo exercises "
                 "every branch of the conductor."),
            ],
        ),
        (
            "panel/planning/ — compiling the plan",
            "Turns a role and some documents into frozen criteria.",
            [
                ("library.py", "368",
                 "The vetted rubric library, and the highest-value file in the "
                 "repository. Nine competencies, each with four behavioural anchors and "
                 "four critical points. Every descriptor describes something observable "
                 "in an answer — never a trait. This is where the r=0.63 lives."),
                ("compiler.py", "100",
                 "Builds the InterviewPlan and freezes it. With a reasoner and a "
                 "résumé or job description, questions are drafted against the real "
                 "role; without, the vetted bank is used. The rubric is identical "
                 "either way — only questions become role-specific, because the rubric "
                 "is what must stay stable for scores to mean anything."),
                ("__init__.py", "4", "Public surface: compile_plan, competencies_for."),
            ],
        ),
        (
            "panel/engine/ — conducting the interview",
            "The state machine. Transport-agnostic by construction.",
            [
                ("conductor.py", "265",
                 "Consumes candidate text, returns interviewer text plus a decision — "
                 "ASK, PROBE, ADVANCE or CLOSE. Tracks evidence coverage per "
                 "competency. Carries two budgets: a global exchange ceiling and a "
                 "per-competency share, the second added after the first build proved "
                 "depth-first and never reached the later competencies. Exposes "
                 "Progress and current_question for any UI to render."),
                ("__init__.py", "3", "Exports Conductor and Step."),
            ],
        ),
        (
            "panel/llm/ — judgement calls",
            "A domain-level interface, not a raw prompt wrapper. That is what lets the "
            "keyless implementation be a real peer rather than a stub.",
            [
                ("base.py", "76",
                 "The Reasoner protocol: draft_questions, assess_answer, score, coach. "
                 "Deliberately domain-level — the conductor asks “was this answer "
                 "substantive and what did it miss?”, never “here is a prompt”. Keeps "
                 "prompt engineering out of the state machine."),
                ("heuristic.py", "315",
                 "The keyless reasoner. Not an imitation of a language model: it "
                 "detects the six observable signals the rubrics are written around — "
                 "specificity, first-person agency, stated outcomes, considered "
                 "alternatives, reflection, method — and reports honestly on what it "
                 "cannot see. Spelled-out numerals count as specificity because "
                 "speech-to-text writes “two days”, not “2 days”."),
                ("anthropic.py", "289",
                 "The Claude-backed reasoner. Structured output through "
                 "messages.parse() with Pydantic models, so the engine never parses "
                 "free text. Verifies every quote against the transcript and drops "
                 "unverifiable ones. Any API failure degrades to the heuristic rather "
                 "than crashing an interview in progress."),
                ("__init__.py", "25",
                 "get_reasoner() — picks the Claude reasoner when a key exists, the "
                 "heuristic otherwise."),
            ],
        ),
        (
            "panel/scoring/ — judging and rendering",
            "Separate from conducting on purpose: during the interview the engine "
            "optimises for a good conversation, here for a defensible judgement.",
            [
                ("scorer.py", "74",
                 "Scores each competency against its anchors using only extracted "
                 "evidence. A competency with no supporting evidence returns NOT "
                 "OBSERVED without consulting the reasoner at all — and if a reasoner "
                 "returns a level anyway, it is discarded."),
                ("report.py", "230",
                 "One Report object, several renderings. build_report is the source of "
                 "truth; the CLI renders text from it, the API serialises it as JSON. "
                 "Refactored to this shape when the browser arrived, so the two "
                 "surfaces cannot drift about what a score means."),
                ("__init__.py", "21", "Public surface for scoring and reports."),
            ],
        ),
        (
            "panel/storage/ — the record",
            "Append-only, because a scorecard you can quietly edit afterwards is not a "
            "record.",
            [
                ("db.py", "220",
                 "SQLite store. Two tables: interviews (summary plus the full report "
                 "JSON) and competency_scores (one row per competency, level nullable). "
                 "No update or delete path exists. trends() is scoped to a single "
                 "plan_hash, because interviews compiled from different criteria are "
                 "not comparable and charting them together would hide that."),
                ("__init__.py", "23", "Public surface for the store."),
            ],
        ),
        (
            "panel/transports/ — the edges",
            "Adapters. They move text in and out; they make no decisions.",
            [
                ("text.py", "44",
                 "The terminal transport. Nine lines of actual loop, because the engine "
                 "does the work. A realtime transport substitutes different say and "
                 "listen callables and changes nothing else."),
                ("realtime.py", "217",
                 "LiveKit voice with optional avatar. Written against livekit-agents "
                 "1.6.10 with the API verified by introspection, but never run against "
                 "a live room. Contains the credential gate, which is tested, and the "
                 "call path, which is not."),
                ("__init__.py", "3", "Exports run_interview."),
            ],
        ),
        (
            "panel/api/ — the HTTP transport",
            "A transport like the CLI. Every interview decision stays in the engine.",
            [
                ("app.py", "327",
                 "FastAPI application: nine routes, in-memory session store, SQLite "
                 "connection opened on the app lifespan. Persists an interview when it "
                 "finishes, whether or not anyone asks to see the report."),
                ("__init__.py", "3", "Exports the app."),
            ],
        ),
        (
            "web/src/ — the browser interface",
            "React 18 on Vite 5. Hand-written CSS with custom properties; no framework.",
            [
                ("App.jsx", "170",
                 "Phase machine — setup, running, done, history — plus the timer, the "
                 "demo-mode banner and the topbar carrying the rubric hash."),
                ("components/Setup.jsx", "132",
                 "Role, focus, length, mode, and optional résumé and job description."),
                ("components/Call.jsx", "120",
                 "The video-call stage: interviewer tile, your camera, the current "
                 "question in serif, the composer, and a side rail with progress and "
                 "live transcript."),
                ("components/Selfie.jsx", "44",
                 "Your camera via getUserMedia, attached to a local video element. "
                 "Never uploaded, never scored. Degrades to “Camera off” when denied."),
                ("components/Report.jsx", "176",
                 "The report on paper. Holds the signature interaction: clicking a "
                 "citation lights and scrolls to the transcript turn it came from."),
                ("components/History.jsx", "147",
                 "Past interviews and per-competency progress, scoped to one rubric "
                 "version with that constraint stated on the page."),
                ("api.js", "45",
                 "Thin fetch client. Surfaces the server's own message, so a 409 reads "
                 "as “this interview is already finished” rather than “request failed”."),
                ("styles.css", "612",
                 "The whole design system: ink call, paper report, one amber accent, "
                 "three type roles, responsive down to 375px."),
                ("main.jsx", "10", "React root."),
            ],
        ),
        (
            "tests/ — 81 tests",
            "The suite runs in 1.3 seconds with no key and no network.",
            [
                ("test_models.py", "174 · 14 tests",
                 "The rules as types: rubrics must have four anchors, scores must cite, "
                 "hashes must be stable, unobserved must not be averaged as zero."),
                ("test_engine.py", "217 · 12 tests",
                 "Conductor transitions with a stub reasoner, so decision logic is the "
                 "only variable. Includes the breadth-before-depth budget guarantee."),
                ("test_scoring.py", "231 · 13 tests",
                 "Heuristic signal detection, scorer rules, and a full end-to-end "
                 "interview asserting every scored competency cites a real quote."),
                ("test_api.py", "254 · 24 tests",
                 "The HTTP contract, including that history records a finished "
                 "interview without being asked and that an abandoned one is not "
                 "recorded."),
                ("test_storage.py", "196 · 12 tests",
                 "Append-only guarantees, NULL semantics surviving into SQL, and "
                 "trends excluding other rubric versions."),
                ("test_realtime_gate.py", "76 · 6 tests",
                 "The credential gate — the only part of the realtime transport "
                 "testable without a live room."),
            ],
        ),
        (
            "Configuration and documentation",
            "",
            [
                ("pyproject.toml", "—",
                 "Package metadata and four dependency groups: runtime, api, dev, "
                 "realtime."),
                ("dev.sh", "—",
                 "Runs the API on 8040 and the web app on 5193 together, with the API "
                 "killed on exit."),
                (".claude/launch.json", "—",
                 "Preview configuration for the dev server."),
                ("web/vite.config.js", "—",
                 "Vite 5 on port 5193, proxying /api to 8040."),
                ("README.md", "—",
                 "Orientation, the three rules, usage, and an explicit statement of "
                 "what is verified versus scaffolded."),
                ("docs/…/panel-design.md", "—",
                 "The design document, including decisions made mid-build and why."),
            ],
        ),
    ]

    for title, blurb, files in groups:
        block = [Paragraph(title, S["h2"])]
        if blurb:
            block.append(para(blurb, "caption"))
        rows = [["FILE", "LINES", "WHAT IT DOES AND WHY"]]
        rows += [[f, n, d] for f, n, d in files]
        block.append(data_table(
            rows,
            [40 * mm, 21 * mm, PAGE_W - 2 * MARGIN - 61 * mm],
            mono_cols=(0,),
        ))
        block.append(Spacer(1, 3 * mm))
        out.append(KeepTogether(block) if len(files) <= 4 else block[0])
        if len(files) > 4:
            out += block[1:]

    out.append(PageBreak())
    return out


def part_seven():
    out = section(
        "07",
        "The rubric library",
        "Nine competencies, thirty-six anchors. Every descriptor describes something "
        "observable in an answer — never a trait of the person.",
    )
    out += [
        para(
            "This is the file that sets the quality ceiling, so it is worth seeing what "
            "an anchor actually looks like. Below is the complete rubric for "
            "<b>Ownership</b>, one of five behavioural competencies."
        ),
        data_table(
            [
                ["LEVEL", "OBSERVABLE IN THE ANSWER"],
                ["1 — Weak",
                 "Speaks only in the plural about team activity; no personal action is "
                 "identifiable. Or names a responsibility held without any instance of "
                 "exercising it."],
                ["2 — Developing",
                 "Names a personal action, but it stays inside assigned duties. "
                 "Ownership stops at the task boundary; hand-offs are described as the "
                 "end of their involvement."],
                ["3 — Strong",
                 "Names a specific problem they took on that nobody assigned them, the "
                 "action they personally took, and the outcome it produced."],
                ["4 — Exceptional",
                 "As Strong, and they changed the system rather than the instance — a "
                 "process, guardrail, test, or norm that outlived the incident and "
                 "prevented recurrence."],
            ],
            [26 * mm, PAGE_W - 2 * MARGIN - 26 * mm],
        ),
        Spacer(1, 3 * mm),
        para(
            "Each competency also carries <b>critical points</b> — the concrete things "
            "a strong answer contains. These drive both probing during the interview "
            "and scoring afterwards. For Ownership: a specific incident rather than a "
            "general practice; their own action stated separately from the team's; an "
            "outcome that is observable or measurable; evidence they went past what was "
            "assigned.",
            "caption",
        ),
        Paragraph("The full set", S["h2"]),
        data_table(
            [
                ["COMPETENCY", "TYPE", "WHAT IT ASSESSES"],
                ["Ownership", "behavioural", "Responsibility beyond assigned tasks"],
                ["Handling Disagreement", "behavioural", "Navigating conflict toward a decision"],
                ["Structured Problem Solving", "behavioural", "Decomposing ambiguity methodically"],
                ["Learning From Failure", "behavioural", "Extracting transferable lessons"],
                ["Communication", "behavioural", "Conveying complex work to a listener"],
                ["Systems Design Tradeoffs", "technical", "Reasoning about what each option costs"],
                ["Debugging Methodology", "technical", "Isolating cause systematically, not by guesswork"],
                ["Depth of Fundamentals", "technical", "Understanding what sits under the abstractions"],
                ["Code Quality Judgement", "technical", "When structure is worth it and when it is waste"],
            ],
            [50 * mm, 24 * mm, PAGE_W - 2 * MARGIN - 74 * mm],
        ),
        Spacer(1, 3 * mm),
        para(
            "A behavioural interview draws the five behavioural competencies; a "
            "technical-verbal interview the four technical ones; a mixed interview "
            "takes the behavioural core plus the two highest-signal technical ones.",
            "caption",
        ),
        PageBreak(),
    ]
    return out


def part_eight():
    out = section(
        "08",
        "The data model",
        "Where the rules stop being conventions and become things the program cannot "
        "express.",
    )
    out += [
        data_table(
            [
                ["TYPE", "WHAT IT GUARANTEES"],
                ["RubricLevel",
                 "One behaviourally-anchored level: a number 1–4, a label, and a "
                 "descriptor of at least ten characters describing observable behaviour."],
                ["Competency",
                 "Raises unless it carries exactly levels 1 through 4. A three-anchor "
                 "or duplicate-level rubric cannot be constructed."],
                ["InterviewPlan",
                 "Validates that every question references a known competency and that "
                 "at least one question exists. Exposes plan_hash — sha256 over the "
                 "criteria, excluding id and timestamp."],
                ["Transcript / Turn",
                 "Append-only conversation with stable integer indices. Turn indices are "
                 "what citations point at."],
                ["Evidence",
                 "A claim tied to (competency, turn index, quoted span), with polarity "
                 "either supporting or undermining."],
                ["CompetencyScore",
                 "<b>Raises if given a level with no supporting evidence.</b> level=None "
                 "means not observed, which is a legitimate and distinct outcome."],
                ["ScoredInterview",
                 "overall() is a weighted mean over observed competencies only; coverage "
                 "is reported separately so a thin interview is visible rather than "
                 "hidden behind a confident number."],
            ],
            [34 * mm, PAGE_W - 2 * MARGIN - 34 * mm],
            mono_cols=(0,),
        ),
        Spacer(1, 4 * mm),
        callout(
            "THE POINT OF PUTTING IT IN TYPES",
            "A prompt asking a model to “always cite evidence” is a request. A "
            "constructor that refuses to build the object is a guarantee. Every layer "
            "downstream — the scorer, the reports, the API, the database — inherits "
            "that guarantee without having to re-check it.",
        ),
        PageBreak(),
    ]
    return out


def part_nine():
    out = section("09", "The HTTP API", "Nine routes. FastAPI, with Pydantic models on "
                                         "both the request and response side.")
    out += [
        data_table(
            [
                ["METHOD", "ROUTE", "WHAT IT DOES"],
                ["GET", "/api/health",
                 "Which reasoner is live, and an explicit note that sessions are held in memory"],
                ["POST", "/api/sessions",
                 "Compiles a frozen plan, opens a conductor, returns the plan summary and first question"],
                ["POST", "/api/sessions/{id}/answer",
                 "One candidate turn in, one interviewer move out, with progress. 409 if already finished"],
                ["GET", "/api/sessions/{id}",
                 "Current state and transcript — survives a page reload"],
                ["GET", "/api/sessions/{id}/report",
                 "The scored report. 409 while the interview is still running"],
                ["DELETE", "/api/sessions/{id}",
                 "Drops the in-memory session; a finished interview stays in the store"],
                ["GET", "/api/history",
                 "Past interviews, newest first, optionally filtered by role"],
                ["GET", "/api/history/{id}",
                 "A past report, citations intact"],
                ["GET", "/api/trends/{plan_hash}",
                 "Per-competency progress across runs of one rubric version only"],
            ],
            [18 * mm, 50 * mm, PAGE_W - 2 * MARGIN - 68 * mm],
            mono_cols=(0, 1),
        ),
        Paragraph("Two behaviours worth knowing", S["h2"]),
        *bullets([
            "<b>Finishing records the interview.</b> Persistence happens when the "
            "conductor closes, not when someone requests the report — so an interview "
            "you never look at is still in your history, and an abandoned one is not.",
            "<b>Trends refuse to mix rubrics.</b> The route is keyed by plan_hash and "
            "returns a note saying so. Comparability is what freezing the plan bought; "
            "quietly averaging across criteria would spend it for nothing.",
        ]),
        PageBreak(),
    ]
    return out


def part_ten():
    out = section(
        "10",
        "The web interface",
        "The structural decision: the call is dark, the report is paper. Two phases, "
        "two genuinely different objects.",
    )
    out += [
        para(
            "A live conversation and a filed record are not the same kind of thing, and "
            "the interface says so by inverting between them. During the call you are "
            "in a dark video-call surface. When it ends you are looking at a document."
        ),
        Paragraph("The design system", S["h2"]),
        data_table(
            [
                ["ELEMENT", "CHOICE", "WHY"],
                ["Call ground", "ink #11151C", "Video-call surface; attention on the exchange"],
                ["Report ground", "paper #E9EBEE", "A cool printed-script white, not the warm cream default"],
                ["Accent", "amber #C98A2B", "Used only for citation marks and the live indicator"],
                ["Not observed", "mute #7A8494", "Hollow dashed scale — never reads as a low score"],
                ["Spoken question", "Instrument Serif", "The words being said aloud, set apart from the interface"],
                ["Interface", "IBM Plex Sans", "Technical without being Inter"],
                ["The record layer", "IBM Plex Mono", "Turn indices, rubric hashes, timers — true to the content"],
            ],
            [30 * mm, 34 * mm, PAGE_W - 2 * MARGIN - 64 * mm],
        ),
        Paragraph("The signature interaction", S["h2"]),
        para(
            "Every piece of evidence in a report is a button carrying its turn index. "
            "Clicking it lights the source turn in the full transcript below and scrolls "
            "it into view. A score can always be walked back to the words that produced "
            "it, in one click."
        ),
        para(
            "This was verified on a report that had been serialised to SQLite and "
            "restored: citation T25 still landed on turn T25, with the quoted text "
            "present in that turn. The audit trail survives persistence, which is the "
            "whole claim."
        ),
        callout(
            "WHAT THE CAMERA IS FOR",
            "Your camera appears in the corner of the call for realism and self-review. "
            "The stream is attached to a local video element and never leaves the "
            "browser — not uploaded, not recorded, not scored. When permission is "
            "denied the tile reads “Camera off” and the interview continues unaffected.",
        ),
        PageBreak(),
    ]
    return out


def part_eleven():
    out = section(
        "11",
        "Testing",
        "81 tests in 1.3 seconds, with no API key and no network. That speed is the "
        "payoff from keeping the engine transport-agnostic.",
    )
    out += [
        stat_strip([
            ("81", "TESTS"), ("6", "FILES"), ("1,148", "LINES"), ("1.3s", "RUNTIME"),
        ]),
        Spacer(1, 3 * mm),
        para(
            "The tests are written against behaviour rather than implementation, and "
            "several of them exist specifically to stop a rule from quietly eroding."
        ),
        Paragraph("Tests that guard the three rules", S["h2"]),
        data_table(
            [
                ["TEST", "WHAT WOULD BREAK WITHOUT IT"],
                ["test_score_without_evidence_is_rejected",
                 "A score could be emitted with nothing behind it"],
                ["test_undermining_evidence_alone_does_not_justify_a_score",
                 "Counter-evidence could be miscounted as support"],
                ["test_unobserved_excluded_from_overall_not_counted_as_zero",
                 "A thin interview would read as a bad candidate"],
                ["test_hash_changes_when_an_anchor_changes",
                 "Criteria could drift while still claiming comparability"],
                ["test_a_fabricated_level_is_downgraded_not_trusted",
                 "A misbehaving reasoner could inject an uncited score"],
                ["test_probes_never_echo_internal_rubric_wording",
                 "The interviewer would read the answer key aloud"],
                ["test_every_competency_gets_asked…",
                 "The conductor would exhaust its budget on the first topic"],
                ["test_sql_average_skips_unobserved_rather_than_counting_zero",
                 "The NULL rule would hold in Python and break in SQL"],
            ],
            [72 * mm, PAGE_W - 2 * MARGIN - 72 * mm],
            mono_cols=(0,),
        ),
        Paragraph("A test design decision worth noting", S["h2"]),
        para(
            "The end-to-end test originally asserted 100% coverage, which conflated two "
            "different responsibilities. It now hard-asserts the <b>engine</b> "
            "invariant — the conductor must ask about every competency it planned to "
            "assess — and holds <b>reasoner recall</b> to a separate, lower bar. The "
            "conductor's job is to ask; extraction quality is somebody else's job, and "
            "the keyless reasoner is explicitly held to a weaker standard than the LLM "
            "path."
        ),
        PageBreak(),
    ]
    return out


def part_twelve():
    out = section(
        "12",
        "Bugs found while building",
        "Four real defects. Three were invisible to the test suite and only appeared "
        "when the thing was actually run.",
    )
    bugs = [
        ("01",
         "The interviewer read the answer key aloud",
         "A probe rendered as: “Say more about this: evidence they went past what was "
         "assigned.” That is an internal rubric string — it tells the candidate exactly "
         "which box to tick.",
         "Probes now come from a bank of interviewer-voiced follow-ups, rotated so a "
         "long interview never repeats one verbatim. A regression test asserts no probe "
         "ever contains a critical point's own wording.",
         "Running the demo and reading the output"),
        ("02",
         "The conductor was depth-first",
         "It probed the opening competency until the clock ran out and never asked "
         "about the last three. A 30-minute mixed interview assessed 2 of 5 "
         "competencies — producing a confident score on one area and NOT OBSERVED "
         "everywhere else.",
         "A per-competency budget alongside the global one. Breadth first, depth "
         "second: an interview that covered two of five competencies is a worse "
         "interview however good those two scores are.",
         "Instrumenting a run and printing what was actually asked"),
        ("03",
         "Nothing scrolled inside the page",
         "The app shell used min-height, so it grew to 7,503 pixels. The report's "
         "overflow never engaged, the whole document scrolled as one column, and the "
         "topbar carrying the rubric hash scrolled away.",
         "The shell is now exactly viewport height, so the call and the report each "
         "scroll inside their own box.",
         "Measuring element geometry in the browser"),
        ("04",
         "The citation jump was silently dead",
         "Clicking a citation highlighted the right turn but never moved the page — "
         "losing half the feature. The first fix made it worse: adding CSS "
         "scroll-behavior broke it again, with scrollTop measurably stuck at 2000 "
         "through a direct assignment.",
         "In this engine, smooth scrolling from either source drops the scroll "
         "entirely, not just the animation. Assigning scrollTop with no smooth "
         "behaviour anywhere is the only reliable form. The amber highlight does the "
         "orienting instead.",
         "Three wrong guesses, then measuring scrollTop directly"),
    ]

    for num, title, symptom, fix, found in bugs:
        block = [
            Paragraph(f"{num} &nbsp;&nbsp; {title}", S["h2"]),
            data_table(
                [
                    ["Symptom", symptom],
                    ["Fix", fix],
                    ["Found by", f"<i>{found}</i>"],
                ],
                [24 * mm, PAGE_W - 2 * MARGIN - 24 * mm],
                header=False,
            ),
            Spacer(1, 3 * mm),
        ]
        # The closing callout rides with the last bug so it can never strand on a
        # page of its own.
        if num == bugs[-1][0]:
            block += [
                Spacer(1, 2 * mm),
                callout(
                    "THE PATTERN",
                    "Every one of these passed the test suite. Three needed the "
                    "application to be run and looked at; the fourth needed a "
                    "measurement rather than a hypothesis. On the citation bug "
                    "specifically, three plausible fixes failed in a row and the "
                    "measurement found the cause immediately — which is an argument "
                    "for measuring earlier, not for guessing more carefully.",
                ),
            ]
        out.append(KeepTogether(block))

    out.append(PageBreak())
    return out


def part_thirteen():
    out = section(
        "13",
        "Status",
        "What is verified, what is scaffolded, and what does not exist. Stated plainly "
        "because the distinction matters more than the total.",
    )
    out += [
        Paragraph("Verified — built, tested, and run", S["h2"]),
        data_table(
            [
                ["COMPONENT", "HOW IT WAS VERIFIED"],
                ["Domain model and rubric library", "14 tests; every anchor checked for substance"],
                ["Plan compiler and hashing", "Hash stability and sensitivity both tested"],
                ["Conductor", "12 tests over transitions and both budgets"],
                ["Evidence extraction and scoring", "13 tests, plus end-to-end citation checking"],
                ["Both report renderings", "Rendered and read in terminal and browser"],
                ["Text transport and CLI", "Full interviews run end to end with no key"],
                ["HTTP API", "24 tests over the contract, including failure modes"],
                ["Web video-call UI", "Complete interviews driven through the browser in both modes"],
                ["Persistence and history", "12 tests; citation integrity verified after a SQLite round trip"],
            ],
            [58 * mm, PAGE_W - 2 * MARGIN - 58 * mm],
        ),
        Paragraph("Scaffolded — written, reviewed, never run", S["h2"]),
        para(
            "The realtime voice transport. It is written against livekit-agents 1.6.10 "
            "with the API surface verified by introspection rather than recalled, and "
            "the credential gate is tested. <b>The call path has never been executed "
            "against a live room</b>, because that needs LiveKit, speech-to-text, "
            "text-to-speech and avatar credentials. The module says so in its own "
            "docstring. Treat it as reviewed scaffolding."
        ),
        Paragraph("Known limitations", S["h2"]),
        *bullets([
            "An interview <b>in progress</b> lives only in memory. Restarting the "
            "server loses it. Finished interviews are persisted; resuming a "
            "half-finished one is not supported.",
            "The keyless reasoner has real limits in both recall and precision. It can "
            "miss a strong answer whose anchors fall outside its six signals, and it "
            "can attach a genuine quote to the wrong critical point. Heuristic-mode "
            "levels are indicative, not defensible.",
            "There is no authentication, no multi-tenancy and no rate limiting. It is a "
            "personal tool bound to localhost.",
        ]),
        Paragraph("Not built", S["h2"]),
        para(
            "The live-coding interview type. It needs a shared editor, a sandboxed "
            "runtime and code-aware scoring, and it sits awkwardly inside a "
            "talking-head video call. It was scoped out of the first cut deliberately "
            "rather than forgotten."
        ),
        PageBreak(),
    ]
    return out


def part_fourteen():
    out = section("14", "Running it", "Everything below works with no API key.")
    out += [
        Paragraph("Install", S["h3"]),
        code_block([
            "python3 -m venv .venv",
            ".venv/bin/pip install -e \".[api,dev]\"",
            "cd web && npm install",
        ]),
        Paragraph("Terminal", S["h3"]),
        code_block([
            "panel demo                                    scripted, deterministic",
            "panel practice --role \"Backend Engineer\" --minutes 20",
            "panel screen   --role \"Backend Engineer\" --resume cv.txt --jd role.txt",
            "panel history                                 past runs and progress",
        ]),
        Paragraph("Browser", S["h3"]),
        code_block([
            "./dev.sh          API on :8040, web app on :5193",
        ]),
        para(
            "Those ports were chosen to avoid the other projects already claiming 8000, "
            "8001, 8010, 8020, 8030 and 5173. On another machine any free pair will do.",
            "caption",
        ),
        Paragraph("Optional credentials", S["h3"]),
        data_table(
            [
                ["VARIABLE", "UNLOCKS"],
                ["ANTHROPIC_API_KEY", "The Claude reasoner. Without it the heuristic runs and everything still works"],
                ["PANEL_MODEL", "Model override; defaults to claude-opus-5"],
                ["PANEL_DB", "Database location; defaults to data/panel.db"],
                ["LIVEKIT_URL / _API_KEY / _API_SECRET", "Realtime voice"],
                ["DEEPGRAM_API_KEY", "Speech-to-text"],
                ["CARTESIA_API_KEY", "Text-to-speech"],
                ["PANEL_AVATAR", "tavus | anam | simli | hedra | none. Off by default"],
            ],
            [62 * mm, PAGE_W - 2 * MARGIN - 62 * mm],
            mono_cols=(0,),
        ),
        Spacer(1, 3 * mm),
        callout(
            "ON AVATAR COST",
            "Talking-head avatars bill roughly $0.10 to $0.37 per active minute, so a "
            "30-minute interview costs $3 to $11 in avatar alone. PANEL_AVATAR defaults "
            "to none for that reason, and missing credentials are reported by name with "
            "what each one buys.",
        ),
        PageBreak(),
    ]
    return out


def part_fifteen():
    out = section("15", "Appendix", "")
    out += [
        Paragraph("Commit history", S["h2"]),
        data_table(
            [
                ["HASH", "WHAT LANDED"],
                ["17e72fc", "The engine: domain model, rubric library, plan compiler, conductor, "
                            "extractor, scorer, both reports, text transport, CLI"],
                ["94d0713", "HTTP API and the video-call web UI; reports refactored into one object "
                            "with several renderings"],
                ["bcb4b9a", "Realtime voice transport scaffolding behind a tested credential gate"],
                ["f70646a", "Append-only persistence, history, and trends scoped to one rubric"],
            ],
            [22 * mm, PAGE_W - 2 * MARGIN - 22 * mm],
            mono_cols=(0,),
        ),
        Spacer(1, 2 * mm),
        para("Across the last three commits: 31 files changed, 4,961 insertions.", "caption"),
        Paragraph("Glossary", S["h2"]),
        data_table(
            [
                ["TERM", "MEANING"],
                ["Anchor",
                 "One level of a rubric, described as observable behaviour in an answer "
                 "rather than as a trait"],
                ["BARS",
                 "Behaviourally-anchored rating scale — the rubric form that lifts "
                 "agreement with human experts from r≈0.20 to r≈0.63"],
                ["Critical point",
                 "A concrete thing a strong answer contains; drives both probing and scoring"],
                ["plan_hash",
                 "sha256 over the criteria, truncated to 16 characters. Two interviews "
                 "sharing one were assessed identically"],
                ["Probe",
                 "A follow-up question targeting the most valuable missing critical point"],
                ["Coverage",
                 "Fraction of planned competencies that actually gathered evidence"],
                ["Not observed",
                 "A competency the interview never reached. Excluded from the average; "
                 "not a low score"],
                ["Reasoner",
                 "The component making judgement calls. Two implementations: Claude-backed "
                 "and keyless heuristic"],
                ["Conductor",
                 "The interview state machine. Chooses which planned question and how deep "
                 "to probe — never what to assess"],
            ],
            [30 * mm, PAGE_W - 2 * MARGIN - 30 * mm],
            mono_cols=(0,),
        ),
        Spacer(1, 6 * mm),
        rule(),
        Paragraph(
            "Panel v0.1.0 &nbsp;·&nbsp; documentation generated 19 August 2026 &nbsp;·&nbsp; "
            "all figures measured from the repository at commit f70646a",
            S["caption"],
        ),
    ]
    return out


def main():
    global S
    register_fonts()
    S = build_styles()

    story = []
    story += cover()
    story += contents()
    story += part_one()
    story += part_two()
    story += part_three()
    story += part_four()
    story += part_five()
    story += part_six()
    story += part_seven()
    story += part_eight()
    story += part_nine()
    story += part_ten()
    story += part_eleven()
    story += part_twelve()
    story += part_thirteen()
    story += part_fourteen()
    story += part_fifteen()

    build_doc().build(story)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
