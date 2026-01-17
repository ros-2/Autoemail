"""Validation utilities for URLs and emails."""
import re
from urllib.parse import urlparse
from typing import Optional


# Job board domains to filter out when looking for company websites
JOB_BOARD_DOMAINS = [
    'indeed.com',
    'indeed.co.uk',
    'glassdoor.com',
    'glassdoor.co.uk',
    'linkedin.com',
    'reed.co.uk',
    's1jobs.com',
    'totaljobs.com',
    'monster.co.uk',
    'cv-library.co.uk',
    'jobsite.co.uk',
    'fish4.co.uk',
    'adzuna.co.uk',
    'jobisjob.co.uk',
    'careerjet.co.uk',
    'simplyhired.co.uk',
    'cwjobs.co.uk',
    'jobs.ac.uk',
    'gov.uk',
    'nhs.uk',
    'facebook.com',
    'twitter.com',
    'instagram.com',
    'youtube.com',
    'wikipedia.org',
]


def validate_url(url: str) -> bool:
    """
    Validate that a string is a properly formatted URL.

    Args:
        url: URL string to validate

    Returns:
        True if valid URL, False otherwise
    """
    if not url:
        return False

    try:
        result = urlparse(url)
        return all([result.scheme in ('http', 'https'), result.netloc])
    except Exception:
        return False


def validate_email(email: str) -> bool:
    """
    Validate that a string is a properly formatted email address.

    Args:
        email: Email string to validate

    Returns:
        True if valid email format, False otherwise
    """
    if not email:
        return False

    # Basic email regex pattern
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip()))


def is_job_board_url(url: str) -> bool:
    """
    Check if a URL belongs to a job board or social media site.

    Args:
        url: URL to check

    Returns:
        True if URL is from a job board/social media, False otherwise
    """
    if not url:
        return True

    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Remove 'www.' prefix if present
        if domain.startswith('www.'):
            domain = domain[4:]

        # Check against known job board domains
        for job_board in JOB_BOARD_DOMAINS:
            if job_board in domain:
                return True

        return False
    except Exception:
        return True


def extract_domain(url: str) -> Optional[str]:
    """
    Extract the domain from a URL.

    Args:
        url: URL to extract domain from

    Returns:
        Domain string or None if invalid
    """
    if not url:
        return None

    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Remove 'www.' prefix if present
        if domain.startswith('www.'):
            domain = domain[4:]

        return domain if domain else None
    except Exception:
        return None


def clean_company_name(name: str) -> str:
    """
    Clean a company name for searching.

    Args:
        name: Raw company name

    Returns:
        Cleaned company name
    """
    if not name:
        return ""

    # Remove common suffixes
    suffixes = [
        ' Ltd', ' Limited', ' PLC', ' plc', ' LLP',
        ' Inc', ' Corp', ' Corporation', ' Co.'
    ]

    cleaned = name.strip()
    for suffix in suffixes:
        if cleaned.endswith(suffix):
            cleaned = cleaned[:-len(suffix)]

    return cleaned.strip()
