"""
Covenant AI — AI Audit Report generator (SAMPLE / reference implementation)

This is a first-pass reference script, not production code. It shows one way to:
  1. take Prompt 1's JSON output + intake volume answers
  2. compute weekly-hours-saved and financial ROI deterministically in Python
     (per the "don't let the LLM do arithmetic" decision made during prompt design)
  3. render the result into a branded PDF with WeasyPrint

Wilson: the data below (INTAKE, RECOMMENDATIONS) stands in for what would actually
come from Supabase + the Claude API response. The TIME_SAVED_RUBRIC and pricing
figures are placeholders from our test rubric doc, not final numbers.

Brand colors below were sampled directly from Covenant_AI_Logo.png (see assets/).
If the real logo file changes, just swap assets/covenant_logo_full.png and
assets/covenant_logo_mark.png — everything else adapts automatically.
"""

import base64
import sys
from pathlib import Path
from weasyprint import HTML
from datetime import date

SCRIPT_DIR = Path(__file__).parent
# Logos live in assets/ if that folder exists, otherwise alongside this script.
ASSETS_DIR = SCRIPT_DIR / "assets" if (SCRIPT_DIR / "assets").is_dir() else SCRIPT_DIR

def b64_image(filename):
    data = (ASSETS_DIR / filename).read_bytes()
    return base64.b64encode(data).decode()

LOGO_FULL_B64 = b64_image("covenant_logo_full.png")
LOGO_MARK_B64 = b64_image("covenant_logo_mark.png")

# ---------------------------------------------------------------------------
# 1. INPUT DATA (stand-ins for real intake + Prompt 1 JSON output)
# ---------------------------------------------------------------------------

BUSINESS = {
    "name": "Highland Auto & Fleet Services",
    "industry": "Automotive Repair & Fleet Maintenance",
    "hourly_rate": 75,
    "weekly_leads": 25,       # intake Q1.4
    "weekly_appointments": 90,  # intake Q3.4
    "employees": 12,
    "named_pain": "Missed/no-show appointments and time spent tracking down backordered parts by phone",
    "named_pain_hours_estimate": 5,  # intake Q0.7, client's own estimate
}

# This is the fixed lookup table from the rubric doc — minutes saved per instance,
# keyed by the `time_saved_driver` tag Prompt 1 assigns. Never re-derive this from
# the LLM; keep it here so it's consistent and easy for Covenant AI to tune.
TIME_SAVED_RUBRIC = {
    "appointment_reminders": {"minutes_per": 3, "basis": "weekly_appointments"},
    "review_requests": {"minutes_per": 2, "basis": "weekly_appointments"},
    "lead_logging": {"minutes_per": 3, "basis": "weekly_leads"},
    "lead_response_speed": {"minutes_per": 5, "basis": "weekly_leads"},
    "followup_automation": {"minutes_per": 4, "basis": "weekly_leads"},
    "online_booking": {"minutes_per": 5, "basis": "weekly_appointments"},
    "task_management": {"minutes_per_employee_per_day": 8, "basis": "employees"},
    "content_drafting": {"minutes_per": 20, "basis": "posts_per_week"},
    "reporting_dashboard": {"flat_weekly_hours": 2},
}

