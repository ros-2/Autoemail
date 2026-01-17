#!/usr/bin/env python3
"""
Lochross Outreach Bot - Daily Automation Script

Runs daily at 6 AM via Windows Task Scheduler to:
1. Scrape job boards for admin/receptionist roles in Scotland
2. Find company websites and contact forms
3. Auto-fill contact forms or draft emails
4. Log everything to Google Sheets
5. Send summary email to Philip

Usage:
    python run_daily.py [--dry-run] [--max-jobs N]

Options:
    --dry-run       Run without actually submitting forms or logging to sheets
    --max-jobs N    Process maximum N jobs (default: 10)
"""
import argparse
import random
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.outreach_bot import (
    scraper,
    website_finder,
    contact_finder,
    email_drafter,
    form_filler,
    sheets_logger,
    setup_logger,
    send_summary_email,
)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Lochross Outreach Bot')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run without actually submitting forms or logging'
    )
    parser.add_argument(
        '--max-jobs',
        type=int,
        default=10,
        help='Maximum number of jobs to process (default: 10)'
    )
    return parser.parse_args()


def main():
    """Main orchestration function."""
    args = parse_args()
    logger = setup_logger('outreach_bot')

    logger.info("=" * 60)
    logger.info("LOCHROSS OUTREACH BOT - Daily Run")
    logger.info(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    logger.info("=" * 60)

    # Results tracking
    results = {
        'forms_sent': 0,
        'emails_drafted': 0,
        'manual_review': [],
        'errors': [],
        'skipped': 0,
    }

    try:
        # Step 1: Scrape jobs from job boards
        logger.info("\n[STEP 1] Scraping job boards...")
        jobs = scraper.find_new_jobs(max_results=15)
        logger.info(f"Found {len(jobs)} job postings")

        if not jobs:
            logger.warning("No jobs found. Exiting.")
            send_summary_if_live(results, args.dry_run)
            return

        # Step 2: Process each job (limit to max_jobs per day)
        processed = 0
        for job in jobs:
            if processed >= args.max_jobs:
                logger.info(f"Reached daily limit of {args.max_jobs} jobs")
                break

            logger.info(f"\n[JOB {processed + 1}] Processing: {job['company']}")
            logger.info(f"  Title: {job['title']}")
            logger.info(f"  Location: {job['location']}")
            logger.info(f"  Source: {job['source']}")

            # Check if already contacted
            if not args.dry_run:
                if sheets_logger.check_already_contacted(job['company']):
                    logger.info("  -> SKIPPED: Already contacted recently")
                    results['skipped'] += 1
                    continue

            # Step 2a: Find company website
            logger.info("  Finding company website...")
            website = website_finder.get_company_website(
                job['company'],
                job['location']
            )

            if not website:
                logger.warning("  -> No website found")
                results['manual_review'].append(job)
                log_if_live(
                    job, 'manual_review', 'no_website',
                    notes='Could not find company website',
                    dry_run=args.dry_run
                )
                processed += 1
                continue

            logger.info(f"  Website: {website}")

            # Step 2b: Generate personalized message
            logger.info("  Generating message...")
            message = email_drafter.generate_message(job)

            if not message:
                logger.warning("  -> Message generation failed")
                message = email_drafter.get_fallback_message(job)

            # Step 2c: Try to find contact form
            logger.info("  Looking for contact form...")
            form_url = contact_finder.find_contact_form(website)

            if form_url:
                logger.info(f"  Contact form found: {form_url}")

                if args.dry_run:
                    logger.info("  -> DRY RUN: Would submit form")
                    results['forms_sent'] += 1
                else:
                    # Try to submit form
                    success = form_filler.submit_form(form_url, message)

                    if success:
                        results['forms_sent'] += 1
                        sheets_logger.log_contact(
                            job, 'contact_form', 'form_sent',
                            contact=form_url, message=message
                        )
                        logger.info("  -> FORM SUBMITTED SUCCESSFULLY")
                    else:
                        # Form failed, try email fallback
                        logger.warning("  -> Form submission failed, trying email...")
                        email = contact_finder.find_email(website)

                        if email:
                            results['emails_drafted'] += 1
                            sheets_logger.log_contact(
                                job, 'email', 'email_drafted',
                                contact=email, message=message,
                                notes='Form submission failed'
                            )
                            logger.info(f"  -> EMAIL DRAFTED for {email}")
                        else:
                            results['manual_review'].append(job)
                            sheets_logger.log_contact(
                                job, 'manual_review', 'form_failed',
                                notes='Form failed, no email found'
                            )
                            logger.info("  -> MANUAL REVIEW needed")
            else:
                # No form, try email
                logger.info("  No contact form found, looking for email...")
                email = contact_finder.find_email(website)

                if email:
                    logger.info(f"  Email found: {email}")

                    if args.dry_run:
                        logger.info("  -> DRY RUN: Would draft email")
                    else:
                        sheets_logger.log_contact(
                            job, 'email', 'email_drafted',
                            contact=email, message=message
                        )

                    results['emails_drafted'] += 1
                    logger.info(f"  -> EMAIL DRAFTED for {email}")
                else:
                    logger.warning("  -> No contact method found")
                    results['manual_review'].append(job)
                    log_if_live(
                        job, 'manual_review', 'no_contact',
                        notes='No form or email found',
                        dry_run=args.dry_run
                    )

            processed += 1

            # Respectful delay between contacts
            delay = random.uniform(5, 10)
            logger.info(f"  Waiting {delay:.1f} seconds...")
            time.sleep(delay)

    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        results['errors'].append("Interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        results['errors'].append(str(e))

    # Step 3: Print and send summary
    logger.info("\n" + "=" * 60)
    logger.info("DAILY RUN COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Forms submitted:  {results['forms_sent']}")
    logger.info(f"Emails drafted:   {results['emails_drafted']}")
    logger.info(f"Manual review:    {len(results['manual_review'])}")
    logger.info(f"Skipped:          {results['skipped']}")

    if results['errors']:
        logger.info(f"Errors:           {len(results['errors'])}")

    # Send summary email
    send_summary_if_live(results, args.dry_run)


def log_if_live(job, method, status, contact=None, message=None, notes=None, dry_run=False):
    """Log to sheets only if not in dry run mode."""
    if not dry_run:
        sheets_logger.log_contact(job, method, status, contact, message, notes)


def send_summary_if_live(results, dry_run):
    """Send summary email only if not in dry run mode."""
    if dry_run:
        print("\n[DRY RUN] Would send summary email with:")
        print(f"  Forms sent: {results['forms_sent']}")
        print(f"  Emails drafted: {results['emails_drafted']}")
        print(f"  Manual review: {len(results['manual_review'])}")
    else:
        logger = setup_logger('outreach_bot')
        logger.info("\nSending summary email...")
        success = send_summary_email(results)
        if success:
            logger.info("Summary email sent!")
        else:
            logger.warning("Failed to send summary email")


if __name__ == "__main__":
    main()
