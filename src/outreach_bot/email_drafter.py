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
MESSAGE_PROMPT_TEMPLATE = """You are writing an outreach message for Philip Ross, a Scottish automation consultant.
Match his writing style exactly based on these real examples he's written:

EXAMPLE 1:
"Since my internship ended, I have started working on finding the work people don't need to do. Then I automate it. To allow people to get more done at work by cutting repetitive tasks and processes.
From what I could find on Redpath Bruce it looks like you may use the CPL software.
One suggestion I researched was that CPL seems to not keep track on the progress of complaints, nor does it fully automate dealing with them.
Alternatively, there may be other tasks that are taking up your team's time which could be worth looking into.
If this is of any interest, I'd be glad to discuss with you."

EXAMPLE 2:
"I focus on finding the tasks that don't need done by humans that drain time in companies. Then I automate it.
Alan thought that these would be worth thinking about:
- SER Automation - to speed up the process
- Drawing Revision Spotting - to stop changes being missed
- Writing reports - for standardisation and speed
- Quote generation - for speed and avoiding under pricing
The aim would be to cut time on a contract, catch mistakes, and allow an increase in the number of contracts you can take on.
If you would like to discuss, I would be glad to do so."

KEY STYLE ELEMENTS:
- Conversational, not corporate
- "I focus on finding the tasks that don't need done by humans. Then I automate it."
- Suggests SPECIFIC automation ideas as bullet points (guess intelligently based on their job posting)
- Shows value: "cut time", "catch mistakes", "speed up", "stop X being missed"
- Soft close: "If this is of any interest, I'd be glad to discuss with you"
- Scottish phrasing: "I'd be glad to discuss" not "Let's schedule a call"
- NO salesy language, NO "game-changer", NO "transform your business"

NOW WRITE A MESSAGE FOR:
- Company: {company}
- Location: {location}
- They posted a job for: {job_title}

Based on the job title "{job_title}", suggest 2-4 specific automation ideas that could help with tasks that role typically handles. Be specific and practical.

FORMAT:
- Start with a brief intro about what Philip does (1-2 sentences)
- Note their job posting
- List 2-4 bullet points of automation suggestions relevant to that role
- End with soft close and mention lochross.com

IMPORTANT: Keep the message SHORT - under 120 words total (excluding sign-off). Only 2-3 bullet points max.

Sign off with:
Kind Regards,

Philip Ross
Automation Consultant
philip@lochross.com
lochross.com"""


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
            max_tokens=500,
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

    return f"""I focus on finding the tasks that don't need done by humans that drain time in companies. Then I automate it.

I noticed you're looking for a {job_title}. Before committing to a new hire, there may be tasks that could be automated instead:

- Data entry and form filling - to cut repetitive work
- Report generation - for speed and standardisation
- Email sorting and responses - to stop distractions
- Invoice processing - to avoid mistakes and delays

The aim would be to free up your team's time for work that actually needs a human.

If this is of any interest, I'd be glad to discuss with you.

Kind Regards,

Philip Ross
Automation Consultant
philip@lochross.com
lochross.com"""


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
