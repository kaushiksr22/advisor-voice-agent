# Advisor Voice Agent (Local Demo)

A lightweight **voice + text appointment scheduler** demo that:
- collects intent + booking details through a conversational flow
- hands off PII to a **secure link page** (Option B) instead of collecting it in the call
- triggers **real “MCP-style” actions** directly (no n8n):
  - Google Sheets: append pre-booking row
  - Google Calendar: create tentative hold
  - Gmail: create email draft for advisor team

> Designed for **screenshots + end-to-end demo recording**.

---

## What you can demo end-to-end

1) User says “Book an appointment”  
2) Agent asks topic → day → time  
3) Agent offers 2 slots  
4) User confirms slot → agent returns **booking code + secure link**  
5) User opens secure link and submits email/phone/notes  
6) Backend performs:
   - ✅ Sheets append
   - ✅ Calendar hold created
   - ✅ Gmail draft created
   - ✅ returns MCP JSON payloads for screenshots

---

## Repo structure (typical)


---

## Prerequisites

- Node 18+
- Python 3.9+ (3.10+ recommended)
- A Google Cloud Project with APIs enabled:
  - Google Sheets API
  - Google Calendar API
  - Gmail API

---

## Setup

### 1) Frontend (Vite)
From repo root:
```bash
cd frontend
npm install
npm run dev

cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

GEMINI_API_KEY=YOUR_KEY
SHEETS_SPREADSHEET_ID=YOUR_SHEET_ID

Google OAuth (one-time)
Files that should NOT be committed

Add this to .gitignore (repo root or backend):

backend/credentials.json
backend/token.json
backend/.env

Create credentials.json

Google Cloud Console → APIs & Services → Credentials → Create Credentials → OAuth client ID
Choose Desktop App and download → place it at:

backend/credentials.json

Generate token.json once

From backend/:

rm -f token.json
python auth_once.py


If it opens a browser, accept permissions.
If it does not open a browser but prints “token created”, that’s fine too.

Verify:

ls -la token.json

Smoke test endpoints (Swagger)

Open http://127.0.0.1:8000/docs
 and run:

1) Sheets append test

POST /api/test-sheets-append
✅ Should append a new row in your spreadsheet.

2) Calendar hold test

POST /api/test-calendar-hold
✅ Should return an eventId + htmlLink
Verify in Google Calendar.

3) Gmail draft test

POST /api/test-gmail-draft
✅ Should return a draftId
Verify in Gmail → Drafts.

Demo flow (recommended)
Text demo (fast + reliable)

Open frontend at http://localhost:5173

Use text input (or whatever your UI provides) and say:

“I want to book an appointment”

“KYC onboarding”

“tomorrow”

“morning”

“option 1”

“yes”

Copy the booking code and click the secure link

Enter email/phone/notes and submit

Backend should log:

SHEETS_APPEND_OK

CALENDAR_OK

GMAIL_DRAFT_OK
…and print MCP JSON payloads.

Voice demo (optional)

Voice uses Gemini multimodal transcription. If you hit quota, the demo may degrade.
Text demo is best for recordings.

What is “MCP style” here?

Instead of wiring n8n, we produce tool-call-like JSON payloads and also execute the real actions:

calendar.create_hold

notes.append (represented via Sheets row in this demo)

email.create_draft

You get:

Real calendar event created

Real Gmail draft created

Row appended in Sheets

JSON payload returned for screenshots

Troubleshooting
“Access blocked / app not verified”

In OAuth consent screen:

Publishing status = Testing is okay

Add your Google account as a Test user

Try auth again (remove token.json and rerun auth_once.py)

It keeps asking to authorize every time

Likely token not being loaded/refreshing. Ensure:

token.json exists in backend/

your auth helper returns early when creds.valid

Sheets error: “Unable to parse range”

Make sure the sheet tab name matches exactly. Example:

Tab name: Advisor Pre-Bookings

Range: 'Advisor Pre-Bookings'!A:G

Python warnings about LibreSSL / 3.9 EOL

These are warnings; the demo can still run. For stability, use Python 3.10+.

Security notes (for judges)

The call flow does not collect PII (email/phone) in conversation.

PII is collected only via a secure details page (Option B).

OAuth tokens and credentials are not committed.

This demo uses in-memory storage for speed; production would use a secure DB + secrets manager.

License

MIT (or replace with your preferred license)


If you want, paste your **actual repo structure** (just the top-level `ls`) and I’ll tweak the README paths + commands so it matches your exact layout.

When you’re ready, reply **A** and I’ll give you the **final demo script** (exact words + what to click + what to show in terminal).
::contentReference[oaicite:0]{index=0}
