"""Google Sheets logger for tracking outreach activity."""
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import gspread
import yaml
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

from .utils.logger import get_logger

# Load environment variables
load_dotenv()

logger = get_logger('outreach_bot.sheets_logger')

# Google Sheets API scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

# Column headers for the sheet
HEADERS = [
    'Date',
    'Company',
    'Job Title',
    'Location',
    'Method',
    'Status',
    'Contact',
    'Message',
    'Notes',
]


def load_config() -> dict:
    """Load configuration from YAML file."""
    config_path = Path(__file__).parent.parent.parent / 'config' / 'config.yaml'
    if config_path.exists():
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    return {}


def get_credentials() -> Optional[Credentials]:
    """
    Get Google Sheets API credentials.

    Returns:
        Credentials object or None if not configured
    """
    config = load_config()
    sheets_config = config.get('google_sheets', {})

    creds_path = os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH')
    if not creds_path:
        creds_path = sheets_config.get('service_account_path', 'credentials/google_sheets_service.json')

    # Resolve path relative to project root
    if not os.path.isabs(creds_path):
        project_root = Path(__file__).parent.parent.parent
        creds_path = project_root / creds_path

    if not Path(creds_path).exists():
        logger.error(f"Google Sheets credentials not found at: {creds_path}")
        return None

    try:
        credentials = Credentials.from_service_account_file(
            str(creds_path),
            scopes=SCOPES
        )
        return credentials
    except Exception as e:
        logger.error(f"Error loading Google Sheets credentials: {e}")
        return None


def get_worksheet() -> Optional[gspread.Worksheet]:
    """
    Get the Google Sheets worksheet.

    Returns:
        Worksheet object or None if connection fails
    """
    config = load_config()
    sheets_config = config.get('google_sheets', {})

    spreadsheet_id = sheets_config.get('spreadsheet_id')
    worksheet_name = sheets_config.get('worksheet_name', 'Sheet1')

    if not spreadsheet_id:
        logger.error("Google Sheets spreadsheet_id not configured")
        return None

    credentials = get_credentials()
    if not credentials:
        return None

    try:
        gc = gspread.authorize(credentials)
        spreadsheet = gc.open_by_key(spreadsheet_id)

        # Try to get existing worksheet or create it
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            logger.info(f"Creating worksheet: {worksheet_name}")
            worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=10)

        # Ensure headers exist
        ensure_headers(worksheet)

        return worksheet

    except gspread.exceptions.APIError as e:
        logger.error(f"Google Sheets API error: {e}")
        return None
    except Exception as e:
        logger.error(f"Error connecting to Google Sheets: {e}")
        return None


def ensure_headers(worksheet: gspread.Worksheet) -> None:
    """
    Ensure the worksheet has proper headers.

    Args:
        worksheet: gspread Worksheet object
    """
    try:
        # Get first row
        first_row = worksheet.row_values(1)

        # Check if headers match
        if first_row != HEADERS:
            # Update or add headers
            worksheet.update('A1:I1', [HEADERS])
            logger.info("Updated worksheet headers")

    except Exception as e:
        logger.error(f"Error ensuring headers: {e}")


def log_contact(
    job_info: Dict,
    method: str,
    status: str,
    contact: Optional[str] = None,
    message: Optional[str] = None,
    notes: Optional[str] = None
) -> bool:
    """
    Log a contact attempt to Google Sheets.

    Args:
        job_info: Dictionary with job information (company, title, location, etc.)
        method: Contact method used ('contact_form', 'email', 'manual_review')
        status: Status of the contact ('form_sent', 'email_drafted', 'manual_review', 'form_failed')
        contact: Contact information (form URL or email address)
        message: Message that was sent/drafted
        notes: Additional notes

    Returns:
        True if logged successfully, False otherwise
    """
    worksheet = get_worksheet()
    if not worksheet:
        logger.error("Could not connect to Google Sheets")
        return False

    try:
        # Prepare row data
        row = [
            datetime.now().strftime('%Y-%m-%d %H:%M'),
            job_info.get('company', 'Unknown'),
            job_info.get('title', 'Unknown'),
            job_info.get('location', 'Unknown'),
            method,
            status,
            contact or '',
            message or '',  # Full message, no truncation
            notes or '',
        ]

        # Append row to sheet
        worksheet.append_row(row, value_input_option='USER_ENTERED')

        # Color code the row based on status
        try:
            row_count = len(worksheet.get_all_values())

            # Define colors (RGB values 0-1)
            if status == 'form_sent':
                # Green for success
                bg_color = {'red': 0.85, 'green': 0.95, 'blue': 0.85}
            elif status == 'email_drafted':
                # Yellow/amber for needs action
                bg_color = {'red': 1.0, 'green': 0.95, 'blue': 0.8}
            elif status in ['manual_review', 'form_failed', 'no_website', 'no_contact']:
                # Red for needs attention
                bg_color = {'red': 0.95, 'green': 0.85, 'blue': 0.85}
            else:
                bg_color = None

            if bg_color:
                worksheet.format(f'A{row_count}:I{row_count}', {
                    'backgroundColor': bg_color
                })
        except Exception as e:
            logger.debug(f"Could not apply color formatting: {e}")

        logger.info(f"Logged contact: {job_info.get('company')} - {status}")
        return True

    except Exception as e:
        logger.error(f"Error logging to Google Sheets: {e}")
        return False


