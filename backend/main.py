import os
import json
import traceback
import re
from typing import Dict, Any, Optional, List

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Body
from fastapi.middleware.cors import CORSMiddleware

from google import genai

# (Optional) kept but not used now; browser speaks agent reply
import pyttsx3  # noqa: F401
from fastapi import HTTPException


# ------------------ ENV + CLIENT ------------------

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY missing in backend/.env")

gemini = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODEL = "models/gemini-2.5-flash"


# ------------------ APP ------------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------ CONFIG ------------------

TIMEZONE_LABEL = "IST"
SECURE_LINK_BASE = "http://localhost:5173/secure"  # Option B secure page route

TOPICS = [
    "KYC/Onboarding",
    "SIP/Mandates",
    "Statements/Tax Docs",
    "Withdrawals & Timelines",
    "Account Changes/Nominee",
]

MOCK_SLOTS = [
    {"slot_id": "SLOT-101", "start": "2026-01-02 10:00 AM", "end": "10:30 AM"},
    {"slot_id": "SLOT-102", "start": "2026-01-02 11:00 AM", "end": "11:30 AM"},
    {"slot_id": "SLOT-103", "start": "2026-01-02 03:00 PM", "end": "03:30 PM"},
    {"slot_id": "SLOT-104", "start": "2026-01-02 05:00 PM", "end": "05:30 PM"},
]


# ------------------ STATE ------------------

STATE: Dict[str, Any] = {
    "disclaimer_done": False,
    "intent": None,

    # booking flow
    "topic": None,
    "day_pref": None,
    "time_pref": None,
    "offered_slots": None,
    "selected_slot": None,
    "booking_code": None,

    # reschedule/cancel
    "provided_code": None,
}

# ------------------ SECURE DETAILS STORE (Option B) ------------------
# Demo-only in-memory store; replace with DB in production
SECURE_DETAILS_STORE: Dict[str, Any] = {}
BOOKINGS: Dict[str, Any] = {}


def reset_booking_state():
    STATE["topic"] = None
    STATE["day_pref"] = None
    STATE["time_pref"] = None
    STATE["offered_slots"] = None
    STATE["selected_slot"] = None
    STATE["booking_code"] = None


def reset_reschedule_cancel():
    STATE["provided_code"] = None


# ------------------ PII GUARD ------------------

PII_PATTERNS = [
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",  # email
    r"\b(?:\+?\d[\d\s-]{8,}\d)\b",                 # phone-ish
    r"\b\d{10}\b",                                 # 10 digits
    r"\b\d{12}\b",                                 # 12 digits
    r"\baccount\b.*\b\d+\b",                       # "account 123..."
]


def contains_pii(text: str) -> bool:
    for p in PII_PATTERNS:
        if re.search(p, text, flags=re.IGNORECASE):
            return True
    return False


def extract_booking_code(text: str) -> Optional[str]:
    m = re.search(r"\bNL-[A-Z0-9]{4}\b", text.upper())
    return m.group(0) if m else None


# ------------------ HELPERS ------------------

def generate_booking_code() -> str:
    import random, string
    return "NL-" + "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(4))


def secure_link_for(code: str) -> str:
    return f"{SECURE_LINK_BASE}?code={code}"


def transcribe(audio_path: str) -> str:
    """
    Gemini multimodal transcription.
    If Gemini quota is exceeded, return empty string rather than crashing.
    """
    try:
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        resp = gemini.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "Transcribe the audio into plain text only. "
                                "Output ONLY the transcript. No commentary, no labels."
                            )
                        },
                        {
                            "inline_data": {
                                "mime_type": "audio/webm",
                                "data": audio_bytes,
                            }
                        },
                    ],
                }
            ],
        )

        text = (resp.text or "").strip()
        print("TRANSCRIPTION RAW:", repr(text))
        return text

    except Exception as e:
        print("TRANSCRIBE_FALLBACK_REASON:", repr(e))
        # Best-effort fallback: return empty string so agent asks to repeat
        return ""



def _json_fallback() -> Dict[str, Any]:
    return {"intent": "other", "topic": None, "day_preference": None, "time_preference": None}