# Stand-in for Prompt 1's JSON array (would come from the Claude API call)
RECOMMENDATIONS = [
    {
        "category": "Scheduling & Fulfillment",
        "current_state": "Appointments are booked by phone or text and tracked on an internal calendar, but no reminders go out to customers before their visit.",
        "recommendation": "Set up automated appointment reminder texts that go out a day before each scheduled service.",
        "why_it_matters": "Directly targets the top time drain you named — fewer no-shows means fewer wasted appointment slots and less time spent rebooking each day.",
        "suggested_tools": ["Podium", "Weave"],
        "estimated_monthly_cost": "$250\u2013300/mo",
        "time_saved_driver": "appointment_reminders",
        "setup_summary": "Enable in your existing Podium account \u2014 about 30 minutes",
        "effort_tier": "Low",
        "priority": "Quick Win",
    },
    {
        "category": "Customer Communication & Nurture",
        "current_state": "Reviews are requested verbally and inconsistently when a customer picks up their vehicle.",
        "recommendation": "Send an automatic text asking for a review a day or two after service is complete.",
        "why_it_matters": "Builds a steady stream of online reviews with no extra effort from staff, helping attract new customers over time.",
        "suggested_tools": ["Podium", "NiceJob"],
        "estimated_monthly_cost": "Included in Podium subscription above",
        "time_saved_driver": "review_requests",
        "setup_summary": "Turn on in the same Podium account \u2014 about 15 minutes",
        "effort_tier": "Low",
        "priority": "Quick Win",
    },
    {
        "category": "Lead Capture & Intake",
        "current_state": "New inquiries come in by phone or referral and aren't tracked anywhere formally \u2014 details rely on staff memory and paper folders.",
        "recommendation": "Start logging incoming inquiries in a simple, free CRM so nothing gets lost between the first call and getting the car in the shop.",
        "why_it_matters": "Protects against lost business when a lead isn't followed up on quickly, and builds a searchable history of past customers.",
        "suggested_tools": ["HubSpot Free CRM"],
        "estimated_monthly_cost": "$0/mo (free tier)",
        "time_saved_driver": "lead_logging",
        "setup_summary": "Free account setup + import existing customer list \u2014 about 2 hours, one-time",
        "effort_tier": "Low",
        "priority": "Quick Win",
    },
    {
        "category": "Internal Ops & Team Communication",
        "current_state": "Parts are reordered by calling suppliers individually when something runs out, and work orders are tracked on paper and a shop whiteboard.",
        "recommendation": "Move to a shop management platform that combines work order tracking with parts ordering, so the front desk and technicians can see stock and reorder status in one place.",
        "why_it_matters": "Addresses the other half of your named biggest time drain \u2014 less time spent tracking down parts by phone means faster turnaround per vehicle.",
        "suggested_tools": ["Shopmonkey", "Tekmetric"],
        "estimated_monthly_cost": "$300\u2013400/mo",
        "time_saved_driver": "task_management",
        "setup_summary": "Full onboarding + staff training, phased over 2\u20134 weeks",
        "effort_tier": "High",
        "priority": "Major Project",
    },
]

WEEKS_PER_MONTH = 4.33

# strftime's no-pad day flag differs by platform (%-d glibc, %#d Windows), so
# build the date string without it.
_today = date.today()
REPORT_DATE = f"{_today:%B} {_today.day}, {_today:%Y}"


# ---------------------------------------------------------------------------
# 2. DETERMINISTIC CALCULATIONS (this replaces "Prompt 2" entirely)
# ---------------------------------------------------------------------------

def compute_weekly_hours(rec, business):
    driver = rec.get("time_saved_driver")
    rule = TIME_SAVED_RUBRIC.get(driver)
    if not rule:
        return None  # qualitative-only recommendation, no number to show
    if "flat_weekly_hours" in rule:
        return rule["flat_weekly_hours"]
    if rule["basis"] == "employees":
        return round(business["employees"] * rule["minutes_per_employee_per_day"] * 5 / 60, 2)
    volume = business.get(rule["basis"], 0)
    return round(volume * rule["minutes_per"] / 60, 2)


for rec in RECOMMENDATIONS:
    rec["weekly_hours_saved"] = compute_weekly_hours(rec, BUSINESS)

quick_wins = [r for r in RECOMMENDATIONS if r["priority"] == "Quick Win"]
major_projects = [r for r in RECOMMENDATIONS if r["priority"] == "Major Project"]
fill_ins = [r for r in RECOMMENDATIONS if r["priority"] == "Fill-In"]

total_weekly_hours_quick_wins = round(
    sum(r["weekly_hours_saved"] or 0 for r in quick_wins), 2
)

def parse_low_end_cost(cost_str):
    if "Included" in cost_str:
        return 0
    digits = "".join(ch for ch in cost_str.split("\u2013")[0] if ch.isdigit())
    return int(digits) if digits else 0

total_monthly_tool_cost_quick_wins = sum(
    parse_low_end_cost(r["estimated_monthly_cost"]) for r in quick_wins
)

weekly_dollar_value = total_weekly_hours_quick_wins * BUSINESS["hourly_rate"]
monthly_dollar_value = round(weekly_dollar_value * WEEKS_PER_MONTH)
monthly_net_roi = monthly_dollar_value - total_monthly_tool_cost_quick_wins

# ---------------------------------------------------------------------------
# 3. HTML TEMPLATE — Covenant AI brand palette (sampled from logo)
# ---------------------------------------------------------------------------

