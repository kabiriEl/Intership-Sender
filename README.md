# AI Internship Email Automation

Projet Python pour:
- scraper des offres de stage (GdR IASIS),
- generer des emails de candidature personnalises avec Gemini,
- envoyer les emails via Gmail SMTP,
- suivre les emails deja traites/envoyes.



## Architecture du projet

```text
stage/
├── generate_emails.py            # Scraping + generation des emails
├── send_emails.py                # Envoi SMTP des emails generes
├── requirements.txt              # Dependances Python
├── .env.example                  # Variables d'environnement (template)
├── .gitignore                    # Protection des fichiers sensibles
├── README.md                     # Documentation
├── resume.example.json           # Exemple de profil candidat (anonyme)
└── scripts/pre_publish_check.ps1 # Verification avant publication GitHub
```

Fichiers locaux sensibles (ignores par git):
- `.env`
- `resume.json`
- `startups.json`
- `generated_emails.json`
- `email_tracking.json`

## Installation rapide

1. Cloner le projet

```powershell
git clone <URL_DU_REPO>
cd stage
```

2. Creer et activer l'environnement virtuel

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Installer les dependances

```powershell
pip install -r requirements.txt
```

4. Initialiser la configuration locale

```powershell
copy .env.example .env
copy resume.example.json resume.json
```

Optionnel (si vous souhaitez preparer votre propre base manuelle):

```powershell
copy startups.json startups.backup.json
```

## Configuration (`.env`)

Variables obligatoires:
- `GOOGLE_API_KEY`
- `GEMINI_MODEL`
- `GMAIL_USER`
- `GMAIL_APP_PASSWORD`

Variables recommandees:
- `SENDER_NAME`
- `TARGET_INTERNSHIP_START`
- `RESUME_LINK`

Variables de chemins (optionnelles):
- `RESUME_FILE` (defaut: `resume.json`)
- `GENERATED_EMAILS_FILE` (defaut: `generated_emails.json`)
- `TRACKING_FILE` (defaut: `email_tracking.json`)

## Utilisation

1. Generer les emails

```powershell
python generate_emails.py
```

Sortie: `generated_emails.json`

2. Envoyer les emails

```powershell
python send_emails.py
```

Le script met a jour `email_tracking.json` pour eviter les doublons d'envoi.

## Personnalisation par profil

Pour adapter le projet a n'importe quel candidat:

1. Remplir `resume.json` avec:
- `basics.name`, `basics.email`, `basics.phone`
- profil LinkedIn dans `basics.profiles`
- formation dans `education`
- competences dans `skills`

2. Mettre a jour `.env`:
- `SENDER_NAME`
- `TARGET_INTERNSHIP_START`
- `RESUME_LINK`

3. Utiliser une base de cibles propre:
- les offres sont scrapees automatiquement par `generate_emails.py`
- `startups.json` peut etre garde pour votre usage perso (non requis par le script actuel)