def extract_first_json_object(text: str) -> Optional[dict]:
    """
    Pull the first {...} JSON object from text (handles ```json fences and extra words).
    Returns dict or None.
    """
    if not text:
        return None
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def local_intent_fallback(user_text: str) -> Dict[str, Any]:
    """
    Offline intent+slot parser used when Gemini quota is exceeded.

    Key behavior:
    - If user provides booking fields (topic/day/time), assume book_new unless they explicitly said cancel/reschedule/etc.
    - Prevents loops like: "Which topic?" -> "KYC" -> intent=other -> menu again.
    """
    t = (user_text or "").lower()

    # topic (best-effort)
    topic = None
    if "kyc" in t or "onboard" in t:
        topic = "KYC/Onboarding"
    elif "sip" in t or "mandate" in t:
        topic = "SIP/Mandates"
    elif "statement" in t or "tax" in t:
        topic = "Statements/Tax Docs"
    elif "withdraw" in t or "timeline" in t or "redemption" in t:
        topic = "Withdrawals & Timelines"
    elif "nominee" in t or "account change" in t or "profile" in t:
        topic = "Account Changes/Nominee"

    # day preference
    day_preference = None
    if "tomorrow" in t:
        day_preference = "tomorrow"
    elif "today" in t:
        day_preference = "today"
    else:
        for d in ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]:
            if d in t:
                day_preference = d
                break

    # time preference
    time_preference = None
    if "morning" in t:
        time_preference = "morning"
    elif "afternoon" in t:
        time_preference = "afternoon"
    elif "evening" in t or "night" in t:
        time_preference = "evening"

    # explicit intent commands
    if any(w in t for w in ["reschedule", "move my", "change my time", "change slot"]):
        intent = "reschedule"
    elif any(w in t for w in ["cancel", "call off", "delete booking"]):
        intent = "cancel"
    elif any(w in t for w in ["prepare", "what should i bring", "what to prepare"]):
        intent = "what_to_prepare"
    elif any(w in t for w in ["availability", "available", "check availability", "any slots"]):
        intent = "check_availability"
    elif any(w in t for w in ["book", "appointment", "schedule"]):
        intent = "book_new"
    else:
        intent = "other"

    # ✅ NEW RULE: if user provides booking fields, default to booking
    # (unless they explicitly asked cancel/reschedule/prepare)
    gave_booking_fields = bool(topic or day_preference or time_preference)
    if intent in ["other", "check_availability"] and gave_booking_fields:
        intent = "book_new"

    # ✅ Existing rule: if mid-booking and they provide fields, keep booking
    mid_booking = bool(STATE.get("topic") or STATE.get("day_pref") or STATE.get("time_pref"))
    if intent == "other" and mid_booking and gave_booking_fields:
        intent = "book_new"

    return {
        "intent": intent,
        "topic": topic,
        "day_preference": day_preference,
        "time_preference": time_preference,
    }


def detect_intent_and_extract(user_text: str) -> Dict[str, Any]:
    """
    Returns dict; never throws.
    - Handles ```json fenced outputs
    - Falls back to local parser if Gemini quota is hit (429)
    """
    if not user_text or not user_text.strip():
        return _json_fallback()

    prompt = f"""
Return STRICT JSON only (no markdown, no code fences).

Allowed intents:
book_new, reschedule, cancel, what_to_prepare, check_availability, other

Allowed topics (must match exactly if present):
{", ".join(TOPICS)}

Keys (always include):
intent, topic, day_preference, time_preference

User said:
{user_text}
""".strip()

    try:
        resp = gemini.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        raw = (resp.text or "").strip()
        print("INTENT RAW:", repr(raw))

        obj = extract_first_json_object(raw)
        return obj if obj else _json_fallback()

    except Exception as e:
        # If we hit quota or any API issue, keep demo working
        print("INTENT_FALLBACK_REASON:", repr(e))
        fb = local_intent_fallback(user_text)
        print("INTENT LOCAL FALLBACK:", fb)
        return fb


