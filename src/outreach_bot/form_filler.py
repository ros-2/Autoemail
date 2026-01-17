"""Form filler using Selenium to auto-fill and submit contact forms."""
import random
import time
from pathlib import Path
from typing import Optional

import yaml
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementNotInteractableException,
    WebDriverException,
)
from webdriver_manager.chrome import ChromeDriverManager

from .utils.logger import get_logger

logger = get_logger('outreach_bot.form_filler')

# User agents for rotation
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

# Field selectors for common form fields
NAME_SELECTORS = [
    'input[name*="name" i]',
    'input[id*="name" i]',
    'input[placeholder*="name" i]',
    'input[name*="your-name" i]',
    'input[name="name"]',
    'input[id="name"]',
    '#your-name',
    '.name-field input',
]

EMAIL_SELECTORS = [
    'input[type="email"]',
    'input[name*="email" i]',
    'input[id*="email" i]',
    'input[placeholder*="email" i]',
    'input[name="your-email"]',
    '#email',
    '#your-email',
    '.email-field input',
]

MESSAGE_SELECTORS = [
    'textarea[name*="message" i]',
    'textarea[id*="message" i]',
    'textarea[name*="enquir" i]',
    'textarea[name*="comment" i]',
    'textarea[placeholder*="message" i]',
    'textarea',
    '#message',
    '#your-message',
    '.message-field textarea',
]

SUBMIT_SELECTORS = [
    'button[type="submit"]',
    'input[type="submit"]',
    'button:contains("Send")',
    'button:contains("Submit")',
    'input[value*="send" i]',
    'input[value*="submit" i]',
    '.submit-button',
    '#submit',
    'button.btn-submit',
    'button.wpcf7-submit',
]

# CAPTCHA indicators
CAPTCHA_INDICATORS = [
    'recaptcha',
    'g-recaptcha',
    'h-captcha',
    'captcha',
    'turnstile',
]


def load_config() -> dict:
    """Load configuration from YAML file."""
    config_path = Path(__file__).parent.parent.parent / 'config' / 'config.yaml'
    if config_path.exists():
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    return {}


def create_driver(headless: bool = True) -> webdriver.Chrome:
    """
    Create a Chrome WebDriver instance.

    Args:
        headless: Run in headless mode if True

    Returns:
        WebDriver instance
    """
    options = Options()
    options.add_argument(f'user-agent={random.choice(USER_AGENTS)}')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')

    if headless:
        options.add_argument('--headless=new')

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


def has_captcha(driver: webdriver.Chrome) -> bool:
    """
    Check if the page has a CAPTCHA.

    Args:
        driver: WebDriver instance

    Returns:
        True if CAPTCHA detected
    """
    page_source = driver.page_source.lower()

    for indicator in CAPTCHA_INDICATORS:
        if indicator in page_source:
            logger.info("CAPTCHA detected on form")
            return True

    # Also check for CAPTCHA elements
    for indicator in CAPTCHA_INDICATORS:
        elements = driver.find_elements(By.CSS_SELECTOR, f'[class*="{indicator}"], [id*="{indicator}"]')
        if elements:
            return True

    return False


def find_element_by_selectors(driver: webdriver.Chrome, selectors: list) -> Optional[any]:
    """
    Find an element using multiple selectors.

    Args:
        driver: WebDriver instance
        selectors: List of CSS selectors to try

    Returns:
        WebElement if found, None otherwise
    """
    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for element in elements:
                if element.is_displayed() and element.is_enabled():
                    return element
        except Exception:
            continue

    return None


def type_like_human(element, text: str) -> None:
    """
    Type text into an element with human-like delays.

    Args:
        element: WebElement to type into
        text: Text to type
    """
    element.clear()
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.02, 0.08))


