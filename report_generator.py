"""Generate per-run reports and send email summaries.

Creates a PDF report in the run archive folder and emails
a text summary to configured recipients.
"""

import os
from datetime import datetime
from weasyprint import HTML
from google.oauth2 import service_account
from googleapiclient.discovery import build
import base64
from email.mime.text import MIMEText

# ── Configuration ──────────────────────────────────────────────────────────────
CREDENTIALS_FILE = "/Users/jasonhicks/Projects/test-settings-sync/credentials.json"
SENDER_EMAIL = "jhicks@soarcharteracademy.org"
RECIPIENTS = [
    "jhicks@soarcharteracademy.org",
    "twalker@soarcharteracademy.org",
    "jlourenco@soarcharteracademy.org",
]


def generate_report(run_dir, caaspp_result, elpac_result,
                    caaspp_verify=None, elpac_verify=None,
                    caaspp_changes=None, elpac_changes=None,
                    sheets_updated=False, seis_result=None,
                    caaspp_errors_removed=None, elpac_errors_removed=None,
                    caaspp_concatenations=None, elpac_concatenations=None):
    """Generate PDF report and return text summary.

    Args:
        run_dir: Path to the run archive folder
        caaspp_result: Upload result string ('uploaded', 'errors', etc.)
        elpac_result: Upload result string
        caaspp_verify: Verification results dict or None
        elpac_verify: Verification results dict or None

    Returns:
        Tuple of (pdf_path, text_summary)
    """
    run_timestamp = os.path.basename(run_dir)
    run_display = run_timestamp.replace("_", " ").replace("-", "/", 2).replace("/", "-", 2)

    # ── Build text summary ───────────────────────────────────────────────
    lines = []
    lines.append("TEST SETTINGS SYNC — RUN REPORT")
    lines.append(f"Run: {run_display}")
    lines.append("")

    # SEIS section
    if seis_result:
        lines.append("── SEIS ────────────────────────────────────")
        lines.append(f"  Import: {seis_result}")
        lines.append("")

    # CAASPP section
    lines.append("── CAASPP ──────────────────────────────────")
    lines.append(f"  Upload: {caaspp_result}")
    if caaspp_verify:
        lines.append(f"  Verified: {caaspp_verify['matched']}/{caaspp_verify['total']}")
        if caaspp_verify['mismatched'] > 0:
            lines.append(f"  Mismatched: {caaspp_verify['mismatched']}")
            for detail in caaspp_verify['details'][:5]:
                if detail['status'] == 'mismatch':
                    lines.append(f"    SSID {detail['ssid']}:")
                    if detail.get('missing'):
                        lines.append(f"      Missing from TOMS: {', '.join(detail['missing'])}")
                    if detail.get('extra'):
                        lines.append(f"      Extra in TOMS: {', '.join(detail['extra'])}")
        if caaspp_verify['missing'] > 0:
            lines.append(f"  Missing from report: {caaspp_verify['missing']}")
            for detail in caaspp_verify['details']:
                if detail['status'] == 'missing':
                    lines.append(f"    SSID {detail['ssid']}")
                elif detail['status'] == 'pass (via UI)':
                    lines.append(f"    SSID {detail['ssid']} — verified via UI ✓")
    if caaspp_concatenations:
        lines.append(f"  Concatenations resolved: {len(caaspp_concatenations)}")
        for c in caaspp_concatenations:
            lines.append(f"    SSID {c['ssid']}:")
            lines.append(f"      Erroneous code created by Aeries report generator: {c['raw']}")
            lines.append(f"      User-corrected code entered into TOMS: {c['chosen']}")
    lines.append("")

    # Google Sheets section
    lines.append("── GOOGLE SHEETS ───────────────────────────")
    lines.append(f"  Settings spreadsheet: {'✓ Updated' if sheets_updated else '✗ Not updated'}")
    lines.append("")

    # ELPAC section
    lines.append("── ELPAC ───────────────────────────────────")
    lines.append(f"  Upload: {elpac_result}")
    if elpac_verify:
        lines.append(f"  Verified: {elpac_verify['matched']}/{elpac_verify['total']}")
        if elpac_verify['mismatched'] > 0:
            lines.append(f"  Mismatched: {elpac_verify['mismatched']}")
            for detail in elpac_verify['details'][:5]:
                if detail['status'] == 'mismatch':
                    lines.append(f"    SSID {detail['ssid']}:")
                    if detail.get('missing'):
                        lines.append(f"      Missing from TOMS: {detail['missing']}")
                    if detail.get('extra'):
                        lines.append(f"      Extra in TOMS: {detail['extra']}")
        if elpac_verify['missing'] > 0:
            lines.append(f"  Missing from report: {elpac_verify['missing']}")
            for detail in elpac_verify['details']:
                if detail['status'] == 'missing':
                    lines.append(f"    SSID {detail['ssid']}")
                elif detail['status'] == 'pass (via UI)':
                    lines.append(f"    SSID {detail['ssid']} — verified via UI ✓")
    if elpac_concatenations:
        lines.append(f"  Concatenations resolved: {len(elpac_concatenations)}")
        for c in elpac_concatenations:
            lines.append(f"    SSID {c['ssid']}:")
            lines.append(f"      Erroneous code created by Aeries report generator: {c['raw']}")
            lines.append(f"      User-corrected code entered into TOMS: {c['chosen']}")
    lines.append("")

    # Changes section
    lines.append("── CHANGES ─────────────────────────────────")
    from change_tracker import format_changes_for_report
    caaspp_change_text = format_changes_for_report(caaspp_changes)
    elpac_change_text = format_changes_for_report(elpac_changes)
    lines.append(f"  CAASPP:")
    lines.append(caaspp_change_text or "  No previous run to compare.")
    lines.append(f"  ELPAC:")
    lines.append(elpac_change_text or "  No previous run to compare.")
    lines.append("")

    text_summary = "\n".join(lines)

    # ── Build HTML for PDF ───────────────────────────────────────────────
    def status_color(result):
        if result == 'uploaded':
            return '#2d7a3a'
        elif result in ('errors', 'unknown'):
            return '#c0392b'
        return '#666'

    def verify_html(verify, label):
        if not verify:
            return '<p style="color: #666;">No verification data.</p>'

        html = f'<div class="stat-row">'
        html += f'<div class="stat"><span class="num" style="color: #2d7a3a;">{verify["matched"]}</span><span class="label">Matched</span></div>'
        html += f'<div class="stat"><span class="num" style="color: #c0392b;">{verify["mismatched"]}</span><span class="label">Mismatched</span></div>'
        html += f'<div class="stat"><span class="num" style="color: #e67e22;">{verify["missing"]}</span><span class="label">Missing</span></div>'
        html += f'<div class="stat"><span class="num">{verify["total"]}</span><span class="label">Total</span></div>'
        html += '</div>'

        if verify['details']:
            html += '<table><thead><tr><th>SSID</th><th>Status</th><th>Details</th></tr></thead><tbody>'
            for detail in verify['details']:
                status = detail['status']
                color = '#2d7a3a' if 'pass' in status else '#c0392b'
                details_text = ''
                if detail.get('missing'):
                    details_text += f'Missing: {", ".join(detail["missing"])}'
                if detail.get('extra'):
                    if details_text:
                        details_text += '<br>'
                    details_text += f'Extra: {", ".join(detail["extra"])}'
                if detail.get('reason'):
                    details_text = detail['reason']
                html += f'<tr><td>{detail["ssid"]}</td><td style="color: {color}; font-weight: bold;">{status}</td><td>{details_text}</td></tr>'
            html += '</tbody></table>'

        return html

    def concat_html(concatenations):
        if not concatenations:
            return ''
        html = f'<h3 style="margin-top: 24px; font-size: 14px;">Concatenations resolved: {len(concatenations)}</h3>'
        html += '<table><thead><tr><th>SSID</th><th>Erroneous code created by Aeries report generator</th><th>User-corrected code entered into TOMS</th></tr></thead><tbody>'
        for c in concatenations:
            html += f'<tr><td>{c["ssid"]}</td><td style="font-family: monospace; font-size: 12px;">{c["raw"]}</td><td style="font-family: monospace; font-size: 12px; color: #2d7a3a;">{c["chosen"]}</td></tr>'
        html += '</tbody></table>'
        return html

    # Build SEIS HTML section
    seis_html = ""
    if seis_result:
        seis_color = '#2d7a3a' if seis_result.startswith('imported') or seis_result == 'no new settings' else '#c0392b'
        seis_bg = '#e6f4ea' if seis_result.startswith('imported') or seis_result == 'no new settings' else '#fce8e6'
        seis_html = f'<h2>SEIS Import <span class="result-badge" style="background: {seis_bg}; color: {seis_color};">{seis_result}</span></h2>'

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                max-width: 800px;
                margin: 40px auto;
                color: #333;
            }}
            h1 {{
                font-size: 24px;
                color: #1a1a1a;
                border-bottom: 2px solid #e0e0e0;
                padding-bottom: 12px;
            }}
            h2 {{
                font-size: 18px;
                margin-top: 32px;
                color: #1a1a1a;
            }}
            .run-info {{
                color: #666;
                font-size: 14px;
                margin-bottom: 24px;
            }}
            .result-badge {{
                display: inline-block;
                padding: 4px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }}
            .stat-row {{
                display: flex;
                gap: 24px;
                margin: 16px 0;
            }}
            .stat {{
                background: #f8f9fa;
                border-radius: 8px;
                padding: 12px 20px;
                text-align: center;
                min-width: 80px;
            }}
            .stat .num {{
                font-size: 28px;
                font-weight: bold;
                display: block;
            }}
            .stat .label {{
                font-size: 11px;
                color: #666;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 16px;
                font-size: 13px;
            }}
            th {{
                background: #f0f0f0;
                text-align: left;
                padding: 8px 12px;
                font-size: 12px;
                text-transform: uppercase;
                color: #555;
            }}
            td {{
                padding: 8px 12px;
                border-bottom: 1px solid #e0e0e0;
            }}
            .footer {{
                margin-top: 32px;
                font-size: 12px;
                color: #999;
            }}
        </style>
    </head>
    <body>
        <h1>Test Settings Sync Report</h1>
        <div class="run-info">Run: {run_display}</div>

        {seis_html}

        <h2>CAASPP <span class="result-badge" style="background: {'#e6f4ea' if caaspp_result == 'uploaded' else '#fce8e6'}; color: {status_color(caaspp_result)};">{caaspp_result}</span></h2>
        {verify_html(caaspp_verify, 'CAASPP')}
        {concat_html(caaspp_concatenations)}

        <h2>ELPAC <span class="result-badge" style="background: {'#e6f4ea' if elpac_result == 'uploaded' else '#fce8e6'}; color: {status_color(elpac_result)};">{elpac_result}</span></h2>
        {verify_html(elpac_verify, 'ELPAC')}
        {concat_html(elpac_concatenations)}

        <div class="footer">
            Generated by test-settings-sync · SOAR Charter Academy
        </div>
    </body>
    </html>
    """

    # ── Write PDF ────────────────────────────────────────────────────────
    pdf_path = os.path.join(run_dir, "sync_report.pdf")
    try:
        HTML(string=html_content).write_pdf(pdf_path)
        print(f"  PDF report saved: {pdf_path}")
    except Exception as e:
        print(f"  PDF generation failed: {e}")
        pdf_path = None

    return pdf_path, text_summary


def send_email(subject, body, recipients=None):
    """Send an email via Gmail API using service account.

    Args:
        subject: Email subject line
        body: Plain text email body
        recipients: List of email addresses (defaults to RECIPIENTS)
    """
    if recipients is None:
        recipients = RECIPIENTS

    try:
        credentials = service_account.Credentials.from_service_account_file(
            CREDENTIALS_FILE,
            scopes=['https://www.googleapis.com/auth/gmail.send'],
            subject=SENDER_EMAIL  # Impersonate this user
        )

        service = build('gmail', 'v1', credentials=credentials)

        message = MIMEText(body)
        message['to'] = ', '.join(recipients)
        message['from'] = SENDER_EMAIL
        message['subject'] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(
            userId='me',
            body={'raw': raw}
        ).execute()

        print(f"  Email sent to: {', '.join(recipients)}")
        return True

    except Exception as e:
        print(f"  Email failed: {e}")
        return False