CREAM = "#F6F6F4"       # page background, matched to logo file's backing tone
CARD = "#FFFFFF"        # card background
CARD_BORDER = "#E3DFD1"
GREEN = "#193A33"       # deep forest green — primary brand color
GOLD = "#C8A94F"        # gold — accent / highlight
INK = "#1D1D1B"         # near-black body text
MUTED = "#726F65"       # warm muted gray

def quick_win_rows():
    rows = ""
    for i, r in enumerate(quick_wins, start=1):
        rows += f"""
        <div class="qw-row">
          <div class="qw-num">{i:02d}</div>
          <div class="qw-title">{r['recommendation'].split('.')[0]}</div>
          <div class="qw-arrow">&#8594;</div>
          <div class="qw-tool">{' / '.join(r['suggested_tools'])}</div>
        </div>"""
    return rows

def solution_cards(recs):
    cards = ""
    for i, r in enumerate(recs, start=1):
        hrs = f"{r['weekly_hours_saved']} hrs/week" if r["weekly_hours_saved"] else "Qualitative benefit"
        cards += f"""
        <div class="solution-card">
          <div class="solution-num">{i:02d}</div>
          <div class="solution-title">{' / '.join(r['suggested_tools'])}</div>
          <div class="solution-desc">{r['recommendation']}</div>
          <div class="solution-stats">
            <div><span class="stat-label">COST</span><span class="stat-value">{r['estimated_monthly_cost']}</span></div>
            <div><span class="stat-label">SETUP</span><span class="stat-value">{r['setup_summary']}</span></div>
            <div><span class="stat-label">SAVES</span><span class="stat-value">{hrs}</span></div>
          </div>
        </div>"""
    return cards

def quick_win_plan_days():
    days = ""
    day_names = ["DAY ONE", "DAY TWO", "DAY THREE"]
    for i, r in enumerate(quick_wins, start=1):
        days += f"""
        <div class="plan-day">
          <div class="plan-num">{i}</div>
          <div class="plan-label">{day_names[i-1] if i-1 < len(day_names) else f'DAY {i}'}</div>
          <div class="plan-task">{r['recommendation']}</div>
          <div class="plan-tool">TOOL &middot; {' / '.join(r['suggested_tools'])}</div>
        </div>"""
    return days

def major_project_summaries():
    if not major_projects and not fill_ins:
        return "<p class='muted'>No additional projects identified this round \u2014 the quick wins above cover the highest-value opportunities right now.</p>"
    html = ""
    for r in major_projects:
        html += f"""
        <div class="next-item">
          <h3>{r['category']} <span class="tag major">Major Project</span></h3>
          <p>{r['current_state']}</p>
          <p><strong>Recommended next step:</strong> {r['recommendation']}</p>
        </div>"""
    for r in fill_ins:
        html += f"""
        <div class="next-item">
          <h3>{r['category']} <span class="tag fill">Fill-In</span></h3>
          <p>{r['current_state']}</p>
          <p><strong>Worth doing eventually:</strong> {r['recommendation']}</p>
        </div>"""
    return html

