"""Contact finder to locate contact forms and email addresses on company websites."""
import random
import re
import time
from typing import Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

from .utils.logger import get_logger
from .utils.validators import validate_email, validate_url

logger = get_logger('outreach_bot.contact_finder')

# User agents for rotation
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
]

# Common contact page URL patterns
CONTACT_URL_PATTERNS = [
    '/contact',
    '/contact-us',
    '/contact_us',
    '/contactus',
    '/get-in-touch',
    '/enquiries',
    '/enquiry',
    '/reach-us',
    '/connect',
    '/about/contact',
    '/about-us/contact',
]

# Email patterns to look for (prioritized)
EMAIL_PRIORITIES = [
    'info@',
    'enquiries@',
    'enquiry@',
    'hello@',
    'contact@',
    'admin@',
    'office@',
    'general@',
    'sales@',
]


def create_driver() -> webdriver.Chrome:
    """Create a headless Chrome driver for form detection."""
    options = Options()
    options.add_argument(f'user-agent={random.choice(USER_AGENTS)}')
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')

    # Disable images for faster loading
    prefs = {'profile.managed_default_content_settings.images': 2}
    options.add_experimental_option('prefs', prefs)

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def get_page_content(url: str, timeout: int = 10) -> Optional[str]:
    """
    Fetch page content using requests.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds

    Returns:
        HTML content or None
    """
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-GB,en;q=0.5',
    }

    try:
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if response.status_code == 200:
            return response.text
    except requests.RequestException as e:
        logger.debug(f"Error fetching {url}: {e}")

    return None