def mock_pick_two_slots(day_pref: str, time_pref: str) -> List[Dict[str, str]]:
    tp = (time_pref or "").lower()

    if "even" in tp or "5" in tp or "6" in tp:
        candidates = [MOCK_SLOTS[3], MOCK_SLOTS[2], MOCK_SLOTS[1]]
    elif "after" in tp or "3" in tp or "4" in tp:
        candidates = [MOCK_SLOTS[2], MOCK_SLOTS[1], MOCK_SLOTS[3]]
    else:
        candidates = [MOCK_SLOTS[0], MOCK_SLOTS[1], MOCK_SLOTS[2]]

    return candidates[:2]


def waitlist_flow_reply(topic: str, day_pref: str, time_pref: str) -> str:
    code = STATE.get("booking_code") or generate_booking_code()
    STATE["booking_code"] = code
    link = secure_link_for(code)

    return (
        "I don’t see a matching slot right now. "
        f"I’ve placed you on a waitlist for {topic}. "
        f"Your booking code is {code}. "
        f"Please use this secure link to share contact details so we can notify you: {link}."
    )


PREP_GUIDES = {
    "KYC/Onboarding": [
        "Have your PAN and address proof handy (as applicable).",
        "Be ready to confirm your onboarding status and any KYC error message you saw.",
    ],
    "SIP/Mandates": [
        "Know your bank name and mandate status (created/pending/failed).",
        "Have approximate SIP amount and frequency you’re trying to set up.",
    ],
    "Statements/Tax Docs": [
        "Mention which period you need (FY year range).",
        "Clarify whether you need statement, capital gains, or tax certificate.",
    ],
    "Withdrawals & Timelines": [
        "Share the date you requested withdrawal and current status.",
        "Be ready to confirm the expected timeline you were told (if any).",
    ],
    "Account Changes/Nominee": [
        "Know what change you want: address, bank, nominee, or other profile detail.",
        "Be ready to confirm whether you already attempted the change in-app.",
    ],
}


# ------------------ AGENT LOGIC ------------------