HTML_TEMPLATE = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{ size: letter; margin: 0; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    background: {CREAM};
    color: {INK};
  }}
  h1, h2, h3, .serif {{ font-family: 'Liberation Serif', Georgia, 'Times New Roman', serif; }}
  .page {{
    width: 8.5in;
    height: 11in;
    padding: 0.65in 0.7in;
    page-break-after: always;
    position: relative;
  }}
  .eyebrow {{
    font-family: 'Liberation Serif', Georgia, serif;
    color: {GOLD};
    letter-spacing: 2px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    margin-bottom: 8px;
  }}
  h1 {{ font-size: 40px; margin: 0 0 6px 0; font-weight: 700; color: {GREEN}; }}
  h2 {{ font-size: 25px; margin: 0 0 18px 0; font-weight: 700; color: {GREEN}; }}
  p {{ line-height: 1.55; font-size: 13.5px; color: {INK}; }}
  .muted {{ color: {MUTED}; }}
  .footer-brand {{
    position: absolute;
    bottom: 0.55in;
    left: 0.7in;
    right: 0.7in;
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 10px;
    color: {MUTED};
    letter-spacing: 1px;
    border-top: 1px solid {CARD_BORDER};
    padding-top: 10px;
  }}
  .footer-brand img {{ height: 14px; width: auto; opacity: 0.85; }}

  /* ---- TITLE PAGE ---- */
  .title-page {{
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: flex-start;
  }}
  .title-logo {{ width: 3.2in; margin-bottom: 0.55in; }}
  .title-page h1 {{ font-size: 50px; }}
  .title-business {{
    font-size: 25px;
    color: {GOLD};
    font-weight: 700;
    font-family: 'Liberation Serif', Georgia, serif;
    margin-top: 4px;
    margin-bottom: 36px;
  }}
  .title-meta {{ font-size: 13px; color: {MUTED}; line-height: 2; }}
  .title-meta strong {{ color: {INK}; }}
  .title-rule {{
    width: 60px; height: 3px; background: {GOLD}; margin: 24px 0;
  }}

  /* ---- EXEC SUMMARY ---- */
  .exec-block {{
    background: {CARD};
    border: 1px solid {CARD_BORDER};
    border-left: 4px solid {GREEN};
    padding: 18px 22px;
    margin-bottom: 16px;
    border-radius: 4px;
  }}
  .exec-block h3 {{
    margin: 0 0 8px 0; font-size: 12.5px; text-transform: uppercase;
    letter-spacing: 1px; color: {GREEN}; font-family: 'Liberation Serif', Georgia, serif;
  }}
  .exec-numbers {{ display: flex; gap: 16px; margin-top: 20px; }}
  .exec-number-card {{
    flex: 1; background: {CARD}; border: 1px solid {CARD_BORDER}; border-radius: 6px; padding: 16px;
    text-align: center;
  }}
  .exec-number-card .num {{ font-size: 28px; font-weight: 700; color: {GREEN}; font-family: 'Liberation Serif', Georgia, serif; }}
  .exec-number-card .label {{
    font-size: 10.5px; color: {MUTED}; text-transform: uppercase;
    letter-spacing: 0.5px; margin-top: 4px;
  }}

  /* ---- MATRIX ---- */
  .matrix-page {{ display: flex; flex-direction: column; }}
  .matrix-title {{
    font-size: 30px; font-weight: 700; letter-spacing: 1px; margin-bottom: 24px; color: {GREEN};
    font-family: 'Liberation Serif', Georgia, serif;
  }}
  .matrix-grid {{
    flex: 1; display: grid; grid-template-columns: 1fr 1fr;
    grid-template-rows: 1fr 1fr; gap: 14px; position: relative;
    margin-bottom: 0.5in;
  }}
  .matrix-cell {{
    border-radius: 8px; padding: 20px; background: {CARD}; border: 1px solid {CARD_BORDER};
    display: flex; flex-direction: column; justify-content: space-between;
  }}
  .matrix-cell.quick-win {{ background: {GOLD}; color: {GREEN}; border: none; }}
  .matrix-cell h4 {{ font-size: 16px; margin: 0 0 8px 0; font-weight: 700; font-family: 'Liberation Serif', Georgia, serif; color: {GREEN}; }}
  .matrix-cell.quick-win h4 {{ color: {GREEN}; }}
  .matrix-cell .items {{ font-size: 20px; font-weight: 700; letter-spacing: 4px; color: {GREEN}; font-family: 'Liberation Serif', Georgia, serif; }}
  .matrix-cell .note {{ font-size: 11px; color: {MUTED}; }}
  .matrix-cell.quick-win .note {{ color: {GREEN}; opacity: 0.85; }}

  /* ---- QUICK WINS LIST ---- */
  .qw-row {{
    display: flex; align-items: center; gap: 14px;
    border-bottom: 1px solid {CARD_BORDER}; padding: 12px 0;
  }}
  .qw-num {{ color: {GOLD}; font-weight: 700; font-size: 15px; width: 30px; font-family: 'Liberation Serif', Georgia, serif; }}
  .qw-title {{ flex: 2; font-size: 13.5px; }}
  .qw-arrow {{ color: {GOLD}; }}
  .qw-tool {{ flex: 1; color: {MUTED}; font-size: 12px; text-align: right; }}

  /* ---- SOLUTION CARDS ---- */
  .solutions-grid {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 18px;
  }}
  .solution-card {{
    background: {CARD}; border: 1px solid {CARD_BORDER}; border-radius: 8px; padding: 16px;
  }}
  .solution-num {{ color: {GOLD}; font-weight: 700; font-size: 13px; font-family: 'Liberation Serif', Georgia, serif; }}
  .solution-title {{ font-size: 14px; font-weight: 700; margin: 4px 0 6px 0; color: {GREEN}; }}
  .solution-desc {{ font-size: 11.5px; color: {INK}; margin-bottom: 10px; line-height: 1.4; }}
  .solution-stats div {{ display: flex; justify-content: space-between; font-size: 10.5px; padding: 2px 0; border-top: 1px solid {CARD_BORDER}; padding-top: 4px; margin-top: 4px; }}
  .solution-stats div:first-child {{ border-top: none; margin-top: 0; }}
  .stat-label {{ color: {MUTED}; letter-spacing: 1px; }}
  .stat-value {{ color: {INK}; text-align: right; max-width: 65%; font-weight: 600; }}

  /* ---- PLAN ---- */
  .plan-grid {{ display: flex; gap: 12px; margin-top: 20px; }}
  .plan-day {{
    flex: 1; background: {CARD}; border: 1px solid {CARD_BORDER}; border-radius: 8px; padding: 16px;
    display: flex; flex-direction: column; justify-content: space-between; min-height: 2.3in;
  }}
  .plan-num {{ font-size: 30px; color: {GOLD}; font-weight: 700; font-family: 'Liberation Serif', Georgia, serif; }}
  .plan-label {{ font-size: 11px; letter-spacing: 1px; color: {MUTED}; margin-bottom: 10px; }}
  .plan-task {{ font-size: 12px; color: {INK}; flex: 1; }}
  .plan-tool {{ font-size: 10px; color: {MUTED}; margin-top: 10px; letter-spacing: 0.5px; }}

  /* ---- WHAT'S NEXT ---- */
  .next-item {{ background: {CARD}; border: 1px solid {CARD_BORDER}; border-radius: 8px; padding: 16px 18px; margin-bottom: 14px; }}
  .next-item h3 {{ font-size: 15px; margin: 0 0 8px 0; color: {GREEN}; }}
  .tag {{ font-size: 9.5px; padding: 2px 8px; border-radius: 10px; letter-spacing: 0.5px; margin-left: 8px; font-family: 'Helvetica Neue', Arial, sans-serif; }}
  .tag.major {{ background: {GOLD}; color: {GREEN}; }}
  .tag.fill {{ background: {GREEN}; color: {CREAM}; }}

  /* ---- FINANCIAL IMPACT ---- */
  .fi-page {{ display: flex; flex-direction: column; }}
  .fi-grid {{ flex: 1; display: grid; grid-template-columns: 1.4fr 1fr; grid-template-rows: 1fr 1fr; gap: 14px; margin-bottom: 0.5in; }}
  .fi-hero {{
    grid-row: span 2; background: {GREEN}; color: {CREAM}; border-radius: 10px;
    padding: 26px; display: flex; flex-direction: column; justify-content: center;
  }}
  .fi-hero .fi-label {{ font-size: 12px; letter-spacing: 1px; text-transform: uppercase; color: {GOLD}; }}
  .fi-hero .fi-value {{ font-size: 54px; font-weight: 700; margin-top: 8px; font-family: 'Liberation Serif', Georgia, serif; color: {CREAM}; }}
  .fi-side {{ background: {CARD}; border: 1px solid {CARD_BORDER}; border-radius: 10px; padding: 20px; display: flex; flex-direction: column; justify-content: center; }}
  .fi-side .fi-label {{ font-size: 11px; letter-spacing: 1px; color: {MUTED}; text-transform: uppercase; }}
  .fi-side .fi-value {{ font-size: 26px; font-weight: 700; margin-top: 6px; color: {GREEN}; font-family: 'Liberation Serif', Georgia, serif; }}
  .fi-formula {{ font-size: 10.5px; color: {CREAM}; opacity: 0.7; margin-top: 16px; }}

  /* ---- NEXT STEPS ---- */
  .next-steps-page {{ display: flex; flex-direction: column; justify-content: center; }}
  .cta-box {{
    background: {GREEN}; color: {CREAM}; border-radius: 10px; padding: 26px 30px; margin-top: 24px;
  }}
  .cta-box h3 {{ color: {GOLD}; }}
  .cta-box p {{ color: {CREAM}; }}