def check_already_contacted(company_name: str, days: int = 30) -> bool:
    """
    Check if a company has been contacted in the last N days.

    Args:
        company_name: Name of the company to check
        days: Number of days to look back (default: 30)

    Returns:
        True if company was contacted recently, False otherwise
    """
    config = load_config()
    dedup_config = config.get('deduplication', {})
    skip_days = dedup_config.get('skip_days', days)

    worksheet = get_worksheet()
    if not worksheet:
        return False

    try:
        # Get all data
        all_records = worksheet.get_all_values()

        if len(all_records) <= 1:  # Only headers or empty
            return False

        # Calculate cutoff date
        cutoff_date = datetime.now() - timedelta(days=skip_days)

        # Check each row (skip header)
        company_lower = company_name.lower().strip()
        # Also get first word for fuzzy matching
        company_first_word = company_lower.split()[0] if company_lower else ""

        for row in all_records[1:]:
            if len(row) < 2:
                continue

            # Parse date (column 0)
            try:
                row_date = datetime.strptime(row[0].split()[0], '%Y-%m-%d')
            except (ValueError, IndexError):
                continue

            # Check if within timeframe
            if row_date < cutoff_date:
                continue

            # Check company name (column 1) - flexible matching
            row_company = row[1].lower().strip()
            row_company_first_line = row_company.split('\n')[0].strip()

            # Match if: exact match, or first line matches, or company name is contained
            if (company_lower == row_company or
                company_lower == row_company_first_line or
                company_lower in row_company or
                row_company_first_line in company_lower):
                logger.debug(f"Company '{company_name}' was contacted on {row[0]}")
                return True

        return False

    except Exception as e:
        logger.error(f"Error checking contact history: {e}")
        return False


def get_manual_review_items(days: int = 7) -> List[Dict]:
    """
    Get items flagged for manual review in the last N days.

    Args:
        days: Number of days to look back

    Returns:
        List of job dictionaries needing manual review
    """
    worksheet = get_worksheet()
    if not worksheet:
        return []

    try:
        all_records = worksheet.get_all_values()

        if len(all_records) <= 1:
            return []

        cutoff_date = datetime.now() - timedelta(days=days)
        manual_items = []

        for row in all_records[1:]:
            if len(row) < 6:
                continue

            # Check status (column 5)
            if row[5] != 'manual_review':
                continue

            # Parse date
            try:
                row_date = datetime.strptime(row[0].split()[0], '%Y-%m-%d')
            except (ValueError, IndexError):
                continue

            if row_date < cutoff_date:
                continue

            manual_items.append({
                'date': row[0],
                'company': row[1],
                'title': row[2],
                'location': row[3],
                'notes': row[8] if len(row) > 8 else '',
            })

        return manual_items

    except Exception as e:
        logger.error(f"Error getting manual review items: {e}")
        return []


def get_stats(days: int = 30) -> Dict:
    """
    Get statistics for the last N days.

    Args:
        days: Number of days to look back

    Returns:
        Dictionary with stats
    """
    worksheet = get_worksheet()
    if not worksheet:
        return {}

    try:
        all_records = worksheet.get_all_values()

        if len(all_records) <= 1:
            return {
                'total': 0,
                'forms_sent': 0,
                'emails_drafted': 0,
                'manual_review': 0,
            }

        cutoff_date = datetime.now() - timedelta(days=days)

        stats = {
            'total': 0,
            'forms_sent': 0,
            'emails_drafted': 0,
            'manual_review': 0,
        }

        for row in all_records[1:]:
            if len(row) < 6:
                continue

            try:
                row_date = datetime.strptime(row[0].split()[0], '%Y-%m-%d')
            except (ValueError, IndexError):
                continue

            if row_date < cutoff_date:
                continue

            stats['total'] += 1
            status = row[5]

            if status == 'form_sent':
                stats['forms_sent'] += 1
            elif status == 'email_drafted':
                stats['emails_drafted'] += 1
            elif status == 'manual_review':
                stats['manual_review'] += 1

        return stats

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return {}


if __name__ == "__main__":
    # Test the sheets logger
    print("Testing Google Sheets connection...")

    worksheet = get_worksheet()
    if worksheet:
        print(f"Connected to worksheet: {worksheet.title}")

        # Get stats
        stats = get_stats(days=30)
        print(f"\nStats (last 30 days): {stats}")

        # Test check_already_contacted
        test_company = "Test Company Ltd"
        contacted = check_already_contacted(test_company)
        print(f"\n'{test_company}' contacted recently: {contacted}")
    else:
        print("Failed to connect to Google Sheets")
