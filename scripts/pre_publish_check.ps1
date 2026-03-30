$ErrorActionPreference = "Stop"

Write-Host "Checking for sensitive files before GitHub push..."

$sensitiveFiles = @(
  ".env",
  "resume.json",
  "startups.json",
  "generated_emails.json",
  "email_tracking.json"
)

if (-not (Test-Path ".git")) {
  Write-Host "No git repository found. Run 'git init' first."
  exit 0
}

$tracked = git ls-files
$foundTrackedSensitive = @()

foreach ($file in $sensitiveFiles) {
  if ($tracked -contains $file) {
    $foundTrackedSensitive += $file
  }
}

if ($foundTrackedSensitive.Count -gt 0) {
  Write-Host "Sensitive tracked files detected:" -ForegroundColor Yellow
  $foundTrackedSensitive | ForEach-Object { Write-Host " - $_" -ForegroundColor Yellow }
  Write-Host "Run:" -ForegroundColor Yellow
  Write-Host "git rm --cached .env resume.json startups.json generated_emails.json email_tracking.json" -ForegroundColor Yellow
  exit 1
}

Write-Host "OK: no sensitive tracked files detected." -ForegroundColor Green