</style>
</head>
<body>

<!-- PAGE 1: TITLE -->
<div class="page title-page">
  <img class="title-logo" src="data:image/png;base64,{LOGO_FULL_B64}">
  <div class="eyebrow">AI Adoption Audit</div>
  <h1>AI Audit Report</h1>
  <div class="title-business">{BUSINESS['name']}</div>
  <div class="title-rule"></div>
  <div class="title-meta">
    <div><strong>Date:</strong> {REPORT_DATE}</div>
    <div><strong>Industry:</strong> {BUSINESS['industry']}</div>
    <div><strong>Main Focus:</strong> Quick Wins &mdash; reducing no-shows &amp; streamlining parts ordering</div>
  </div>
</div>

<!-- PAGE 2: EXECUTIVE SUMMARY -->
<div class="page">
  <div class="eyebrow">Executive Summary</div>
  <h2>Where your time is really going</h2>
  <div class="exec-block">
    <h3>Your biggest pain point</h3>
    <p>{BUSINESS['named_pain']}. You estimated this costs you around <strong>{BUSINESS['named_pain_hours_estimate']} hours a week</strong> &mdash; and once we broke down the numbers below, the real opportunity turned out to be even larger.</p>
  </div>
  <div class="exec-block">
    <h3>Where to start</h3>
    <p>Three quick wins address this directly: automated appointment reminders and review requests through <strong>Podium</strong>, plus a free CRM (<strong>HubSpot</strong>) to stop losing track of new inquiries. All three can be running within a week, with no new hires and no custom software.</p>
  </div>
  <div class="exec-numbers">
    <div class="exec-number-card">
      <div class="num">~{total_weekly_hours_quick_wins:.1f}</div>
      <div class="label">Hours Reclaimed / Week</div>
    </div>
    <div class="exec-number-card">
      <div class="num">${monthly_dollar_value:,}</div>
      <div class="label">Estimated Value / Month</div>
    </div>
    <div class="exec-number-card">
      <div class="num">${total_monthly_tool_cost_quick_wins}</div>
      <div class="label">Tool Cost / Month</div>
    </div>
  </div>
  <p class="muted" style="margin-top:18px; font-size:10.5px;">Estimates are based on your reported volume of ~{BUSINESS['weekly_appointments']} appointments and ~{BUSINESS['weekly_leads']} new inquiries per week, at your estimated hourly rate of ${BUSINESS['hourly_rate']}. Actual results will vary.</p>
  <div class="footer-brand"><img src="data:image/png;base64,{LOGO_MARK_B64}"> COVENANT AI CONSULTING &middot; AI AUDIT REPORT</div>
