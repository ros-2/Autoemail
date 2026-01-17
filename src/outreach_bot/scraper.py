"""Job scraper for Indeed UK and S1jobs using Selenium."""
import random
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote_plus, urljoin

import yaml
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)
from webdriver_manager.chrome import ChromeDriverManager

from .utils.logger import get_logger

logger = get_logger('outreach_bot.scraper')


def clean_text(text: str) -> str:
    """Clean text by taking first line only and stripping whitespace."""
    if not text:
        return ""
    # Take first line only (removes location mixed in with company name)
    return text.split('\n')[0].strip()


# User agents for rotation
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
]


def load_config() -> dict:
    """Load configuration from YAML file."""
    config_path = Path(__file__).parent.parent.parent / 'config' / 'config.yaml'
    if config_path.exists():
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    return {}


def create_driver() -> webdriver.Chrome:
    """Create a Selenium Chrome driver with anti-detection settings."""
    options = Options()

    # Random user agent
    user_agent = random.choice(USER_AGENTS)
    options.add_argument(f'user-agent={user_agent}')

    # Anti-detection settings
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)

    # Performance settings
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')

    # Run headless for automation
    options.add_argument('--headless=new')

    # Disable images for faster loading
    prefs = {
        'profile.managed_default_content_settings.images': 2,
        'profile.default_content_setting_values.notifications': 2,
    }
    options.add_experimental_option('prefs', prefs)

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        # Remove webdriver flag
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            '''
        })

        return driver
    except Exception as e:
        logger.error(f"Failed to create Chrome driver: {e}")
        raise


def parse_posted_date(date_text: str) -> Optional[datetime]:
    """
    Parse job posting date from text like 'Posted 1 day ago', 'Just posted', etc.

    Args:
        date_text: Raw date text from job listing

    Returns:
        Datetime object or None if couldn't parse
    """
    date_text = date_text.lower().strip()
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if 'just posted' in date_text or 'today' in date_text:
        return today

    # Match patterns like "1 day ago", "2 days ago"
    day_match = re.search(r'(\d+)\s*day', date_text)
    if day_match:
        days = int(day_match.group(1))
        return today - timedelta(days=days)

    # Match patterns like "1 hour ago", "5 hours ago"
    hour_match = re.search(r'(\d+)\s*hour', date_text)
    if hour_match:
        return today

    # Match patterns like "Active X days ago"
    active_match = re.search(r'active\s+(\d+)\s*day', date_text)
    if active_match:
        days = int(active_match.group(1))
        return today - timedelta(days=days)

    return None


def should_exclude_job(company: str, title: str, config: dict) -> bool:
    """
    Check if a job should be excluded based on company name or title.

    Args:
        company: Company name
        title: Job title
        config: Configuration dictionary

    Returns:
        True if job should be excluded
    """
    exclude_keywords = config.get('scraping', {}).get('exclude_keywords', [])

    text_to_check = f"{company} {title}".lower()

    for keyword in exclude_keywords:
        if keyword.lower() in text_to_check:
            logger.debug(f"Excluding job due to keyword '{keyword}': {company} - {title}")
            return True

    return False


def random_delay(min_sec: float = 5, max_sec: float = 10) -> None:
    """Sleep for a random duration between min and max seconds."""
    delay = random.uniform(min_sec, max_sec)
    logger.debug(f"Waiting {delay:.1f} seconds...")
    time.sleep(delay)


def scrape_indeed(driver: webdriver.Chrome, config: dict, max_results: int = 15) -> List[Dict]:
    """
    Scrape job listings from Indeed UK.

    Args:
        driver: Selenium WebDriver instance
        config: Configuration dictionary
        max_results: Maximum number of results to return

    Returns:
        List of job dictionaries
    """
    jobs = []
    scraping_config = config.get('scraping', {})
    search_terms = scraping_config.get('search_terms', ['administrator'])
    locations = scraping_config.get('locations', ['Scotland'])
    max_age_days = scraping_config.get('max_age_days', 2)
    delay_range = scraping_config.get('delay_between_requests', [5, 10])

    cutoff_date = datetime.now() - timedelta(days=max_age_days)

    for term in search_terms:
        if len(jobs) >= max_results:
            break

        for location in locations:
            if len(jobs) >= max_results:
                break

            # Build Indeed URL with filters
            # fromage=2 means jobs posted in last 2 days
            query = quote_plus(term)
            loc = quote_plus(location)
            url = f"https://uk.indeed.com/jobs?q={query}&l={loc}&fromage={max_age_days}"

            logger.info(f"Scraping Indeed: '{term}' in {location}")

            try:
                driver.get(url)
                random_delay(delay_range[0], delay_range[1])

                # Wait for job cards to load
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[class*="job_seen_beacon"], [class*="jobsearch-ResultsList"]'))
                )

                # Find all job cards
                job_cards = driver.find_elements(By.CSS_SELECTOR, '[class*="job_seen_beacon"]')

                if not job_cards:
                    # Try alternative selectors
                    job_cards = driver.find_elements(By.CSS_SELECTOR, '.result, .jobsearch-ResultsList > li')

                logger.info(f"Found {len(job_cards)} job cards")

                for card in job_cards:
                    if len(jobs) >= max_results:
                        break

                    try:
                        # Extract job title
                        title_elem = card.find_element(By.CSS_SELECTOR, '[class*="jobTitle"] a, h2 a, .title a')
                        title = title_elem.text.strip()
                        job_url = title_elem.get_attribute('href')

                        # Extract company name
                        try:
                            company_elem = card.find_element(By.CSS_SELECTOR, '[data-testid="company-name"], .companyName, [class*="company"]')
                            company = clean_text(company_elem.text)
                        except NoSuchElementException:
                            company = "Unknown Company"

                        # Extract location
                        try:
                            location_elem = card.find_element(By.CSS_SELECTOR, '[data-testid="text-location"], .companyLocation, [class*="location"]')
                            job_location = clean_text(location_elem.text)
                        except NoSuchElementException:
                            job_location = location

                        # Extract posted date
                        try:
                            date_elem = card.find_element(By.CSS_SELECTOR, '[class*="date"], .date, [data-testid="myJobsStateDate"]')
                            date_text = date_elem.text.strip()
                            posted_date = parse_posted_date(date_text)
                        except NoSuchElementException:
                            posted_date = datetime.now()

                        # Check if job is too old
                        if posted_date and posted_date < cutoff_date:
                            logger.debug(f"Skipping old job: {title} at {company}")
                            continue

                        # Check exclusions
                        if should_exclude_job(company, title, config):
                            continue

                        # Check for duplicates
                        if any(j['company'].lower() == company.lower() and j['title'].lower() == title.lower() for j in jobs):
                            continue

                        job = {
                            'company': company,
                            'title': title,
                            'location': job_location,
                            'url': job_url,
                            'posted_date': posted_date.strftime('%Y-%m-%d') if posted_date else datetime.now().strftime('%Y-%m-%d'),
                            'source': 'indeed'
                        }

                        jobs.append(job)
                        logger.info(f"Found job: {company} - {title} ({job_location})")

                    except NoSuchElementException as e:
                        logger.debug(f"Could not extract job details: {e}")
                        continue

            except TimeoutException:
                logger.warning(f"Timeout loading Indeed results for '{term}' in {location}")
            except WebDriverException as e:
                if 'blocked' in str(e).lower() or '403' in str(e) or '429' in str(e):
                    logger.error("Indeed appears to have blocked our requests. Stopping scrape.")
                    return jobs
                logger.error(f"WebDriver error on Indeed: {e}")

            random_delay(delay_range[0], delay_range[1])

    return jobs


def scrape_s1jobs(driver: webdriver.Chrome, config: dict, max_results: int = 15) -> List[Dict]:
    """
    Scrape job listings from S1jobs.

    Args:
        driver: Selenium WebDriver instance
        config: Configuration dictionary
        max_results: Maximum number of results to return

    Returns:
        List of job dictionaries
    """
    jobs = []
    scraping_config = config.get('scraping', {})
    search_terms = scraping_config.get('search_terms', ['administrator'])
    max_age_days = scraping_config.get('max_age_days', 2)
    delay_range = scraping_config.get('delay_between_requests', [5, 10])

    cutoff_date = datetime.now() - timedelta(days=max_age_days)

    for term in search_terms:
        if len(jobs) >= max_results:
            break

        # S1jobs URL structure
        query = quote_plus(term)
        url = f"https://www.s1jobs.com/jobs/?keywords={query}&location=Scotland"

        logger.info(f"Scraping S1jobs: '{term}'")

        try:
            driver.get(url)
            random_delay(delay_range[0], delay_range[1])

            # Wait for job listings to load
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '.job-listing, .search-results, article'))
            )

            # Find job cards - S1jobs uses different selectors
            job_cards = driver.find_elements(By.CSS_SELECTOR, '.job-listing, article.job, .search-result-item')

            if not job_cards:
                # Try broader selector
                job_cards = driver.find_elements(By.CSS_SELECTOR, '[class*="job"], [class*="listing"]')

            logger.info(f"Found {len(job_cards)} job cards on S1jobs")

            for card in job_cards:
                if len(jobs) >= max_results:
                    break

                try:
                    # Extract job title and URL
                    title_elem = card.find_element(By.CSS_SELECTOR, 'h2 a, h3 a, .job-title a, a[class*="title"]')
                    title = title_elem.text.strip()
                    job_url = title_elem.get_attribute('href')

                    if not title or not job_url:
                        continue

                    # Extract company
                    try:
                        company_elem = card.find_element(By.CSS_SELECTOR, '.company, .employer, [class*="company"]')
                        company = company_elem.text.strip()
                    except NoSuchElementException:
                        company = "Unknown Company"

                    # Extract location
                    try:
                        location_elem = card.find_element(By.CSS_SELECTOR, '.location, [class*="location"]')
                        job_location = location_elem.text.strip()
                    except NoSuchElementException:
                        job_location = "Scotland"

                    # Extract posted date
                    try:
                        date_elem = card.find_element(By.CSS_SELECTOR, '.date, .posted, [class*="date"]')
                        date_text = date_elem.text.strip()
                        posted_date = parse_posted_date(date_text)
                    except NoSuchElementException:
                        posted_date = datetime.now()

                    # Check if job is too old
                    if posted_date and posted_date < cutoff_date:
                        continue

                    # Check exclusions
                    if should_exclude_job(company, title, config):
                        continue

                    # Check for duplicates
                    if any(j['company'].lower() == company.lower() and j['title'].lower() == title.lower() for j in jobs):
                        continue

                    job = {
                        'company': company,
                        'title': title,
                        'location': job_location,
                        'url': job_url if job_url.startswith('http') else f"https://www.s1jobs.com{job_url}",
                        'posted_date': posted_date.strftime('%Y-%m-%d') if posted_date else datetime.now().strftime('%Y-%m-%d'),
                        'source': 's1jobs'
                    }

                    jobs.append(job)
                    logger.info(f"Found job: {company} - {title} ({job_location})")

                except NoSuchElementException:
                    continue

        except TimeoutException:
            logger.warning(f"Timeout loading S1jobs results for '{term}'")
        except WebDriverException as e:
            if 'blocked' in str(e).lower() or '403' in str(e) or '429' in str(e):
                logger.error("S1jobs appears to have blocked our requests. Stopping scrape.")
                return jobs
            logger.error(f"WebDriver error on S1jobs: {e}")

        random_delay(delay_range[0], delay_range[1])

    return jobs


def find_new_jobs(max_results: int = 15) -> List[Dict]:
    """
    Main function to find new job postings from all configured job boards.

    Args:
        max_results: Maximum total results to return

    Returns:
        List of job dictionaries with keys:
        - company: Company name
        - title: Job title
        - location: Job location
        - url: Link to job posting
        - posted_date: Date posted (YYYY-MM-DD)
        - source: Job board source (indeed/s1jobs)
    """
    config = load_config()
    all_jobs = []
    driver = None

    try:
        logger.info("Starting job scraper...")
        driver = create_driver()

        # Scrape Indeed UK
        indeed_jobs = scrape_indeed(driver, config, max_results=max_results)
        all_jobs.extend(indeed_jobs)
        logger.info(f"Found {len(indeed_jobs)} jobs from Indeed UK")

        # Scrape S1jobs if we haven't hit the limit
        if len(all_jobs) < max_results:
            remaining = max_results - len(all_jobs)
            s1_jobs = scrape_s1jobs(driver, config, max_results=remaining)

            # Filter duplicates across sources
            for job in s1_jobs:
                if not any(
                    j['company'].lower() == job['company'].lower() and
                    j['title'].lower() == job['title'].lower()
                    for j in all_jobs
                ):
                    all_jobs.append(job)

            logger.info(f"Found {len(s1_jobs)} jobs from S1jobs")

        logger.info(f"Total unique jobs found: {len(all_jobs)}")

    except Exception as e:
        logger.error(f"Error during job scraping: {e}")

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    return all_jobs[:max_results]


if __name__ == "__main__":
    # Test the scraper
    jobs = find_new_jobs(max_results=5)
    print(f"\nFound {len(jobs)} jobs:")
    for job in jobs:
        print(f"  - {job['company']}: {job['title']} ({job['location']})")
