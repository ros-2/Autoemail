"""Email drafter using Claude API to generate personalized outreach messages."""
import os
from pathlib import Path
from typing import Dict, Optional

import yaml
from anthropic import Anthropic
from dotenv import load_dotenv

from .utils.logger import get_logger

# Load environment variables
load_dotenv()

logger = get_logger('outreach_bot.email_drafter')


def load_config() -> dict:
    """Load configuration from YAML file."""
    config_path = Path(__file__).parent.parent.parent / 'config' / 'config.yaml'
    if config_path.exists():
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    return {}


# Message template for Claude
MESSAGE_PROMPT_TEMPLATE = """Write a brief, direct business enquiry for a Scottish automation consultant.

Context:
- Company: {company}
- Location: {location}
- They just posted a job for: {job_title}
- Consultant: Philip Ross at Lochross
- Website: lochross.com
- Previous work: Saved Blythswood Care 15hrs/week through EPOS automation, built Scripture verification system for Christian Focus Publications

Write an 80-word message that:
1. References their specific job posting for {job_title}
2. Suggests automation as an alternative or complement to hiring
3. Offers a brief call or demo
4. Links to lochross.com
5. Uses a Scottish tone - direct, no fluff, no corporate jargon

Format as plain text suitable for a contact form or email body. No greeting line needed (just start with the message). No sign-off needed.

Important: Keep it under 80 words. Be specific about their job posting. Sound human and helpful, not salesy."""


def generate_message(job_info: Dict) -> Optional[str]:
    """
    Generate a personalized outreach message using Claude API.

    Args:
        job_info: Dictionary containing:
            - company: Company name
            - title: Job title they're hiring for
            - location: Job location

    Returns:
        Generated message string, or None if generation fails
    """
    api_key = os.getenv('ANTHROPIC_API_KEY')

    if not api_key:
        logger.error("ANTHROPIC_API_KEY not found in environment variables")
        return None

    company = job_info.get('company', 'your company')
    job_title = job_info.get('title', 'administrator')
    location = job_info.get('location', 'Scotland')

    prompt = MESSAGE_PROMPT_TEMPLATE.format(
        company=company,
        location=location,
        job_title=job_title
    )

    try:
        client = Anthropic(api_key=api_key)

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        # Extract text from response
        if message.content and len(message.content) > 0:
            generated_text = message.content[0].text.strip()
            logger.info(f"Generated message for {company} ({len(generated_text.split())} words)")
            return generated_text

        logger.warning(f"Empty response from Claude API for {company}")
        return None

    except Exception as e:
        logger.error(f"Error generating message with Claude API: {e}")
        return get_fallback_message(job_info)


def get_fallback_message(job_info: Dict) -> str:
    """
    Get a fallback message template when API fails.

    Args:
        job_info: Dictionary with job information

    Returns:
        Fallback message string
    """
    company = job_info.get('company', 'your company')
    job_title = job_info.get('title', 'administrator')

    return f"""I noticed you're looking for a {job_title}. Before you commit to a new hire, I'd like to show you how automation could handle some of those tasks.

I'm Philip Ross from Lochross - I help Scottish businesses automate their admin work. Recently saved Blythswood Care 15 hours a week by automating their EPOS reporting.

Would you be open to a quick call to see if automation could help? No pressure, just a conversation.

More at lochross.com"""


def generate_subject_line(job_info: Dict) -> str:
    """
    Generate an email subject line for the outreach.

    Args:
        job_info: Dictionary with job information

    Returns:
        Subject line string
    """
    job_title = job_info.get('title', 'administrator')

    # Keep it simple and relevant
    subjects = [
        f"Re: Your {job_title} vacancy - automation alternative?",
        f"Quick question about your {job_title} role",
        f"Automation for your {job_title} tasks",
    ]

    # Use first option as default
    return subjects[0]


def generate_message_with_subject(job_info: Dict) -> Dict[str, Optional[str]]:
    """
    Generate both message and subject line.

    Args:
        job_info: Dictionary with job information

    Returns:
        Dictionary with 'subject' and 'message' keys
    """
    return {
        'subject': generate_subject_line(job_info),
        'message': generate_message(job_info)
    }


if __name__ == "__main__":
    # Test the email drafter
    test_job = {
        'company': 'Test Company Ltd',
        'title': 'Transport Administrator',
        'location': 'Glasgow',
    }

    print("Testing message generation...")
    message = generate_message(test_job)
    if message:
        print(f"\nGenerated message:\n{message}")
        print(f"\nWord count: {len(message.split())}")
    else:
        print("Failed to generate message")