</div>

<!-- PAGE 3: IMPACT-EFFORT MATRIX -->
<div class="page matrix-page">
  <div class="eyebrow">Prioritization</div>
  <div class="matrix-title">Impact&ndash;Effort Matrix</div>
  <div class="matrix-grid">
    <div class="matrix-cell quick-win">
      <h4>QUICK WINS</h4>
      <div class="items">{' '.join(str(i) for i in range(1, len(quick_wins)+1))}</div>
      <div class="note">High impact, low effort &mdash; this report focuses here.</div>
    </div>
    <div class="matrix-cell">
      <h4>MAJOR PROJECTS</h4>
      <div class="items">{' '.join(str(i) for i in range(len(quick_wins)+1, len(quick_wins)+len(major_projects)+1)) or '&mdash;'}</div>
      <div class="note">High impact, high effort &mdash; phase these in after the wins.</div>
    </div>
    <div class="matrix-cell">
      <h4>FILL-INS</h4>
      <div class="items">{'&mdash;' if not fill_ins else ' '.join(str(i) for i in range(1, len(fill_ins)+1))}</div>
      <div class="note">Low impact, low effort &mdash; do these when time allows.</div>
    </div>
    <div class="matrix-cell">
      <h4>IGNORE THESE</h4>
      <div class="items">&mdash;</div>
      <div class="note">Low impact, high effort &mdash; not worth the time right now.</div>
    </div>
  </div>
  <div class="footer-brand"><img src="data:image/png;base64,{LOGO_MARK_B64}"> COVENANT AI CONSULTING &middot; AI AUDIT REPORT</div>
