import json
import os
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables from .env file
load_dotenv()

# Validate API Key
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
GEMINI_MODEL = os.getenv('GEMINI_MODEL')
TARGET_INTERNSHIP_START = os.getenv('TARGET_INTERNSHIP_START', 'février 2025')
if not GOOGLE_API_KEY:
    raise ValueError("Invalid or placeholder API key detected. Replace with your actual Gemini API key in .env file")
if not GEMINI_MODEL:
    raise ValueError("GEMINI_MODEL is not set. Define it in .env (for example: gemini-1.5-flash).")

# Configure the Gemini API
genai.configure(api_key=GOOGLE_API_KEY)

KIOSQUE_URL = "https://gdr-iasis.cnrs.fr/kiosque/"
STAGE_SECTION_LABEL = "Propositions de postes"
EMAIL_REGEX = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
RESUME_FILE = os.getenv('RESUME_FILE', 'resume.json')
TRACKING_FILE = os.getenv('TRACKING_FILE', 'email_tracking.json')
GENERATED_EMAILS_FILE = os.getenv('GENERATED_EMAILS_FILE', 'generated_emails.json')

def load_resume(json_path):
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading resume: {str(e)}")
        return {}

def load_tracking_data():
    try:
        if os.path.exists(TRACKING_FILE):
            with open(TRACKING_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'processed_entries' not in data:
                    data['processed_entries'] = data.get('processed_companies', [])
                return data
    except json.JSONDecodeError as e:
        print(f"Error loading tracking data: {str(e)}")
    return {'processed_entries': []}

def save_tracking_data(tracking_data):
    with open(TRACKING_FILE, 'w', encoding='utf-8') as f:
        json.dump(tracking_data, f, indent=2)

def load_generated_emails():
    """Load existing generated emails from JSON file"""
    try:
        if os.path.exists(GENERATED_EMAILS_FILE):
            with open(GENERATED_EMAILS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error loading email data: {str(e)}")
    return []

def save_generated_emails(email_data):
    """Save generated emails to JSON file"""
    with open(GENERATED_EMAILS_FILE, 'w', encoding='utf-8') as f:
        json.dump(email_data, f, indent=2, ensure_ascii=False)


def fetch_page(url):
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        return response.text
    except requests.RequestException as exc:
        print(f"[ERROR] Unable to fetch {url}: {exc}")
        return ""


def extract_emails_from_text(text):
    if not text:
        return []
    return sorted({email.lower() for email in EMAIL_REGEX.findall(text)})


def normalize_whitespace(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def derive_company_name(title, description):
    base = re.sub(r"\[[^\]]+\]", "", title or "").strip(" :-")
    if ":" in base:
        _, after = base.split(":", 1)
        candidate = after.strip()
        if candidate:
            return candidate
    if base:
        return base
    snippet = (description or "").split(".")[0].strip()
    return snippet if snippet else "Organisation partenaire du GdR IASIS"


def fetch_offer_details(url):
    if not url:
        return {"description": "", "emails": [], "contact_name": ""}

    html = fetch_page(url)
    if not html:
        return {"description": "", "emails": [], "contact_name": ""}

    soup = BeautifulSoup(html, 'html.parser')
    content = soup.find('div', class_='entry-content') or soup.find('article') or soup

    blocks = []
    for tag in content.find_all(['p', 'li']):
        text = tag.get_text(" ", strip=True)
        if text:
            blocks.append(text)
    description = "\n".join(blocks) if blocks else content.get_text(" ", strip=True)

    raw_html = content.decode() if hasattr(content, 'decode') else str(content)
    emails = extract_emails_from_text(description) or extract_emails_from_text(raw_html)

    contact_name = ""
    contact_label = content.find(string=lambda s: s and 'contact' in s.lower())
    if contact_label and contact_label.parent:
        contact_line = contact_label.parent.get_text(" ", strip=True)
        contact_name = contact_line.replace(contact_label.strip(), "").strip(" :")

    return {
        "description": description.strip(),
        "emails": emails,
        "contact_name": contact_name
    }


def scrape_stage_offers(max_offers=None):
    html = fetch_page(KIOSQUE_URL)
    if not html:
        print("[ERROR] Failed to load GdR IASIS kiosk page.")
        return []

    soup = BeautifulSoup(html, 'html.parser')
    header = soup.find(lambda tag: tag.name in ('h2', 'h3') and STAGE_SECTION_LABEL in tag.get_text())
    if not header:
        print(f"[ERROR] Unable to locate section '{STAGE_SECTION_LABEL}'.")
        return []

    offers_list = header.find_next('ul')
    if not offers_list:
        print("[ERROR] Unable to locate the offers list on the kiosk page.")
        return []

    offers = []
    for item in offers_list.find_all('li', recursive=False):
        title = normalize_whitespace(item.get_text(" ", strip=True))
        link = item.find('a')
        url = urljoin(KIOSQUE_URL, link['href']) if link and link.get('href') else None

        details = fetch_offer_details(url)
        emails = details.get('emails', [])
        if not emails:
            print(f"[WARN] {title} - no email found, skipping this offer.")
            continue

        offer = {
            "offer_id": url or title,
            "title": title,
            "url": url,
            "description": details.get('description', ''),
            "emails": emails,
            "contact_name": details.get('contact_name', ''),
            "company_name": derive_company_name(title, details.get('description', '')),
            "company_focus": title,
        }
        offers.append(offer)

        if max_offers and len(offers) >= max_offers:
            break

    return offers

class GeminiClient:
    def __init__(self, resume_data):
        self.resume_data = resume_data
        self.model = genai.GenerativeModel(GEMINI_MODEL) 

    def _extract_profile(self):
        basics = self.resume_data.get('basics', {})
        skills = self.resume_data.get('skills', [])
        skill_keywords = []
        for skill in skills:
            for keyword in skill.get('keywords', []):
                if keyword and keyword not in skill_keywords:
                    skill_keywords.append(keyword)

        primary_skills = ', '.join(skill_keywords[:8]) if skill_keywords else 'Python, Machine Learning, analyse de donnees'

        return {
            'name': basics.get('name', 'Votre Nom'),
            'email': basics.get('email', 'votre.email@example.com'),
            'phone': basics.get('phone', ''),
            'linkedin': self._extract_linkedin_url(basics),
            'school': self._extract_school_name(),
            'program': self._extract_program_name(),
            'skills': primary_skills,
        }

    def _extract_program_name(self):
        education = self.resume_data.get('education', [])
        if education:
            first = education[0]
            area = first.get('area', '')
            study_type = first.get('studyType', '')
            if area and study_type:
                return f"{study_type} en {area}"
            return area or study_type or 'Programme en Intelligence Artificielle'
        return 'Programme en Intelligence Artificielle'

    def _extract_school_name(self):
        education = self.resume_data.get('education', [])
        if education:
            return education[0].get('institution', "votre etablissement")
        return "votre etablissement"

    def _extract_linkedin_url(self, basics):
        for profile in basics.get('profiles', []):
            if (profile.get('network') or '').lower() == 'linkedin':
                return profile.get('url', '')
        return ''

    def _build_signature(self, profile):
        contact_parts = [p for p in [profile['phone'], profile['email'], profile['linkedin']] if p]
        contact_line = ' | '.join(contact_parts)
        if contact_line:
            return f"Cordialement,\n{profile['name']}\n{contact_line}"
        return f"Cordialement,\n{profile['name']}"

    def generate_email(self, offer):
        profile = self._extract_profile()
        
        company_name = offer.get('company_name') or 'votre organisation'
        offer_title = offer.get('title') or 'Offre de stage en intelligence artificielle'
        description = normalize_whitespace((offer.get('description') or '').strip())
        description_summary = description if len(description) <= 800 else f"{description[:800]}..."
        contact_name = offer.get('contact_name') or 'Responsable du recrutement'
        contact_email = offer.get('emails', [''])[0] if offer.get('emails') else ''
        offer_url = offer.get('url') or KIOSQUE_URL
        
        prompt = f"""
Écris un email professionnel pour une candidature de stage de fin d'études pret a l'envoi.

INFORMATIONS CANDIDAT:
    - Nom: {profile['name']}
    - Formation: Etudiant en derniere annee
    - Ecole: {profile['school']}
    - Programme: {profile['program']}
    - Competences: {profile['skills']}
    - Periode souhaitee: Debut {TARGET_INTERNSHIP_START}

INFORMATIONS OFFRE SCRAPÉE:
- Nom ou entité associée: {company_name}
- Titre de l'offre: {offer_title}
- Description courte: {description_summary}
- Contact référencé: {contact_name}
- Email de contact: {contact_email}
- Lien source: {offer_url}

STRUCTURE REQUISE:
1. Objet: "Candidature Stage PFE Intelligence Artificielle - {profile['name']}"
2. Corps de l'email (120-150 mots):
   - Salutation personnalisée
    - Présentation du profil académique actuel seulement ({profile['program']})
   - Intérêt explicite pour {offer_title} en reliant la mission aux besoins décrits
   - Compétences pertinentes avec exemples de projets concrets en IA/data
   - Demande d'entretien
   - Mention du CV en pièce jointe
3. Signature exacte:
{self._build_signature(profile)}

STYLE: Professionnel, naturel, spécifique aux technologies mentionnées."""


        response = self.model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=500,
            )
        )
        
        # Check if response is valid and has content
        if not response or not response.candidates:
            raise Exception("No response generated from Gemini API")
        
        candidate = response.candidates[0]
        if not candidate.content or not candidate.content.parts:
            finish_reason = candidate.finish_reason if hasattr(candidate, 'finish_reason') else 'unknown'
            raise Exception(f"Content generation failed. Finish reason: {finish_reason}")
        
        # Check for safety issues
        if hasattr(candidate, 'finish_reason') and candidate.finish_reason == 2:
            raise Exception("Content blocked by safety filters")
        
        response_text = candidate.content.parts[0].text
        if not response_text:
            raise Exception("Empty response from Gemini API")
            
        return self.parse_email_response(response_text)
    
    def parse_email_response(self, email_text):
        """Parse email response into subject and body components"""
        parts = email_text.split('\n\n', 1)
        if len(parts) >= 2:
            # Extract subject from first line
            subject_line = parts[0].strip()
            if subject_line.startswith('Subject:'):
                subject = subject_line[8:].strip()
            else:
                subject = subject_line
            
            # The rest is the body
            body = parts[1].strip()
        else:
            # Fallback if parsing fails
            subject = "Internship Request"
            body = email_text.strip()
        
        return subject, body


def main():
    offers = scrape_stage_offers()
    if not offers:
        print("[ERROR] No internship offers scraped. Exiting.")
        return

    resume_data = load_resume(RESUME_FILE)
    if not resume_data:
        print("[ERROR] No resume data loaded. Exiting.")
        return

    tracking_data = load_tracking_data()
    tracking_entries = tracking_data.setdefault('processed_entries', [])
    existing_emails = load_generated_emails()

    processed_entries = {
        e.get('offer_id') or e.get('offer_url') or e.get('company_name')
        for e in existing_emails
    }
    processed_entries.update(tracking_entries)

    client = GeminiClient(resume_data)

    for offer in offers:
        offer_id = offer.get('offer_id') or offer.get('url') or offer.get('title')
        company_display = offer.get('company_name') or offer.get('title') or "Organisation"

        if not offer_id:
            print(f"[WARN] Missing identifier for offer '{company_display}'. Skipping.")
            continue

        if offer_id in processed_entries:
            print(f"[SKIP] {company_display} - already processed.")
            continue

        try:
            print(f"[INFO] Generating email for {company_display}...")
            subject, body = client.generate_email(offer)

            email_obj = {
                "offer_id": offer_id,
                "company_name": offer.get('company_name'),
                "offer_title": offer.get('title'),
                "offer_url": offer.get('url'),
                "hr_name": offer.get('contact_name', ''),
                "hr_email": offer['emails'][0],
                "additional_emails": offer['emails'][1:],
                "offer_description": offer.get('description', ''),
                "email_subject": subject,
                "email_body": body
            }

            existing_emails.append(email_obj)
            save_generated_emails(existing_emails)

            tracking_entries.append(offer_id)
            save_tracking_data(tracking_data)

            processed_entries.add(offer_id)

            print(f"[SUCCESS] Email saved for {company_display}")

        except Exception as e:
            error_str = str(e)
            if "429" in error_str and "quota" in error_str.lower():
                print("\n[QUOTA LIMIT REACHED] API quota limit has been reached.")
                print("Progress has been saved. You can run the script again later to continue.")
                print(f"Processed {len(existing_emails)} offers so far.")
                return  # Exit the script when quota is reached
            elif "safety filters" in error_str.lower():
                print(f"[SKIP] {company_display} - Content blocked by safety filters. Skipping...")
                tracking_entries.append(offer_id)
                save_tracking_data(tracking_data)
                continue
            elif "finish reason" in error_str.lower():
                print(f"[SKIP] {company_display} - Generation failed: {error_str}. Skipping...")
                tracking_entries.append(offer_id)
                save_tracking_data(tracking_data)
                continue
            else:
                print(f"[ERROR] Failed to generate email for {company_display}: {error_str}")

    print(f"\n[INFO] Email generation completed. Total processed: {len(existing_emails)}")

if __name__ == "__main__":
    main()