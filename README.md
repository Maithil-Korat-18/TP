# 🚀 Smart India Hackathon (SIH) Problem Statement Count Monitor

A production-ready Python monitoring application that tracks **Smart India Hackathon (SIH)** problem statement idea submission counts in real time and automatically alerts you via **Email (Gmail SMTP)** and optional **WhatsApp (Twilio)** whenever the count increases.

---

## 📑 Table of Contents

1. [Architecture & Workflow](#1-architecture--workflow)
2. [Data Extraction Verification (How SIH Count is Loaded)](#2-data-extraction-verification)
3. [Installation](#3-installation)
4. [Environment Variables & Credentials](#4-environment-variables--credentials)
5. [Finding & Configuring Problem Statements](#5-finding--configuring-problem-statements)
6. [Configuring Notifications](#6-configuring-notifications)
   * [Email (Gmail App Password)](#a-email-configuration-gmail-smtp)
   * [WhatsApp (Twilio)](#b-whatsapp-configuration-twilio)
7. [Running the Application](#7-running-the-application)
   * [Continuous Monitoring Loop](#continuous-monitoring-loop)
   * [Single Check Cycle (`--check-now`)](#single-check-cycle---check-now)
   * [Dry Run Mode (`--dry-run`)](#dry-run-mode---dry-run)
   * [Simulated Increase Test (`--simulate-increase`)](#simulated-increase-test---simulate-increase)
   * [Database Status (`--status`)](#database-status---status)
   * [Health Check (`--health`)](#health-check---health)
   * [List All Available Portal PS (`--list-ps`)](#discover--list-all-portal-problem-statements---list-ps)
8. [Automated Testing](#8-automated-testing)
9. [Deployment Options](#9-deployment-options)
   * [Local Windows (Windows Task Scheduler)](#local-windows-task-scheduler)
   * [Linux / VPS (systemd Service)](#linux--vps-systemd-service)
   * [Cloud Platforms (AWS EC2, Render, Railway, etc.)](#cloud-platforms-render-railway-aws-ec2)
10. [Troubleshooting & FAQ](#10-troubleshooting--faq)
11. [Extending the System](#11-extending-the-system)
   * [Adding a New Notification Provider](#how-to-add-a-new-notification-provider)
   * [Adding a New Data Source Scraper](#how-to-add-a-new-sih-data-source)

---

## 1. Architecture & Workflow

```
       ┌────────────────────────────────────────────────────────┐
       │               SIH Portal (sih.gov.in)                  │
       │       Public Server-Rendered HTML (table#dataTablePS)  │
       └───────────────────────────┬────────────────────────────┘
                                   │ HTTP GET (SSL / Requests)
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │              Scraper Adapter (HtmlSource)              │
       │ Parses 240+ PS: ID, Title, Submitted Idea Count (N/500)│
       └───────────────────────────┬────────────────────────────┘
                                   │ Normalized Data
                                   ▼
       ┌────────────────────────────────────────────────────────┐
       │                      SihMonitor                        │
       │  • Exponential Backoff Retries                         │
       │  • Change Detection (Baseline, Increase, Unchanged)    │
       │  • Duplicate Suppression & Cooldown Protection         │
       └──────────────┬──────────────────────────┬──────────────┘
                      │                          │
                      ▼                          ▼
      ┌──────────────────────────┐    ┌──────────────────────────┐
      │   SQLite Database (db)   │    │  NotificationDispatcher  │
      │   • ps_count_history     │    │  • EmailNotification     │
      │   • ps_notification_hist │    │  • WhatsAppNotification  │
      └──────────────────────────┘    └──────────────────────────┘
```

---

## 2. Data Extraction Verification

### Portal URL
* **URL:** `https://sih.gov.in/sih2026PS`

### Verification Summary
* **Authentication / Login Required?** **NO**. The problem statement table is completely public.
* **CAPTCHA Required?** **NO**. The listing page has no Cloudflare Turnstile, hCaptcha, or reCAPTCHA barriers.
* **How is the data rendered?** 
  The SIH backend server renders all 240+ problem statements directly into a master HTML table with `id="dataTablePS"`. Client-side JavaScript only initializes visual search/pagination via `$('#dataTablePS').DataTable()`.
* **Exact HTML Element Parsed:**
  ```html
  <table id="dataTablePS" class="table ...">
    <thead>
      <tr>
        <th>S.No.</th>
        <th>Organization</th>
        <th>Problem Statement Title</th>
        <th>Category</th>
        <th>PS Number</th>
        <th>Submitted Idea(s) Count</th>
        <th>Theme</th>
        <th>Deadline for Idea Submission</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>2</td>
        <td>Ministry of Development of North Eastern Region (MDoNER)</td>
        <td>Al-Based Smart Logistics and Accessibility Intelligence Platform...</td>
        <td>Software</td>
        <td>SIH26002</td>
        <td>204/500</td>
        <td>Transportation & Logistics</td>
        <td>30 September 2026</td>
      </tr>
    </tbody>
  </table>
  ```
* **Count Column:** Column index `5` (`Submitted Idea(s) Count`).
  Format is `<current_count>/<max_capacity>` (e.g., `204/500`).
  The regex `(\d+)\s*(?:/\s*(\d+))?` extracts:
  * `current_count = 204`
  * `max_capacity = 500`

---

## 3. Installation

### Requirements
* Python 3.9+ (Tested on Python 3.13)
* Internet access to reach `https://sih.gov.in`

### Setup

1. **Clone or navigate to the repository:**
   ```bash
   cd c:\Maithil\tp\as
   ```

2. **(Optional) Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   # Windows PowerShell:
   .\venv\Scripts\Activate.ps1
   # Linux/macOS:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

---

## 4. Environment Variables & Credentials

Never hard-code passwords, API keys, or tokens in source code or `config.yaml`. All secrets are loaded from `.env` using `python-dotenv`.

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Your `.env` file should look like this:

```env
# --- Email Notifications (Gmail SMTP) ---
SMTP_SENDER=your_email@gmail.com
SMTP_RECIPIENT=your_email@gmail.com
SMTP_APP_PASSWORD=abcd efgh ijkl mnop

# --- WhatsApp Notifications (Twilio) ---
TWILIO_ACCOUNT_SID=your_twilio_account_sid_here
TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
TWILIO_FROM_NUMBER=whatsapp:+14155238886
TWILIO_TO_NUMBER=whatsapp:+919876543210
```

> [!IMPORTANT]
> For SIH scraping itself, **NO** credentials or API keys are required. You only need credentials for the notification channels (Email or WhatsApp) you wish to receive alerts on.

---

## 5. Finding & Configuring Problem Statements

### How to list all available Problem Statements
Run:
```bash
python app.py --list-ps
```
This connects to the live SIH portal and lists the PS ID, current idea count, category, and title.

### Configuring in `config.yaml`
Open `config.yaml` and specify the problem statements you want to track:

```yaml
sih:
  url: "https://sih.gov.in/sih2026PS"

# Multi-PS Support: Monitor one or more PS simultaneously
problem_statements:
  - id: "SIH26002"
    title: "Al-Based Smart Logistics and Accessibility Intelligence Platform for North Eastern Region (NER)"
    enabled: true

  - id: "SIH26004"
    title: "Al-Assisted Early Detection System for Osteoarthritis (OA) Risk Markers in North Eastern Region (NER)"
    enabled: true

  - id: "SIH26005"
    title: "Solar-Powered Smart Mini Cold Storage System for Fresh Vegetables in North Eastern Region (NER)"
    enabled: false

monitor:
  interval_seconds: 300       # Check every 5 minutes
  request_timeout_seconds: 30
  max_retries: 5
  scraper_type: "html"        # "html", "browser", or "api"

notification:
  cooldown_seconds: 300       # Prevent rapid repeated alerts within 5 minutes
  email:
    enabled: true
    smtp_host: "smtp.gmail.com"
    smtp_port: 587
    use_tls: true
    sender: "${SMTP_SENDER}"
    recipient: "${SMTP_RECIPIENT}"
    app_password: "${SMTP_APP_PASSWORD}"

  whatsapp:
    enabled: false
    provider: "twilio"
    account_sid: "${TWILIO_ACCOUNT_SID}"
    auth_token: "${TWILIO_AUTH_TOKEN}"
    from_number: "${TWILIO_FROM_NUMBER}"
    to_number: "${TWILIO_TO_NUMBER}"
```

---

## 6. Configuring Notifications

### A. Email Configuration (Gmail SMTP)
To send email alerts using Gmail, you need an **App Password** (your regular Gmail password will NOT work due to Google security policies):

1. Go to your [Google Account Management](https://myaccount.google.com/).
2. Select **Security** from the left panel.
3. Under "How you sign in to Google", ensure **2-Step Verification** is turned ON.
4. Search for **App Passwords** in the search bar.
5. In "App name", enter `SIH Monitor` and click **Create**.
6. Google displays a 16-character code (e.g. `abcd efgh ijkl mnop`).
7. Copy this code into your `.env` file for `SMTP_APP_PASSWORD` (spaces are optional and stripped automatically).
8. Test your email setup:
   ```bash
   python app.py --test-email
   ```

#### Sending Email Alerts to Multiple People
You can specify multiple recipients using any of the following formats:

* **Method 1: YAML List in `config.yaml` (Recommended):**
  ```yaml
  notification:
    email:
      enabled: true
      recipients:
        - "person1@gmail.com"
        - "person2@gmail.com"
        - "teammate@college.edu"
  ```

* **Method 2: Comma-separated string in `config.yaml`:**
  ```yaml
  notification:
    email:
      enabled: true
      recipients: "person1@gmail.com, person2@gmail.com, teammate@college.edu"
  ```

* **Method 3: Environment variable in `.env`:**
  ```env
  SMTP_RECIPIENT=person1@gmail.com, person2@gmail.com, teammate@college.edu
  ```

All recipients receive the notification in a single email delivery.

### B. WhatsApp Configuration (Twilio)

WhatsApp alerting is powered by Twilio's WhatsApp API. It is completely optional. If disabled in `config.yaml`, the system runs without errors using Email.

1. Sign up for a free account at [Twilio](https://www.twilio.com/).
2. In the Twilio Console, find your **Account SID** and **Auth Token**.
3. Go to **Messaging** -> **Try it out** -> **Send a WhatsApp message** to activate the Twilio WhatsApp Sandbox.
4. Send the join code (e.g., `join <keyword>`) from your WhatsApp phone to the Twilio Sandbox number.
5. In `.env`, set:
   * `TWILIO_ACCOUNT_SID`
   * `TWILIO_AUTH_TOKEN`
   * `TWILIO_FROM_NUMBER=whatsapp:+14155238886` (your Twilio Sandbox number)
   * `TWILIO_TO_NUMBER=whatsapp:+91XXXXXXXXXX` (your WhatsApp number with country code)
6. Enable WhatsApp in `config.yaml`:
   ```yaml
   notification:
     whatsapp:
       enabled: true
   ```
7. Test your WhatsApp setup:
   ```bash
   python app.py --test-whatsapp
   ```

---

## 7. Running the Application

### Continuous Monitoring Loop
Runs the production background monitoring loop indefinitely (checks every `interval_seconds`):
```bash
python app.py
```

### Single Check Cycle (`--check-now`)
Performs exactly one check cycle across all enabled PS, updates the database, sends alerts if counts increased, and exits:
```bash
python app.py --check-now
```

### Dry Run Mode (`--dry-run`)
Fetches the real count from the portal, compares it with the database, and prints what notification WOULD be sent, without writing to the database or sending actual alerts:
```bash
python app.py --check-now --dry-run
```

### Simulated Increase Test (`--simulate-increase`)
Test how an increase alert looks without waiting for real submissions:
```bash
python app.py --check-now --dry-run --simulate-increase 5
```
Output:
```text
==================================================
DRY RUN: CHANGE DETECTED
PS: SIH26002 - Al-Based Smart Logistics and Accessibility Intelligence Platform...
Previous count: 204
Current count: 209
Increase: +5
Would send: Email -> enabled, WhatsApp -> disabled
==================================================
```

### Database Status (`--status`)
Inspect monitored counts and alert history:
```bash
python app.py --status
```

### Health Check (`--health`)
Returns JSON health status suitable for monitoring endpoints and uptime checks:
```bash
python app.py --health
```
Output:
```json
{
  "status": "healthy",
  "last_check": "2026-09-25 11:42:22",
  "monitored_ps": 2,
  "database": "C:\\Maithil\\tp\\as\\sih_monitor.db"
}
```

### Discover & List All Portal Problem Statements (`--list-ps`)
```bash
python app.py --list-ps
```

---

## 8. Automated Testing

The project includes an automated test suite (`pytest`) covering:
* Count transitions:
  * `None -> 42` = Baseline only (no alert)
  * `37 -> 42` = Alert (+5 increase)
  * `42 -> 42` = Unchanged (no alert)
  * `42 -> 40` = Decreased (warning logged, no increase alert)
  * `42 -> 43` = Alert (+1 increase)
* Duplicate alert prevention across repeated checks
* Multi-PS concurrent monitoring
* API & network retry backoff handling
* Database transactions & cooldown enforcement
* Notification failure isolation (email or whatsapp crash does not crash monitor)

Run all tests:
```bash
pytest -v
```

---

## 9. Deployment Options

### Understanding Continuous Workers vs Serverless

| Platform Type | Supported? | Explanation |
| :--- | :---: | :--- |
| **Local PC / Laptop** | ✅ Yes | Can run continuously via terminal or scheduled via Windows Task Scheduler. |
| **Linux VPS (DigitalOcean, Linode, Hetzner)** | ✅ Yes | Ideal for continuous Python daemon services using `systemd`. |
| **AWS EC2 / Lightsail** | ✅ Yes | Reliable 24/7 continuous worker. |
| **Render (Background Worker)** | ✅ Yes | Use a **Background Worker** service (not Web Service, which spins down without HTTP traffic). |
| **Railway** | ✅ Yes | Runs Docker/Python workers continuously. |
| **PythonAnywhere** | ⚠️ Partial | Web accounts do not support continuous loops without "Always-on Task" upgrade (paid). You can use Scheduled Tasks for single checks. |
| **Vercel / Netlify / AWS Lambda** | ❌ No | Serverless platforms terminate after 10–60 seconds; they cannot run continuous background monitoring loops. |

---

### Local Windows (Windows Task Scheduler)
To run the monitor automatically on Windows every 5 minutes without leaving a terminal open:

1. Open **Task Scheduler** in Windows (`taskschd.msc`).
2. Click **Create Task...**
3. On the **General** tab:
   * Name: `SIH Problem Statement Monitor`
   * Check: **Run whether user is logged on or not**
4. On the **Triggers** tab:
   * Click **New...**
   * Begin the task: **At startup** (or on a schedule)
   * Repeat task every: **5 minutes** for a duration of: **Indefinitely**
5. On the **Actions** tab:
   * Action: **Start a program**
   * Program/script: `python.exe` (or full path, e.g., `C:\Users\HP\AppData\Local\Programs\Python\Python313\python.exe`)
   * Add arguments: `app.py --check-now`
   * Start in: `C:\Maithil\tp\as`
6. Click **OK** to save.

---

### Linux / VPS (systemd Service)
To run the continuous monitor as a system service on Ubuntu/Debian:

1. Create a service file:
   ```bash
   sudo nano /etc/systemd/system/sih-monitor.service
   ```
2. Paste the following configuration:
   ```ini
   [Unit]
   Description=SIH Problem Statement Monitor
   After=network.target

   [Service]
   Type=simple
   User=ubuntu
   WorkingDirectory=/home/ubuntu/sih-monitor
   ExecStart=/home/ubuntu/sih-monitor/venv/bin/python app.py
   Restart=always
   RestartSec=30
   EnvironmentFile=/home/ubuntu/sih-monitor/.env

   [Install]
   WantedBy=multi-user.target
   ```
3. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable sih-monitor
   sudo systemctl start sih-monitor
   sudo systemctl status sih-monitor
   ```

---

## 10. Troubleshooting & FAQ

#### Q: "Email notification skipped: SMTP credentials not fully configured."
* **Solution:** Ensure you copied `.env.example` to `.env` and entered a valid Gmail address and 16-character **App Password** (not your login password).

#### Q: "Unrecognized count format" or "Table not found"
* **Solution:** Check if SIH changed the table format. Run `python app.py --list-ps` to verify table accessibility.

#### Q: "Count increased alert was not sent immediately."
* **Solution:** Check the cooldown setting in `config.yaml` (`notification.cooldown_seconds`). If an alert was sent recently, subsequent rapid increases are deferred until the cooldown window passes to avoid spam.

#### Q: Where are application logs stored?
* **Solution:** Logs are written to `logs/sih_monitor.log` (automatically rotated at 5 MB, keeping 5 backups).

---

## 11. Extending the System

### How to Add a New Notification Provider
Inherit from `NotificationService` in `notifications/`:

```python
# notifications/telegram.py
from notifications.base import NotificationService, NotificationMessage
import requests

class TelegramNotification(NotificationService):
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, message: NotificationMessage) -> bool:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": message.plain_text}
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200

    def test_connection(self) -> bool:
        url = f"https://api.telegram.org/bot{self.bot_token}/getMe"
        return requests.get(url, timeout=10).status_code == 200
```
Register it in `notifications/__init__.py` inside `build_notification_dispatcher`.

### How to Add a New SIH Data Source
Inherit from `BaseScraper` in `scraper/`:

```python
# scraper/my_source.py
from scraper.base import BaseScraper
from typing import Dict, Any

class CustomSource(BaseScraper):
    def fetch_all(self) -> Dict[str, Dict[str, Any]]:
        # Implement custom extraction logic
        return {...}
```
Register it in `scraper/__init__.py` inside `get_scraper`.
#   T P  
 