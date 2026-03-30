import smtplib
import ssl
import json
import logging
import os
import time
from email.mime.text import MIMEText
from email.utils import formataddr
from dotenv import load_dotenv

load_dotenv()

# Configuration
SENDER_EMAIL = os.getenv('GMAIL_USER') 
SENDER_PASSWORD = os.getenv('GMAIL_APP_PASSWORD')
SENDER_NAME = os.getenv('SENDER_NAME', 'Internship Candidate')
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
EMAILS_JSON_FILE = os.getenv('GENERATED_EMAILS_FILE', 'generated_emails.json')
TRACKING_FILE = os.getenv('TRACKING_FILE', 'email_tracking.json')
RESUME_LINK = os.getenv('RESUME_LINK', '').strip()

# Set up logging to console only
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

def is_valid_email(email):
    """Return True if email looks valid (basic sanity check)."""
    if not isinstance(email, str):
        return False
    candidate = email.strip()
    if not candidate:
        return False
    if '@' not in candidate:
        return False
    local, _, domain = candidate.partition('@')
    if not local or not domain or '.' not in domain:
        return False
    return True

def load_tracking_data():
    """Load tracking data from JSON file with proper initialization"""
    if os.path.exists(TRACKING_FILE):
        try:
            with open(TRACKING_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Ensure the data structure is correct
            if 'sent_emails' not in data:
                data['sent_emails'] = []
            return data
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading tracking file: {str(e)}")
            # Return properly initialized data structure
            return {"sent_emails": []}
    # Initialize new tracking file
    return {"sent_emails": []}

def update_tracking_data(company_name):
    """Update tracking file with new sent email"""
    tracking_data = load_tracking_data()
    
    # Ensure we have the correct data structure
    if 'sent_emails' not in tracking_data:
        tracking_data['sent_emails'] = []
    
    if company_name not in tracking_data["sent_emails"]:
        tracking_data["sent_emails"].append(company_name)
        
        try:
            with open(TRACKING_FILE, 'w', encoding='utf-8') as f:
                json.dump(tracking_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Updated tracking for {company_name}")
            return True
        except IOError as e:
            logger.error(f"Failed to update tracking file: {str(e)}")
            return False
    return True

def create_email_message(recipient_name, recipient_email, subject, body):
    """Create MIME email message with resume link added"""
    body_with_resume = body
    if RESUME_LINK:
        body_with_resume = f"{body}\n\nVous pouvez consulter mon CV ici : {RESUME_LINK}"
    
    msg = MIMEText(body_with_resume, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = formataddr((SENDER_NAME, SENDER_EMAIL))
    msg['To'] = formataddr((recipient_name, recipient_email))
    return msg

def send_single_email(msg, recipient_email, company_name):
    """Send a single email with confirmation and error handling"""
    context = ssl.create_default_context()
    
    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            logger.info(f"Email successfully sent to {recipient_email}")
            
            # Update tracking after successful send
            if update_tracking_data(company_name):
                return True
            logger.error(f"Sent to {recipient_email} but failed to update tracking")
            return False
    except smtplib.SMTPAuthenticationError:
        logger.error("Authentication failed. Check email credentials.")
    except smtplib.SMTPRecipientsRefused:
        logger.error(f"Recipient refused: {recipient_email}")
    except smtplib.SMTPSenderRefused:
        logger.error("Sender address refused.")
    except smtplib.SMTPDataError as e:
        logger.error(f"SMTP data error: {str(e)}")
    except smtplib.SMTPException as e:
        logger.error(f"SMTP general error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
    
    return False

def main():
    """Main function to process and send emails sequentially"""
    # Validate environment variables
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        logger.error("Email credentials not set in environment variables")
        return
    
    # Load tracking data
    tracking_data = load_tracking_data()
    sent_emails = set(tracking_data.get("sent_emails", []))
    logger.info(f"Loaded {len(sent_emails)} previously sent emails from tracking")
    
    # Load email data
    try:
        with open(EMAILS_JSON_FILE, 'r', encoding='utf-8') as f:
            emails = json.load(f)
        logger.info(f"Loaded {len(emails)} email records")
    except FileNotFoundError:
        logger.error(f"Email file not found: {EMAILS_JSON_FILE}")
        return
    except json.JSONDecodeError:
        logger.error("Invalid JSON format in email file")
        return
    
    # Filter out already sent emails
    emails_to_send = [
        e for e in emails 
        if e['company_name'] not in sent_emails
    ]
    skipped = len(emails) - len(emails_to_send)
    logger.info(f"Skipped {skipped} already sent emails. {len(emails_to_send)} emails to send")
    
    # Process emails sequentially
    successful_sends = 0
    for idx, email_data in enumerate(emails_to_send, 1):
        company_name = email_data['company_name']
        logger.info(f"Processing email {idx}/{len(emails_to_send)} to {company_name}")
        
        # Validate recipient email before creating message
        try:
            recipient_email = email_data['hr_email']
            recipient_name = email_data.get('hr_name', '')
            if not is_valid_email(recipient_email):
                logger.warning(f"Skipping {company_name}: invalid or missing hr_email -> {recipient_email}")
                # Mark as sent to avoid retrying broken data in next runs
                update_tracking_data(company_name)
                continue

            msg = create_email_message(
                recipient_name=recipient_name,
                recipient_email=recipient_email,
                subject=email_data['email_subject'],
                body=email_data['email_body']
            )
        except KeyError as e:
            logger.error(f"Missing required field in email data: {str(e)}")
            # Mark as sent to avoid blocking on malformed record
            update_tracking_data(company_name)
            continue
        
        # Send email with retries
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            logger.info(f"Attempt {attempt}/{max_retries} for {company_name}")
            if send_single_email(msg, recipient_email, company_name):
                successful_sends += 1
                break
            if attempt < max_retries:
                wait_time = 5 * attempt  # Exponential backoff
                logger.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
        else:
            logger.error(f"Failed to send to {company_name} after {max_retries} attempts. Stopping.")
            break  # Stop entire process on failure
    
    logger.info(f"Process completed. Successfully sent {successful_sends}/{len(emails_to_send)} emails")

if __name__ == "__main__":
    main()