def find_contact_page_links(base_url: str, html_content: str) -> list:
    """
    Find links to potential contact pages in the HTML.

    Args:
        base_url: Base URL for resolving relative links
        html_content: HTML content to search

    Returns:
        List of potential contact page URLs
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    contact_links = []

    # Find all links
    for link in soup.find_all('a', href=True):
        href = link.get('href', '').lower()
        text = link.get_text().lower()

        # Check if link text or href suggests contact page
        contact_indicators = ['contact', 'enquir', 'get in touch', 'reach us', 'connect']

        if any(indicator in href or indicator in text for indicator in contact_indicators):
            full_url = urljoin(base_url, link['href'])
            if validate_url(full_url) and full_url not in contact_links:
                contact_links.append(full_url)

    return contact_links


def has_contact_form(url: str, driver: Optional[webdriver.Chrome] = None) -> bool:
    """
    Check if a URL contains a contact form using Selenium.

    Args:
        url: URL to check
        driver: Optional existing WebDriver instance

    Returns:
        True if contact form found
    """
    close_driver = False
    if driver is None:
        driver = create_driver()
        close_driver = True

    try:
        driver.get(url)
        time.sleep(2)  # Wait for page load

        # Look for form elements
        form_indicators = [
            'form[action*="contact"]',
            'form[action*="enquir"]',
            'form[id*="contact"]',
            'form[class*="contact"]',
            'form[name*="contact"]',
            '.contact-form',
            '#contact-form',
            '[class*="contact-form"]',
            '[class*="enquiry-form"]',
        ]

        for selector in form_indicators:
            forms = driver.find_elements(By.CSS_SELECTOR, selector)
            if forms:
                logger.debug(f"Found contact form with selector: {selector}")
                return True

        # Also check for forms with message/enquiry fields
        forms = driver.find_elements(By.TAG_NAME, 'form')
        for form in forms:
            # Check if form has message-like textarea or input
            message_fields = form.find_elements(By.CSS_SELECTOR,
                'textarea, input[name*="message"], input[name*="enquir"], input[type="email"]'
            )
            if len(message_fields) >= 2:  # At least email + message
                return True

        return False

    except (TimeoutException, WebDriverException) as e:
        logger.debug(f"Error checking form on {url}: {e}")
        return False

    finally:
        if close_driver:
            try:
                driver.quit()
            except Exception:
                pass


def find_contact_form(website_url: str) -> Optional[str]:
    """
    Find a contact form on the company website.

    Args:
        website_url: Company website URL

    Returns:
        URL of the contact form page, or None if not found
    """
    if not website_url:
        return None

    logger.info(f"Looking for contact form on: {website_url}")

    # Ensure URL has scheme
    if not website_url.startswith('http'):
        website_url = f'https://{website_url}'

    parsed = urlparse(website_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    driver = None
    try:
        driver = create_driver()

        # First, check common contact URL patterns
        for pattern in CONTACT_URL_PATTERNS:
            test_url = f"{base_url}{pattern}"
            logger.debug(f"Checking: {test_url}")

            try:
                driver.get(test_url)
                time.sleep(1)

                # Check if page exists (not 404)
                if "404" in driver.title.lower() or "not found" in driver.title.lower():
                    continue

                # Check for form
                if has_contact_form(test_url, driver):
                    logger.info(f"Found contact form at: {test_url}")
                    return test_url

            except WebDriverException:
                continue

        # If no standard URL works, check homepage for contact links
        html = get_page_content(website_url)
        if html:
            contact_links = find_contact_page_links(website_url, html)

            for link in contact_links[:5]:  # Check first 5 potential links
                if has_contact_form(link, driver):
                    logger.info(f"Found contact form at: {link}")
                    return link

        logger.info(f"No contact form found on: {website_url}")
        return None

    except Exception as e:
        logger.error(f"Error finding contact form: {e}")
        return None

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def extract_emails_from_text(text: str) -> list:
    """
    Extract email addresses from text.

    Args:
        text: Text to search

    Returns:
        List of email addresses found
    """
    # Email regex pattern
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    emails = re.findall(pattern, text)

    # Filter and validate
    valid_emails = []
    for email in emails:
        email = email.lower().strip()

        # Skip obvious non-emails
        skip_patterns = [
            'example.com',
            'yourdomain',
            'domain.com',
            'email.com',
            '@sentry',
            'wixpress',
            '.png',
            '.jpg',
            '.gif',
        ]

        if any(skip in email for skip in skip_patterns):
            continue

        if validate_email(email) and email not in valid_emails:
            valid_emails.append(email)

    return valid_emails


def prioritize_emails(emails: list) -> list:
    """
    Sort emails by priority (info@, enquiries@, etc. first).

    Args:
        emails: List of email addresses

    Returns:
        Sorted list with priority emails first
    """
    def get_priority(email: str) -> int:
        email_lower = email.lower()
        for i, prefix in enumerate(EMAIL_PRIORITIES):
            if email_lower.startswith(prefix):
                return i
        return len(EMAIL_PRIORITIES)  # Unknown prefix goes last

    return sorted(emails, key=get_priority)


def find_email(website_url: str) -> Optional[str]:
    """
    Find an email address on the company website.

    Args:
        website_url: Company website URL

    Returns:
        Best email address found, or None
    """
    if not website_url:
        return None

    logger.info(f"Looking for email on: {website_url}")

    # Ensure URL has scheme
    if not website_url.startswith('http'):
        website_url = f'https://{website_url}'

    parsed = urlparse(website_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    all_emails = set()

    # Check homepage
    html = get_page_content(website_url)
    if html:
        emails = extract_emails_from_text(html)
        all_emails.update(emails)

    # Check common contact pages
    contact_urls = [f"{base_url}{pattern}" for pattern in CONTACT_URL_PATTERNS[:5]]

    for url in contact_urls:
        html = get_page_content(url)
        if html:
            emails = extract_emails_from_text(html)
            all_emails.update(emails)

            # If we found some emails, don't need to check more pages
            if len(all_emails) >= 3:
                break

        time.sleep(random.uniform(0.5, 1))

    if all_emails:
        # Prioritize and return best email
        sorted_emails = prioritize_emails(list(all_emails))
        best_email = sorted_emails[0]
        logger.info(f"Found email: {best_email}")
        return best_email

    logger.info(f"No email found on: {website_url}")
    return None


def find_contact_method(website_url: str) -> Tuple[Optional[str], Optional[str], str]:
    """
    Find the best contact method for a company website.

    Priority: Contact form > Email > None

    Args:
        website_url: Company website URL

    Returns:
        Tuple of (contact_form_url, email_address, method_type)
        method_type is one of: 'contact_form', 'email', 'none'
    """
    # Try to find contact form first (preferred)
    form_url = find_contact_form(website_url)
    if form_url:
        return (form_url, None, 'contact_form')

    # Fallback to email
    email = find_email(website_url)
    if email:
        return (None, email, 'email')

    return (None, None, 'none')


if __name__ == "__main__":
    # Test the contact finder
    test_urls = [
        "https://www.lochross.com",
        "https://www.blythswoodcare.org",
    ]

    for url in test_urls:
        print(f"\nTesting: {url}")
        form_url, email, method = find_contact_method(url)
        print(f"  Method: {method}")
        if form_url:
            print(f"  Form URL: {form_url}")
        if email:
            print(f"  Email: {email}")