</div>

<!-- PAGE 4: QUICK WINS WITH DETAILS -->
<div class="page">
  <div class="eyebrow">High Impact, Low Effort</div>
  <h2>Quick Wins</h2>
  {quick_win_rows()}
  <div class="solutions-grid">
    {solution_cards(quick_wins)}
  </div>
  <div class="footer-brand"><img src="data:image/png;base64,{LOGO_MARK_B64}"> COVENANT AI CONSULTING &middot; AI AUDIT REPORT</div>
</div>

<!-- PAGE 5: X-DAY QUICK WIN PLAN -->
<div class="page">
  <div class="eyebrow">Getting Started</div>
  <h2>Your {len(quick_wins)}-Day Quick Wins Plan</h2>
  <p class="muted">One quick win per day &mdash; small, sequential, no overwhelm.</p>
  <div class="plan-grid">
    {quick_win_plan_days()}
  </div>
  <div class="footer-brand"><img src="data:image/png;base64,{LOGO_MARK_B64}"> COVENANT AI CONSULTING &middot; AI AUDIT REPORT</div>
</div>

<!-- PAGE 6: WHAT TO DO NEXT -->
<div class="page">
  <div class="eyebrow">Looking Ahead</div>
  <h2>What to Do Next</h2>
  {major_project_summaries()}
  <div class="footer-brand"><img src="data:image/png;base64,{LOGO_MARK_B64}"> COVENANT AI CONSULTING &middot; AI AUDIT REPORT</div>
</div>

<!-- PAGE 7: FINANCIAL IMPACT -->
<div class="page fi-page">
  <div class="eyebrow">The Bottom Line</div>
  <h2>Financial Impact</h2>
  <div class="fi-grid">
    <div class="fi-hero">
      <div class="fi-label">Monthly Net ROI</div>
      <div class="fi-value">${monthly_net_roi:,}</div>
      <div class="fi-formula">Monthly Net ROI = (weekly time returned &times; hourly rate) &minus; total monthly tool cost</div>
    </div>
    <div class="fi-side">
      <div class="fi-label">Weekly Time Returned</div>
      <div class="fi-value">{total_weekly_hours_quick_wins:.1f} hrs</div>
    </div>
    <div class="fi-side">
      <div class="fi-label">Total Monthly Tool Cost</div>
      <div class="fi-value">${total_monthly_tool_cost_quick_wins}</div>
    </div>
  </div>
  <div class="footer-brand"><img src="data:image/png;base64,{LOGO_MARK_B64}"> COVENANT AI CONSULTING &middot; AI AUDIT REPORT</div>
</div>

<!-- PAGE 8: NEXT STEPS -->
<div class="page next-steps-page">
  <div class="eyebrow">Next Steps</div>
  <h2>Let's put this into action</h2>
  <p>This report is a starting point, not the finish line. Every recommendation here uses off-the-shelf tools &mdash; no custom development, no long-term lock-in &mdash; so you can move as fast or as gradually as makes sense for your shop.</p>
  <div class="cta-box">
    <h3 style="margin:0 0 8px 0;">Ready to talk it through?</h3>
    <p>Reach out to schedule a short review call. We'll walk through this report together, answer any questions, and help you get the first quick win running this week.</p>
  </div>
  <p style="margin-top:40px;">Thank you for choosing Covenant AI Consulting.</p>
  <div class="footer-brand"><img src="data:image/png;base64,{LOGO_MARK_B64}"> COVENANT AI CONSULTING &middot; AI AUDIT REPORT</div>
</div>

</body>
</html>
"""

if __name__ == "__main__":
    # Optional CLI override; otherwise write into output/ next to this script so
    # reruns don't clobber the checked-in sample PDF.
    if len(sys.argv) > 1:
        out_path = Path(sys.argv[1])
    else:
        out_path = SCRIPT_DIR / "output" / "Highland_Auto_AI_Audit_Report_SAMPLE.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=HTML_TEMPLATE).write_pdf(out_path)
    print(f"Wrote {out_path}")
    print(f"Quick win weekly hours: {total_weekly_hours_quick_wins}")
    print(f"Monthly $ value: {monthly_dollar_value}")
    print(f"Monthly tool cost: {total_monthly_tool_cost_quick_wins}")
    print(f"Monthly net ROI: {monthly_net_roi}")
