"""Email sending utilities for outreach and daily summary reports."""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from dotenv import load_dotenv

from .logger import get_logger

# Load environment variables
load_dotenv()

logger = get_logger('outreach_bot.email')


def send_outreach_email(to_email: str, subject: str, message: str) -> bool:
    """
    Send an outreach email to a prospective client.

    Args:
        to_email: Recipient email address
        subject: Email subject line
        message: Email body content

    Returns:
        True if email sent successfully, False otherwise
    """
    config = load_config()
    email_config = config.get('email', {})

    smtp_server = email_config.get('smtp_server', 'smtp.zoho.com')
    smtp_port = email_config.get('smtp_port', 587)
    from_email = email_config.get('from_email', 'philip@lochross.com')
    from_name = email_config.get('from_name', 'Philip Ross')

    password = os.getenv('EMAIL_APP_PASSWORD')

    if not password:
        logger.error("EMAIL_APP_PASSWORD not found in environment variables")
        return False

    # Create message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"{from_name} <{from_email}>"
    msg['To'] = to_email

    # Add greeting to message
    full_message = f"Hello,\n\n{message}"

    # Plain text version
    text_part = MIMEText(full_message, 'plain')
    msg.attach(text_part)

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(from_email, password)
            server.send_message(msg)

        logger.info(f"Outreach email sent to {to_email}")
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed. Check email credentials.")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error sending outreach email: {e}")
        return False
    except Exception as e:
        logger.error(f"Error sending outreach email to {to_email}: {e}")
        return False


def load_config() -> dict:
    """Load configuration from YAML file."""
    config_path = Path(__file__).parent.parent.parent.parent.parent / 'config' / 'config.yaml'
    if config_path.exists():
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    return {}


def send_summary_email(results: Dict) -> bool:
    """
    Send daily summary email to Philip.

    Args:
        results: Dictionary containing:
            - forms_sent: int
            - emails_drafted: int
            - manual_review: List of job dicts needing attention
            - errors: List of error messages (optional)

    Returns:
        True if email sent successfully, False otherwise
    """
    config = load_config()
    email_config = config.get('email', {})

    smtp_server = email_config.get('smtp_server', 'smtp.zoho.com')
    smtp_port = email_config.get('smtp_port', 587)
    from_email = email_config.get('from_email', 'philip@lochross.com')
    from_name = email_config.get('from_name', 'Philip Ross')
    recipient = email_config.get('summary_recipient', 'philip@lochross.com')

    password = os.getenv('EMAIL_APP_PASSWORD')

    if not password:
        logger.error("EMAIL_APP_PASSWORD not found in environment variables")
        return False

    # Build email content
    subject = f"Lochross Outreach Summary - {datetime.now().strftime('%d %B %Y')}"

    body = build_summary_body(results)

    # Create message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"{from_name} <{from_email}>"
    msg['To'] = recipient

    # Plain text version
    text_part = MIMEText(body, 'plain')
    msg.attach(text_part)

    # HTML version
    html_body = build_summary_html(results)
    html_part = MIMEText(html_body, 'html')
    msg.attach(html_part)

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(from_email, password)
            server.send_message(msg)

        logger.info(f"Summary email sent to {recipient}")
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed. Check email credentials.")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error sending email: {e}")
        return False
    except Exception as e:
        logger.error(f"Error sending summary email: {e}")
        return False