def next_agent_reply(user_text: str) -> str:
    user_text = (user_text or "").strip()
    if not user_text:
        return "Sorry, I didn’t catch that. Please repeat."

    if contains_pii(user_text):
        code = STATE.get("booking_code") or "NL-XXXX"
        link = secure_link_for(code)
        return (
            "For security, please don’t share personal details on this call. "
            f"Use this secure link to add contact details: {link}. "
            "Now, what topic is this about?"
        )

    if not STATE["disclaimer_done"]:
        STATE["disclaimer_done"] = True
        return (
            "Hi — this is the Advisor Appointment Scheduler. "
            "This call is for informational support only and not investment advice. "
            "Would you like to book a new slot, reschedule, cancel, check availability, or ask what to prepare?"
        )

    lower = user_text.lower()
    if any(k in lower for k in ["buy", "sell", "invest", "stock", "mutual fund", "recommend"]):
        return (
            "I can’t provide investment advice or recommendations. "
            "I can help with account processes or book an informational advisor session. "
            "Which topic is this for: KYC/Onboarding, SIP/Mandates, Statements/Tax Docs, Withdrawals & Timelines, or Account Changes/Nominee?"
        )

    info = detect_intent_and_extract(user_text)
    intent = (info.get("intent") or "other").strip()

    # ✅ If booking has started, NEVER leave booking flow
    if STATE.get("offered_slots") or STATE.get("topic"):
        intent = "book_new"

    STATE["intent"] = intent


    # Cancel
    if intent == "cancel":
        if not STATE["provided_code"]:
            code = extract_booking_code(user_text)
            if code:
                STATE["provided_code"] = code
            else:
                return "Sure. Please tell me your booking code, for example NL-A742."
        code = STATE["provided_code"]
        reset_booking_state()
        reset_reschedule_cancel()
        return f"Done. I’ve noted a cancellation request for booking code {code}."

    # Reschedule
    if intent == "reschedule":
        if not STATE["provided_code"]:
            code = extract_booking_code(user_text)
            if code:
                STATE["provided_code"] = code
                reset_booking_state()
                return (
                    f"Got it. Booking code {code}. "
                    f"What topic is this for, and what day and time preference in {TIMEZONE_LABEL}?"
                )
            else:
                return "Sure. Please tell me your booking code, for example NL-A742."
        intent = "book_new"
        STATE["intent"] = "book_new"

    # What to prepare
    if intent == "what_to_prepare":
        topic = info.get("topic")
        if topic in TOPICS:
            tips = PREP_GUIDES.get(topic, [])
            tip_text = " ".join([f"{i+1}. {t}" for i, t in enumerate(tips)]) if tips else ""
            return f"For {topic}, here’s what to prepare: {tip_text}"
        return "Sure — which topic: KYC/Onboarding, SIP/Mandates, Statements/Tax Docs, Withdrawals & Timelines, or Account Changes/Nominee?"

    # Check availability
    if intent == "check_availability":
        topic = info.get("topic")
        day_pref = info.get("day_preference")
        time_pref = info.get("time_preference")

        if topic not in TOPICS:
            return "Which topic is this for: KYC/Onboarding, SIP/Mandates, Statements/Tax Docs, Withdrawals & Timelines, or Account Changes/Nominee?"
        if not day_pref:
            return "What day should I check for? For example tomorrow or Friday."
        if not time_pref:
            return f"What time preference in {TIMEZONE_LABEL}? Morning, afternoon, or evening?"

        slots = mock_pick_two_slots(day_pref, time_pref)
        return (
            f"For {topic}, I see two options in {TIMEZONE_LABEL}. "
            f"Option 1: {slots[0]['start']} {TIMEZONE_LABEL}. "
            f"Option 2: {slots[1]['start']} {TIMEZONE_LABEL}."
        )

    # Default to book_new if user asks appointment
    if intent != "book_new":
        if "book" in lower or "appointment" in lower or "slot" in lower:
            intent = "book_new"
            STATE["intent"] = "book_new"
        else:
            return "I can help you book, reschedule, cancel, check availability, or tell you what to prepare. What would you like to do?"

    # ---- BOOK NEW FLOW ----
    if not STATE["topic"]:
        topic = info.get("topic")
        if topic in TOPICS:
            STATE["topic"] = topic
        else:
            return "Which topic is this for: KYC/Onboarding, SIP/Mandates, Statements/Tax Docs, Withdrawals & Timelines, or Account Changes/Nominee?"

    if not STATE["day_pref"]:
        day_pref = info.get("day_preference")
        if day_pref:
            STATE["day_pref"] = day_pref
        else:
            return "What day works best for you? For example tomorrow, Friday, or next week."

    if not STATE["time_pref"]:
        time_pref = info.get("time_preference")
        if time_pref:
            STATE["time_pref"] = time_pref
        else:
            return f"Do you prefer morning, afternoon, or evening {TIMEZONE_LABEL}?"

    if not STATE["offered_slots"]:
        slots = mock_pick_two_slots(STATE["day_pref"], STATE["time_pref"])
        if not slots or len(slots) < 2:
            return waitlist_flow_reply(STATE["topic"], STATE["day_pref"], STATE["time_pref"])

        STATE["offered_slots"] = slots
        return (
            f"I have two options in {TIMEZONE_LABEL}. "
            f"Option 1: {slots[0]['start']} {TIMEZONE_LABEL}. "
            f"Option 2: {slots[1]['start']} {TIMEZONE_LABEL}. "
            "Which option do you prefer, 1 or 2?"
        )

    if not STATE["selected_slot"]:
        if "1" in lower or "one" in lower:
            STATE["selected_slot"] = STATE["offered_slots"][0]
        elif "2" in lower or "two" in lower:
            STATE["selected_slot"] = STATE["offered_slots"][1]
        else:
            return "Please say option 1 or option 2."

        slot = STATE["selected_slot"]
        return (
            f"Just to confirm in {TIMEZONE_LABEL}: "
            f"{STATE['topic']} on {slot['start']} {TIMEZONE_LABEL}. "
            "Is that correct? Say yes or no."
        )

    if not STATE["booking_code"]:
        if "yes" in lower:
            code = generate_booking_code()
            STATE["booking_code"] = code
            slot = STATE["selected_slot"]
            link = secure_link_for(code)

            BOOKINGS[code] = {
                "topic": STATE["topic"],
                "slot": slot,
                "timezone": TIMEZONE_LABEL,
            }
            print("BOOKING CREATED:", BOOKINGS[code])


            return (
                f"Great. Your booking code is {code}. "
                f"Your tentative slot is {slot['start']} {TIMEZONE_LABEL} for {STATE['topic']}. "
                "For security, I can’t collect personal details on this call. "
                f"Please use this secure link to finish details: {link}."
            )
        else:
            STATE["selected_slot"] = None
            return "No problem. Do you prefer option 1 or option 2?"

    return "All set. Do you need anything else?"