def submit_form(
    form_url: str,
    message: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    headless: bool = True
) -> bool:
    """
    Fill and submit a contact form.

    Args:
        form_url: URL of the contact form page
        message: Message to send
        name: Name to use (defaults to config value)
        email: Email to use (defaults to config value)
        headless: Run browser in headless mode

    Returns:
        True if form submitted successfully, False otherwise
    """
    config = load_config()
    contact_config = config.get('contact', {})

    # Get default values from config
    if name is None:
        name = contact_config.get('user_name', 'Philip Ross')
    if email is None:
        email = contact_config.get('user_email', 'philip@lochross.com')

    logger.info(f"Attempting to fill form at: {form_url}")

    driver = None
    try:
        driver = create_driver(headless=headless)
        driver.get(form_url)

        # Wait for page to load
        time.sleep(3)

        # Check for CAPTCHA
        if has_captcha(driver):
            logger.warning("Form has CAPTCHA - cannot auto-fill")
            return False

        # Find and fill name field
        name_field = find_element_by_selectors(driver, NAME_SELECTORS)
        if name_field:
            logger.debug("Found name field")
            type_like_human(name_field, name)
            time.sleep(random.uniform(0.5, 1))
        else:
            logger.debug("No name field found")

        # Find and fill email field
        email_field = find_element_by_selectors(driver, EMAIL_SELECTORS)
        if email_field:
            logger.debug("Found email field")
            type_like_human(email_field, email)
            time.sleep(random.uniform(0.5, 1))
        else:
            logger.warning("No email field found - form may require email")

        # Find and fill message field
        message_field = find_element_by_selectors(driver, MESSAGE_SELECTORS)
        if message_field:
            logger.debug("Found message field")
            type_like_human(message_field, message)
            time.sleep(random.uniform(0.5, 1))
        else:
            logger.warning("No message field found - cannot submit form")
            return False

        # Take a brief pause before submitting
        time.sleep(random.uniform(1, 2))

        # Find and click submit button
        submit_button = find_element_by_selectors(driver, SUBMIT_SELECTORS)

        if not submit_button:
            # Try finding by button text
            buttons = driver.find_elements(By.TAG_NAME, 'button')
            for button in buttons:
                text = button.text.lower()
                if any(word in text for word in ['send', 'submit', 'enquire', 'contact']):
                    submit_button = button
                    break

        if submit_button:
            logger.debug("Found submit button")

            # Scroll to button
            driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
            time.sleep(0.5)

            # Click submit
            try:
                submit_button.click()
            except ElementNotInteractableException:
                # Try JavaScript click as fallback
                driver.execute_script("arguments[0].click();", submit_button)

            logger.info("Form submitted")

            # Wait for response
            time.sleep(3)

            # Check for success indicators
            page_source = driver.page_source.lower()
            success_indicators = [
                'thank you',
                'thanks',
                'success',
                'received',
                'sent',
                'submitted',
                'we will',
                "we'll be in touch",
                'confirmation',
            ]

            for indicator in success_indicators:
                if indicator in page_source:
                    logger.info(f"Form submission confirmed: found '{indicator}'")
                    return True

            # Check for error indicators
            error_indicators = [
                'error',
                'failed',
                'invalid',
                'required',
                'please fill',
            ]

            for indicator in error_indicators:
                if indicator in page_source:
                    logger.warning(f"Form submission may have failed: found '{indicator}'")
                    return False

            # If no clear indicator, assume success (form was submitted)
            logger.info("Form submitted (no confirmation message detected)")
            return True

        else:
            logger.warning("No submit button found")
            return False

    except TimeoutException:
        logger.error("Timeout while filling form")
        return False

    except WebDriverException as e:
        logger.error(f"WebDriver error: {e}")
        return False

    except Exception as e:
        logger.error(f"Error filling form: {e}")
        return False

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def test_form_fillable(form_url: str) -> dict:
    """
    Test if a form can be filled without actually submitting.

    Args:
        form_url: URL of the contact form

    Returns:
        Dictionary with field detection results
    """
    driver = None
    results = {
        'has_name_field': False,
        'has_email_field': False,
        'has_message_field': False,
        'has_submit_button': False,
        'has_captcha': False,
        'fillable': False,
    }

    try:
        driver = create_driver(headless=True)
        driver.get(form_url)
        time.sleep(2)

        results['has_captcha'] = has_captcha(driver)
        results['has_name_field'] = find_element_by_selectors(driver, NAME_SELECTORS) is not None
        results['has_email_field'] = find_element_by_selectors(driver, EMAIL_SELECTORS) is not None
        results['has_message_field'] = find_element_by_selectors(driver, MESSAGE_SELECTORS) is not None
        results['has_submit_button'] = find_element_by_selectors(driver, SUBMIT_SELECTORS) is not None

        # Form is fillable if it has message field, submit button, and no CAPTCHA
        results['fillable'] = (
            results['has_message_field'] and
            results['has_submit_button'] and
            not results['has_captcha']
        )

    except Exception as e:
        logger.error(f"Error testing form: {e}")

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    return results


if __name__ == "__main__":
    # Test the form filler (without actually submitting)
    test_url = "https://www.lochross.com/contact"

    print(f"Testing form detection at: {test_url}")
    results = test_form_fillable(test_url)

    print("\nForm analysis:")
    for key, value in results.items():
        print(f"  {key}: {value}")
