"""Website finder using Selenium to find company websites."""
import random
import re
import time
from typing import Optional
from urllib.parse import quote_plus, urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

from .utils.logger import get_logger
from .utils.validators import is_job_board_url, validate_url, clean_company_name

logger = get_logger('outreach_bot.website_finder')

# User agents for rotation
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
]

# Shared driver instance
_driver = None


def get_driver() -> webdriver.Chrome:
    """Get or create a shared Chrome driver."""
    global _driver
    if _driver is None:
        options = Options()
        options.add_argument(f'user-agent={random.choice(USER_AGENTS)}')
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-blink-features=AutomationControlled')
        prefs = {'profile.managed_default_content_settings.images': 2}
        options.add_experimental_option('prefs', prefs)

        service = Service(ChromeDriverManager().install())
        _driver = webdriver.Chrome(service=service, options=options)
    return _driver


def close_driver():
    """Close the shared driver."""
    global _driver
    if _driver:
        try:
            _driver.quit()
        except Exception:
            pass
        _driver = None


def search_google(query: str, num_results: int = 5) -> list:
    """
    Perform a Google search using Selenium and return result URLs.

    Args:
        query: Search query string
        num_results: Number of results to return

    Returns:
        List of URLs from search results
    """
    encoded_query = quote_plus(query)
    url = f"https://www.google.com/search?q={encoded_query}&num={num_results + 5}&hl=en"

    try:
        driver = get_driver()
        driver.get(url)
        time.sleep(random.uniform(2, 4))

        urls = []

        # Find search result links
        selectors = [
            'div.g a[href^="http"]',
            'div.yuRUbf a',
            'a[data-ved][href^="http"]',
        ]

        for selector in selectors:
            try:
                links = driver.find_elements(By.CSS_SELECTOR, selector)
                for link in links:
                    href = link.get_attribute('href')
                    if href and href.startswith('http') and 'google' not in href:
                        if validate_url(href) and href not in urls:
                            urls.append(href)
                        if len(urls) >= num_results:
                            break
            except Exception:
                continue
            if len(urls) >= num_results:
                break

        return urls[:num_results]

    except WebDriverException as e:
        logger.error(f"Error performing Google search: {e}")
        return []


def search_duckduckgo(query: str, num_results: int = 5) -> list:
    """
    Fallback search using DuckDuckGo with Selenium.

    Args:
        query: Search query string
        num_results: Number of results to return

    Returns:
        List of URLs from search results
    """
    encoded_query = quote_plus(query)
    url = f"https://duckduckgo.com/?q={encoded_query}&t=h_&ia=web"

    try:
        driver = get_driver()
        driver.get(url)
        time.sleep(random.uniform(2, 4))

        urls = []

        # Find result links
        try:
            links = driver.find_elements(By.CSS_SELECTOR, 'a[data-testid="result-title-a"], article a[href^="http"]')
            for link in links:
                href = link.get_attribute('href')
                if href and href.startswith('http') and 'duckduckgo' not in href:
                    if validate_url(href) and href not in urls:
                        urls.append(href)
                    if len(urls) >= num_results:
                        break
        except Exception:
            pass

        return urls[:num_results]

    except WebDriverException as e:
        logger.error(f"Error performing DuckDuckGo search: {e}")
        return []


def extract_domain_from_results(urls: list, company_name: str) -> Optional[str]:
    """
    Extract the most likely company website from search results.

    Args:
        urls: List of URLs from search
        company_name: Company name to match against

    Returns:
        Best matching company website URL or None
    """
    company_clean = clean_company_name(company_name).lower()
    company_words = set(company_clean.split())

    # Remove very common words
    stop_words = {'the', 'and', 'of', 'for', 'in', 'on', 'at', 'to', 'a', 'an'}
    company_words = company_words - stop_words

    for url in urls:
        # Skip job boards and social media
        if is_job_board_url(url):
            continue

        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Remove www prefix
            if domain.startswith('www.'):
                domain = domain[4:]

            # Check if any company word is in domain
            domain_name = domain.split('.')[0]

            # Direct match
            for word in company_words:
                if len(word) > 2 and word in domain_name:
                    logger.debug(f"Found domain match: {url} (matched '{word}')")
                    return url

        except Exception:
            continue

    # If no direct match found, return first non-job-board URL
    for url in urls:
        if not is_job_board_url(url):
            return url

    return None


def get_company_website(company_name: str, location: str = "") -> Optional[str]:
    """
    Find the company's website using search engines.

    Args:
        company_name: Name of the company
        location: Optional location to narrow search

    Returns:
        Company website URL or None if not found
    """
    if not company_name or company_name.lower() == "unknown company":
        return None

    clean_name = clean_company_name(company_name)
    logger.info(f"Searching for website: {clean_name}")

    # Build search queries - try multiple approaches
    queries = [
        f'"{clean_name}" {location} official website',
        f'{clean_name} {location} site:.co.uk OR site:.com',
        f'{clean_name} company website',
    ]

    for query in queries:
        # Try Google first
        urls = search_google(query, num_results=5)

        if not urls:
            # Fallback to DuckDuckGo
            urls = search_duckduckgo(query, num_results=5)

        if urls:
            website = extract_domain_from_results(urls, company_name)
            if website:
                logger.info(f"Found website for {company_name}: {website}")
                return website

        # Short delay between query attempts
        time.sleep(random.uniform(2, 4))

    logger.warning(f"Could not find website for: {company_name}")
    return None


def verify_website_active(url: str, timeout: int = 10) -> bool:
    """
    Verify that a website is active and accessible.

    Args:
        url: URL to verify
        timeout: Request timeout in seconds

    Returns:
        True if website is accessible
    """
    if not url:
        return False

    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml',
    }

    try:
        response = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        return response.status_code < 400
    except requests.RequestException:
        try:
            # Try GET if HEAD fails
            response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            return response.status_code < 400
        except requests.RequestException:
            return False


if __name__ == "__main__":
    # Test the website finder
    test_companies = [
        ("Wm Pringle & Son Ltd", "Carluke"),
        ("Blythswood Care", "Glasgow"),
        ("Test Company XYZ", "Edinburgh"),
    ]

    for company, location in test_companies:
        website = get_company_website(company, location)
        print(f"{company}: {website or 'Not found'}")