# ------------------ API ------------------

@app.post("/api/voice-turn")
async def voice_turn(audio: UploadFile = File(...)):
    try:
        os.makedirs("tmp", exist_ok=True)
        in_path = os.path.join("tmp", audio.filename)

        with open(in_path, "wb") as f:
            f.write(await audio.read())

        transcript = transcribe(in_path)
        reply_text = next_agent_reply(transcript)

        return {"transcript": transcript, "reply_text": reply_text}

    except Exception as e:
        print("VOICE_TURN_ERROR:", repr(e))
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/text-turn")
async def text_turn(payload: Dict[str, Any] = Body(...)):
    user_text = (payload.get("text") or "").strip()
    reply_text = next_agent_reply(user_text)
    return {
        "transcript": user_text,
        "reply_text": reply_text,
    }

@app.post("/api/secure-details")
async def secure_details(payload: Dict[str, Any] = Body(...)):
    booking_code = payload.get("booking_code")
    email = payload.get("email")
    phone = payload.get("phone")
    notes = payload.get("notes")

    if not booking_code or not email:
        return {"error": "booking_code and email are required"}

    # Store securely (demo: in-memory)
    SECURE_DETAILS_STORE[booking_code] = {
        "email": email,
        "phone": phone,
        "notes": notes,
    }

    # Use current STATE if it matches this booking code (demo assumption)
    booking = BOOKINGS.get(booking_code)
    if not booking:
        return {"error": f"Unknown booking_code: {booking_code}. Please use the code provided by the agent."}

    topic = booking.get("topic")
    slot = booking.get("slot")
    timezone = booking.get("timezone")

    # MCP-ready payloads (these are what n8n/MCP would consume)
    mcp_calendar_hold = {
        "action": "calendar.create_hold",
        "title": f"Advisor Q&A — {topic} — {booking_code}",
        "start": slot.get("start"),
        "timezone": TIMEZONE_LABEL,
        "status": "tentative",
    }

    mcp_notes_append = {
        "action": "notes.append",
        "doc": "Advisor Pre-Bookings",
        "entry": {
            "date": slot.get("start"),
            "topic": topic,
            "slot_id": slot.get("slot_id"),
            "code": booking_code,
            "contact_email": email,
        },
    }

    mcp_email_draft = {
        "action": "email.create_draft",
        "approval_required": True,
        "to": "advisor-team@example.com",
        "subject": f"Pre-booking request — {topic} — {booking_code}",
        "body": (
            f"Hi Advisor Team,\n\n"
            f"A caller has tentatively booked an advisor slot.\n\n"
            f"Booking Code: {booking_code}\n"
            f"Topic: {topic}\n"
            f"Slot (IST): {slot.get('start')}\n"
            f"Caller Email: {email}\n"
            f"Caller Phone: {phone or 'Not provided'}\n"
            f"Notes: {notes or '—'}\n\n"
            f"Please review and confirm.\n"
        ),
    }

    print("MCP_CALENDAR_HOLD:", mcp_calendar_hold)
    print("MCP_NOTES_APPEND:", mcp_notes_append)
    print("MCP_EMAIL_DRAFT:", mcp_email_draft)

    return {
        "ok": True,
        "mcp": {
            "calendar_hold": mcp_calendar_hold,
            "notes_append": mcp_notes_append,
            "email_draft": mcp_email_draft,
        }
    }