def build_summary_body(results: Dict) -> str:
    """Build plain text email body."""
    forms_sent = results.get('forms_sent', 0)
    emails_sent = results.get('emails_sent', 0)
    emails_drafted = results.get('emails_drafted', 0)
    manual_review = results.get('manual_review', [])
    errors = results.get('errors', [])

    total_processed = forms_sent + emails_sent + emails_drafted + len(manual_review)

    lines = [
        "LOCHROSS OUTREACH - DAILY SUMMARY",
        "=" * 40,
        "",
        f"Date: {datetime.now().strftime('%A, %d %B %Y')}",
        "",
        "RESULTS:",
        f"  - Contact forms submitted: {forms_sent}",
        f"  - Emails sent: {emails_sent}",
        f"  - Emails drafted (needs manual send): {emails_drafted}",
        f"  - Needs manual review: {len(manual_review)}",
        f"  - Total processed: {total_processed}",
        "",
    ]

    if emails_drafted > 0:
        lines.extend([
            "ACTION REQUIRED:",
            "  Check Google Sheets for drafted emails to send manually.",
            "",
        ])

    if manual_review:
        lines.extend([
            "MANUAL REVIEW NEEDED:",
            "-" * 30,
        ])
        for job in manual_review:
            lines.append(f"  - {job.get('company', 'Unknown')} ({job.get('location', 'Unknown')})")
            lines.append(f"    Job: {job.get('title', 'Unknown')}")
            lines.append(f"    Reason: No contact method found")
            lines.append("")

    if errors:
        lines.extend([
            "ERRORS:",
            "-" * 30,
        ])
        for error in errors[:5]:  # Limit to 5 errors
            lines.append(f"  - {error}")
        lines.append("")

    lines.extend([
        "-" * 40,
        "View full details in Google Sheets:",
        "https://docs.google.com/spreadsheets/d/1C-nfnPB0KguC64SLn7FDkAamindbST0fbMF7JN2OZuY",
        "",
        "This is an automated message from Lochross Outreach Bot.",
    ])

    return "\n".join(lines)


def build_summary_html(results: Dict) -> str:
    """Build HTML email body."""
    forms_sent = results.get('forms_sent', 0)
    emails_sent = results.get('emails_sent', 0)
    emails_drafted = results.get('emails_drafted', 0)
    manual_review = results.get('manual_review', [])
    errors = results.get('errors', [])

    total_processed = forms_sent + emails_sent + emails_drafted + len(manual_review)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .header {{ background: #2c3e50; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; }}
            .stats {{ display: flex; flex-wrap: wrap; gap: 15px; margin: 20px 0; }}
            .stat-box {{ background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center; flex: 1; min-width: 120px; }}
            .stat-number {{ font-size: 32px; font-weight: bold; color: #2c3e50; }}
            .stat-label {{ color: #666; font-size: 14px; }}
            .success {{ color: #27ae60; }}
            .warning {{ color: #f39c12; }}
            .action {{ background: #fff3cd; padding: 15px; border-radius: 8px; margin: 20px 0; }}
            .manual-review {{ background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0; }}
            .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 30px; }}
            a {{ color: #3498db; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Lochross Outreach Summary</h1>
            <p>{datetime.now().strftime('%A, %d %B %Y')}</p>
        </div>
        <div class="content">
            <div class="stats">
                <div class="stat-box">
                    <div class="stat-number success">{forms_sent}</div>
                    <div class="stat-label">Forms Submitted</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number success">{emails_sent}</div>
                    <div class="stat-label">Emails Sent</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number warning">{emails_drafted}</div>
                    <div class="stat-label">Emails to Send</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{len(manual_review)}</div>
                    <div class="stat-label">Manual Review</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{total_processed}</div>
                    <div class="stat-label">Total Processed</div>
                </div>
            </div>
    """

    if emails_drafted > 0:
        html += """
            <div class="action">
                <strong>Action Required:</strong> You have drafted emails ready to send.
                Check the Google Sheet for email addresses and message content.
            </div>
        """

    if manual_review:
        html += "<h3>Manual Review Needed</h3>"
        for job in manual_review:
            html += f"""
            <div class="manual-review">
                <strong>{job.get('company', 'Unknown')}</strong> - {job.get('location', 'Unknown')}<br>
                <small>{job.get('title', 'Unknown')}</small><br>
                <small style="color: #e74c3c;">No contact method found</small>
            </div>
            """

    if errors:
        html += "<h3>Errors</h3><ul>"
        for error in errors[:5]:
            html += f"<li>{error}</li>"
        html += "</ul>"

    html += f"""
            <div class="footer">
                <p><a href="https://docs.google.com/spreadsheets/d/1C-nfnPB0KguC64SLn7FDkAamindbST0fbMF7JN2OZuY">View full details in Google Sheets</a></p>
                <p>Automated message from Lochross Outreach Bot</p>
            </div>
        </div>
    </body>
    </html>
    """

    return html
