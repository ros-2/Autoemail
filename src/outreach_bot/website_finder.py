"""Website finder using Google search to find company websites."""
import random
import re
import time
from typing import Optional
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup

from .utils.logger import get_logger
from .utils.validators import is_job_board_url, validate_url, clean_company_name

logger = get_logger('outreach_bot.website_finder')

# User agents for rotation
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
]


def search_google(query: str, num_results: int = 5) -> list:
    """
    Perform a Google search and return result URLs.

    Args:
        query: Search query string
        num_results: Number of results to return

    Returns:
        List of URLs from search results
    """
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-GB,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

    encoded_query = quote_plus(query)
    url = f"https://www.google.com/search?q={encoded_query}&num={num_results + 5}&hl=en"

    try:
        # Add random delay to avoid rate limiting
        time.sleep(random.uniform(1, 3))

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 429:
            logger.warning("Google rate limit hit. Waiting before retry...")
            time.sleep(30)
            return []

        if response.status_code != 200:
            logger.warning(f"Google search returned status {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')

        # Find search result links
        urls = []

        # Try multiple selectors for Google results
        selectors = [
            'div.g a[href^="http"]',
            'div.yuRUbf a',
            'a[data-ved]',
            '.r a',
        ]

        for selector in selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get('href', '')
                if href.startswith('http') and 'google' not in href:
                    # Clean up Google redirect URLs
                    if '/url?q=' in href:
                        href = href.split('/url?q=')[1].split('&')[0]

                    if validate_url(href) and href not in urls:
                        urls.append(href)

                    if len(urls) >= num_results:
                        break

            if len(urls) >= num_results:
                break

        return urls[:num_results]

    except requests.RequestException as e:
        logger.error(f"Error performing Google search: {e}")
        return []


def search_duckduckgo(query: str, num_results: int = 5) -> list:
    """
    Fallback search using DuckDuckGo HTML.

    Args:
        query: Search query string
        num_results: Number of results to return

    Returns:
        List of URLs from search results
    """
    headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-GB,en;q=0.5',
    }

    encoded_query = quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

    try:
        time.sleep(random.uniform(1, 2))

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            logger.warning(f"DuckDuckGo search returned status {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')

        urls = []
        results = soup.select('.result__url, .result__a')

        for result in results:
            href = result.get('href', '')
            if not href:
                # Try to get URL from text
                url_text = result.get_text().strip()
                if url_text and '.' in url_text:
                    href = f"https://{url_text}" if not url_text.startswith('http') else url_text

            if href and validate_url(href) and href not in urls:
                urls.append(href)

            if len(urls) >= num_results:
                break

        return urls[:num_results]

    except requests.RequestException as e:
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
