"""HTML audit report generator.

Produces a clean, professional single-file HTML report that can be
sent to prospects as a cold outreach attachment.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from jinja2 import Template

from models import Severity, SiteAudit

REPORT_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Website Audit: {{ audit.url }}</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1a1a2e; background: #f8f9fa; line-height: 1.6; }
  .container { max-width: 800px; margin: 0 auto; padding: 20px; }
  .header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 40px; border-radius: 12px; margin-bottom: 24px; }
  .header h1 { font-size: 24px; margin-bottom: 8px; }
  .header .url { opacity: 0.8; font-size: 14px; word-break: break-all; }
  .score-card { display: flex; gap: 20px; margin-bottom: 24px; }
  .score-box { flex: 1; background: white; border-radius: 12px; padding: 24px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
  .score-number { font-size: 48px; font-weight: 800; }
  .score-number.bad { color: #e74c3c; }
  .score-number.ok { color: #f39c12; }
  .score-number.good { color: #27ae60; }
  .score-label { font-size: 13px; color: #666; margin-top: 4px; }
  .waste-box { background: #fff3cd; border-left: 4px solid #f39c12; }
  .waste-number { font-size: 20px; font-weight: 700; color: #856404; }
  .section { background: white; border-radius: 12px; padding: 24px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
  .section h2 { font-size: 18px; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid #f0f0f0; }
  .leak { padding: 16px; margin-bottom: 12px; border-radius: 8px; border-left: 4px solid #ccc; }
  .leak.critical { border-left-color: #e74c3c; background: #fdf0ef; }
  .leak.high { border-left-color: #e67e22; background: #fef5ec; }
  .leak.medium { border-left-color: #f1c40f; background: #fefcf0; }
  .leak.low { border-left-color: #3498db; background: #f0f7fd; }
  .leak-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
  .leak-type { font-weight: 700; font-size: 14px; }
  .badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; text-transform: uppercase; color: white; }
  .badge.critical { background: #e74c3c; }
  .badge.high { background: #e67e22; }
  .badge.medium { background: #f1c40f; color: #333; }
  .badge.low { background: #3498db; }
  .leak-desc { font-size: 14px; color: #333; margin-bottom: 8px; }
  .leak-rec { font-size: 13px; color: #155724; background: #d4edda; padding: 8px 12px; border-radius: 4px; }
  .leak-rec strong { color: #0b5a1e; }
  .leak-impact { font-size: 12px; color: #856404; margin-top: 6px; }
  .leak-page { font-size: 12px; color: #666; margin-top: 4px; word-break: break-all; }
  .summary-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
  .stat { text-align: center; padding: 12px; background: #f8f9fa; border-radius: 8px; }
  .stat-num { font-size: 24px; font-weight: 700; }
  .stat-num.critical { color: #e74c3c; }
  .stat-num.high { color: #e67e22; }
  .stat-num.medium { color: #f1c40f; }
  .stat-num.low { color: #3498db; }
  .stat-label { font-size: 11px; color: #666; text-transform: uppercase; }
  .footer { text-align: center; padding: 24px; color: #999; font-size: 12px; }
  .page-summary { font-size: 13px; color: #666; margin-bottom: 16px; }
  .cta-section { background: linear-gradient(135deg, #27ae60 0%, #2ecc71 100%); color: white; padding: 32px; border-radius: 12px; text-align: center; margin-bottom: 16px; }
  .cta-section h2 { color: white; border: none; padding: 0; margin-bottom: 12px; }
  .cta-section p { font-size: 16px; opacity: 0.95; }
</style>
</head>
<body>
<div class="container">

<div class="header">
  <h1>Website Revenue Leak Audit</h1>
  <div class="url">{{ audit.url }}</div>
  {% if audit.business_name %}
  <div class="url" style="margin-top: 4px; font-weight: 600;">{{ audit.business_name }}</div>
  {% endif %}
</div>

<div class="score-card">
  <div class="score-box">
    <div class="score-number {{ 'bad' if audit.overall_score < 40 else ('ok' if audit.overall_score < 70 else 'good') }}">{{ audit.overall_score }}</div>
    <div class="score-label">Health Score (out of 100)</div>
  </div>
  <div class="score-box waste-box">
    <div class="waste-number">{{ audit.estimated_monthly_waste }}</div>
    <div class="score-label">Estimated Monthly Revenue Leak</div>
  </div>
</div>

<div class="section">
  <h2>Issues Found</h2>
  <div class="summary-stats">
    <div class="stat">
      <div class="stat-num critical">{{ counts.critical }}</div>
      <div class="stat-label">Critical</div>
    </div>
    <div class="stat">
      <div class="stat-num high">{{ counts.high }}</div>
      <div class="stat-label">High</div>
    </div>
    <div class="stat">
      <div class="stat-num medium">{{ counts.medium }}</div>
      <div class="stat-label">Medium</div>
    </div>
    <div class="stat">
      <div class="stat-num low">{{ counts.low }}</div>
      <div class="stat-label">Low</div>
    </div>
  </div>
  <div class="page-summary">
    Scanned {{ audit.pages_scanned | length }} page(s) &middot;
    Generated {{ generated_at }}
  </div>
</div>

{% for leak in audit.leaks %}
<div class="section">
  <div class="leak {{ leak.severity.value }}">
    <div class="leak-header">
      <span class="leak-type">{{ leak.leak_type.value | replace('_', ' ') | title }}</span>
      <span class="badge {{ leak.severity.value }}">{{ leak.severity.value }}</span>
    </div>
    <div class="leak-desc">{{ leak.description }}</div>
    <div class="leak-rec"><strong>Fix:</strong> {{ leak.recommendation }}</div>
    {% if leak.estimated_monthly_impact %}
    <div class="leak-impact">💰 Impact: {{ leak.estimated_monthly_impact }}</div>
    {% endif %}
    <div class="leak-page">Page: {{ leak.page_url }}</div>
  </div>
</div>
{% endfor %}

{% if audit.leaks %}
<div class="cta-section">
  <h2>We Can Fix This</h2>
  <p>We identified {{ audit.leaks | length }} issues costing you {{ audit.estimated_monthly_waste }}.<br>
  We can fix the critical issues within 48 hours. Want to talk?</p>
</div>
{% endif %}

<div class="footer">
  Generated by LeakEngine &middot; {{ generated_at }}
</div>

</div>
</body>
</html>
""")


def generate_html_report(audit: SiteAudit) -> str:
    """Generate a standalone HTML audit report."""
    counts = {
        "critical": sum(1 for l in audit.leaks if l.severity == Severity.CRITICAL),
        "high": sum(1 for l in audit.leaks if l.severity == Severity.HIGH),
        "medium": sum(1 for l in audit.leaks if l.severity == Severity.MEDIUM),
        "low": sum(1 for l in audit.leaks if l.severity == Severity.LOW),
    }

    generated_at = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")

    return REPORT_TEMPLATE.render(
        audit=audit,
        counts=counts,
        generated_at=generated_at,
    )


def save_report(audit: SiteAudit, output_path: str = "audit.html") -> str:
    """Generate and save an HTML report. Returns the output path."""
    html = generate_html_report(audit)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)
    return output_path
