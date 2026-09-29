import hashlib
import hmac
import mimetypes
import os
import random
import re
import secrets
import smtplib
import time

from datetime import timedelta, timezone, datetime
from email.message import EmailMessage

from flask import Flask, request, jsonify, send_from_directory, session
from flask_migrate import Migrate
from sqlalchemy import text

from models import (
    db,
    User,
    VerificationCode,
    LocationShare,
    Party,
    PartyMember,
    PARTY_STATUS_ACTIVE,
    PARTY_STATUS_ENDED,
    PARTY_ROLE_HOST,
    PARTY_ROLE_MEMBER,
    CHECK_IN_GOOD,
    CHECK_IN_HEADING_HOME,
    CHECK_IN_NEED_HELP,
)

from party import PartyTracker, FRESH_SECONDS, is_usable

from calculations import (
    CLUSTER_DISTANCE,
    gps_to_xy,
    distance_from_party,
)

from event_sources import normalize_destination


# ==================================================
# FOLDERS
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(
    os.path.join(BASE_DIR, "..", "..")
)


def load_local_env_file():

    env_path = os.path.join(PROJECT_DIR, ".env")

    if not os.path.exists(env_path):
        return

    with open(env_path, encoding="utf-8") as env_file:

        for line in env_file:

            stripped = line.strip()

            if (
                not stripped
                or stripped.startswith("#")
                or "=" not in stripped
            ):
                continue

            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            os.environ.setdefault(key, value)


load_local_env_file()

# Windows can map .js to text/plain in the registry, and browsers
# refuse to run a service worker (sw.js) served that way.
mimetypes.add_type("application/javascript", ".js")

FRONTEND_DIR = os.path.abspath(
    os.path.join(BASE_DIR, "..", "..", "Frontend")
)


# ==================================================
# FLASK APP
# ==================================================

app = Flask(__name__)

def env_flag(name):

    return os.environ.get(name, "").lower() == "true"


def running_in_production():

    return (
        os.environ.get("FLASK_ENV") == "production"
        or os.environ.get("FRIENDSNME_ENV") == "production"
        or bool(os.environ.get("RAILWAY_ENVIRONMENT"))
    )


PRODUCTION_MODE = running_in_production()

# Debug mode turns on the Werkzeug debugger and /api/debug/users.
# Only enable it on your own machine: FRIENDSNME_DEBUG=true
DEBUG_MODE = env_flag("FRIENDSNME_DEBUG") and not PRODUCTION_MODE

# The secret signs login cookies. A hard-coded fallback would let
# anyone who has read this file forge a session. In production this
# must be configured; local dev gets a temporary one for convenience.
app.secret_key = os.environ.get("SESSION_SECRET")

PRODUCTION_REQUIRED_ENV = [
    "SESSION_SECRET",
    "DATABASE_URL",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_FROM",
    "SMTP_USER",
    "SMTP_PASS",
    "SMTP_SECURE",
]

if PRODUCTION_MODE:

    missing = [
        name
        for name in PRODUCTION_REQUIRED_ENV
        if not os.environ.get(name)
    ]

    if missing:
        raise RuntimeError(
            "Missing required production environment variables: "
            + ", ".join(missing)
        )

if not app.secret_key:

    app.secret_key = secrets.token_hex(32)

    print(
        "WARNING: SESSION_SECRET is not set. Using a random secret; "
        "everyone will be signed out when the server restarts.",
        flush=True
    )

app.permanent_session_lifetime = timedelta(days=30)
app.config["SESSION_COOKIE_SECURE"] = PRODUCTION_MODE
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


# ==================================================
# PARTY STATE
# ==================================================

# Only geofence snapshots live in server memory. Party and
# membership records are database-backed and survive restarts.
party_tracker = PartyTracker()


# ==================================================
# DATABASE
# ==================================================

DATABASE_PATH = os.path.join(BASE_DIR, "friendsnme.db")

def database_uri():

    configured_url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("FRIENDSNME_DATABASE_URI")
    )

    if configured_url:

        # Some platforms expose postgres://, while SQLAlchemy 2
        # expects postgresql://.
        if configured_url.startswith("postgres://"):
            configured_url = (
                "postgresql://"
                + configured_url[len("postgres://"):]
            )

        return configured_url

    return f"sqlite:///{DATABASE_PATH}"


DATABASE_URI = database_uri()


def database_log_label(uri):

    if uri.startswith("sqlite:///"):
        return uri

    if "://" not in uri:
        return "configured"

    scheme, rest = uri.split("://", 1)
    host_part = rest.split("@", 1)[-1]

    return f"{scheme}://{host_part}"

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
migrate = Migrate(app, db, compare_type=True)

print("\n================================")
print("DATABASE CONFIGURED")
print("================================")

print("Database:", database_log_label(DATABASE_URI))

if PRODUCTION_MODE:
    print("Production mode: migrations must be run with flask db upgrade.")


# ==================================================
# AUTH SETTINGS
# ==================================================

CODE_TTL_MINUTES = 10
MAX_CODES_PER_HOUR = 5
MIN_RESEND_SECONDS = 60
MAX_CODE_ATTEMPTS = 5

TEMPLE_EMAIL_RE = re.compile(
    r"^[^\s@]+@temple\.edu$",
    re.IGNORECASE
)

PARTY_CODE_RE = re.compile(r"^[A-Z]{2,8}-\d{4}$")
PARTY_CODE_WORDS = [
    "OWL",
    "BELL",
    "CHERRY",
    "DIAMOND",
    "NORTH",
    "LIAC",
]
PARTY_DURATION_HOURS = 12
MAX_JOIN_ATTEMPTS = 10
JOIN_ATTEMPT_WINDOW_SECONDS = 5 * 60

CHECK_IN_STATUSES = {
    CHECK_IN_GOOD: "I'm Good",
    CHECK_IN_HEADING_HOME: "Heading Home",
    CHECK_IN_NEED_HELP: "Need Help",
}


# ==================================================
# HELPERS
# ==================================================

def now_utc():
    return datetime.now(timezone.utc)


def iso_now():
    return now_utc().isoformat()


def as_utc(value):

    # SQLite drops timezone information when reading
    # DateTime values. They were stored as UTC.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value


def normalize_email(email):

    return str(email or "").strip().lower()


def normalize_username(username):

    return " ".join(
        str(username or "").strip().split()
    )


def is_temple_email(email):

    return bool(
        TEMPLE_EMAIL_RE.match(
            normalize_email(email)
        )
    )


def hmac_value(value):

    return hmac.new(
        app.secret_key.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def find_user_by_email(email):

    return User.query.filter_by(
        email=email
    ).first()


def find_user_by_id(user_id):

    return db.session.get(
        User,
        user_id
    )


def find_user_by_username(username):

    return User.query.filter_by(
        username_lower=username.lower()
    ).first()


def require_user():

    user_id = session.get("user_id")

    if not user_id:
        return None

    return find_user_by_id(user_id)


def json_error(message, status):

    return jsonify({
        "error": message
    }), status


def clean_required_text(value, field_name, max_length):

    text = " ".join(
        str(value or "").strip().split()
    )

    if not text:
        raise ValueError(f"{field_name} is required.")

    if len(text) > max_length:
        raise ValueError(
            f"{field_name} must be {max_length} characters or fewer."
        )

    return text


def normalize_party_code(code):

    text = str(code or "").strip().upper()
    text = re.sub(r"\s+", "", text)

    # Let students type OWL4827 and normalize it to OWL-4827.
    if "-" not in text and len(text) > 4:
        text = f"{text[:-4]}-{text[-4:]}"

    return text


def generate_join_code():

    rng = random.SystemRandom()

    for _ in range(100):

        code = (
            f"{rng.choice(PARTY_CODE_WORDS)}-"
            f"{rng.randint(1000, 9999)}"
        )

        if not Party.query.filter_by(join_code=code).first():
            return code

    raise RuntimeError("Could not generate a unique party code.")


def check_join_rate_limit():

    current = time.time()

    attempts = [
        attempt
        for attempt in session.get("party_join_attempts", [])
        if current - float(attempt) < JOIN_ATTEMPT_WINDOW_SECONDS
    ]

    if len(attempts) >= MAX_JOIN_ATTEMPTS:
        session["party_join_attempts"] = attempts
        return False

    attempts.append(current)
    session["party_join_attempts"] = attempts
    session.modified = True

    return True


def party_is_expired(party, current):

    return (
        party.status == PARTY_STATUS_ACTIVE
        and as_utc(party.expires_at) <= current
    )


def mark_party_ended(party, current):

    party.status = PARTY_STATUS_ENDED
    party.ended_at = current

    PartyMember.query.filter_by(
        party_id=party.id
    ).update({
        PartyMember.location_sharing_enabled: False
    })

    party_tracker.forget(party.id)


def expire_old_parties(current=None):

    current = current or now_utc()
    changed = False

    active_parties = Party.query.filter_by(
        status=PARTY_STATUS_ACTIVE
    ).all()

    for party in active_parties:

        if party_is_expired(party, current):
            mark_party_ended(party, current)
            changed = True

    if changed:
        db.session.commit()


def active_member_clause():

    return (
        PartyMember.left_at.is_(None),
        PartyMember.removed_at.is_(None),
    )


def current_party_membership(user):

    current = now_utc()
    expire_old_parties(current)

    return (
        PartyMember.query
        .join(Party, PartyMember.party_id == Party.id)
        .filter(
            PartyMember.user_id == user.id,
            Party.status == PARTY_STATUS_ACTIVE,
            Party.expires_at > current,
            *active_member_clause()
        )
        .order_by(PartyMember.joined_at.desc())
        .first()
    )


def get_member(party_id, user_id):

    return PartyMember.query.filter_by(
        party_id=party_id,
        user_id=user_id
    ).first()


def require_active_party_member(party_id):

    user = require_user()

    if not user:
        return None, None, None, json_error(
            "You must be signed in.",
            401
        )

    current = now_utc()
    expire_old_parties(current)

    party = db.session.get(Party, party_id)

    if not party:
        return user, None, None, json_error(
            "Party not found.",
            404
        )

    if party.status != PARTY_STATUS_ACTIVE:
        return user, party, None, json_error(
            "That party has ended.",
            409
        )

    if as_utc(party.expires_at) <= current:
        expire_old_parties(current)
        return user, party, None, json_error(
            "That party has expired.",
            409
        )

    member = get_member(
        party.id,
        user.id
    )

    if (
        not member
        or member.left_at is not None
        or member.removed_at is not None
    ):
        return user, party, member, json_error(
            "You are not a current member of this party.",
            403
        )

    return user, party, member, None


def require_party_host(party_id):

    user, party, member, error = require_active_party_member(
        party_id
    )

    if error:
        return user, party, member, error

    if member.role != PARTY_ROLE_HOST:
        return user, party, member, json_error(
            "Only the host can do that.",
            403
        )

    return user, party, member, None


# ==================================================
# EMAIL VERIFICATION
# ==================================================

def send_verification_email(email, code):

    require_email_delivery = (
        PRODUCTION_MODE
        or env_flag("FRIENDSNME_REQUIRE_EMAIL_DELIVERY")
    )

    should_log = (
        env_flag("AUTH_LOG_VERIFICATION_CODES")
        and not PRODUCTION_MODE
        and not require_email_delivery
    )

    # During development, print verification code
    # directly into terminal if SMTP is not configured.
    if (
        should_log
        or (
            not require_email_delivery
            and not os.environ.get("SMTP_HOST")
        )
    ):

        print(
            f"[AUTH] Verification code for {email}: {code}",
            flush=True
        )

        return

    smtp_host = os.environ.get("SMTP_HOST")
    smtp_from = os.environ.get("SMTP_FROM")

    if not smtp_host or not smtp_from:

        raise RuntimeError(
            "Email delivery is not configured. Set SMTP_HOST and SMTP_FROM."
        )

    smtp_port = int(
        os.environ.get(
            "SMTP_PORT",
            "587"
        )
    )

    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")

    smtp_secure = (
        os.environ.get(
            "SMTP_SECURE",
            ""
        ).lower() == "true"
    )

    message = EmailMessage()

    message["From"] = smtp_from
    message["To"] = email
    message["Subject"] = "Your FriendsNMe verification code"

    message.set_content(
        f"Your FriendsNMe verification code is {code}. "
        "It expires in 10 minutes."
    )

    if smtp_secure:

        server = smtplib.SMTP_SSL(
            smtp_host,
            smtp_port,
            timeout=20
        )

    else:

        server = smtplib.SMTP(
            smtp_host,
            smtp_port,
            timeout=20
        )

    with server:

        if not smtp_secure:
            server.starttls()

        if smtp_user and smtp_pass:

            server.login(
                smtp_user,
                smtp_pass
            )

        server.send_message(message)


def latest_usable_code(email):

    current = now_utc()

    return (
        VerificationCode.query
        .filter(
            VerificationCode.email == email,
            VerificationCode.used_at.is_(None),
            VerificationCode.expires_at > current,
        )
        .order_by(
            VerificationCode.created_at.desc()
        )
        .first()
    )


# ==================================================
# WEBSITE
# ==================================================

@app.route("/")
def home():

    return send_from_directory(
        FRONTEND_DIR,
        "index.html"
    )


@app.route("/join")
def join_page():

    return send_from_directory(
        FRONTEND_DIR,
        "index.html"
    )


# ==================================================
# HEALTH CHECK
# ==================================================

@app.get("/api/health")
def health_check():

    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "database": "unavailable"
        }), 503

    return jsonify({
        "status": "ok",
        "database": "ok"
    })


# ==================================================
# AUTH SESSION
# ==================================================

@app.get("/api/auth/session")
def auth_session():

    user = require_user()

    if not user:

        return jsonify({
            "authenticated": False
        }), 401

    return jsonify({
        "authenticated": True,
        "user": user.to_public_dict()
    })


# ==================================================
# REQUEST VERIFICATION CODE
# ==================================================

@app.post("/api/auth/request-code")
def request_code():

    body = request.get_json(
        silent=True
    ) or {}

    email = normalize_email(
        body.get("email")
    )

    if not is_temple_email(email):

        return json_error(
            "Only Temple University email addresses can access this website.",
            400
        )

    current = now_utc()

    recent_codes = (
        VerificationCode.query
        .filter(
            VerificationCode.email == email,
            VerificationCode.created_at
            >= current - timedelta(hours=1),
        )
        .order_by(
            VerificationCode.created_at.desc()
        )
        .all()
    )

    if len(recent_codes) >= MAX_CODES_PER_HOUR:

        return json_error(
            "Too many verification codes requested. Try again later.",
            429
        )

    if recent_codes:

        latest_created = as_utc(
            recent_codes[0].created_at
        )

        if (
            current - latest_created
        ).total_seconds() < MIN_RESEND_SECONDS:

            return json_error(
                "Please wait before requesting another verification code.",
                429
            )

    code = str(
        random.SystemRandom().randint(
            100000,
            999999
        )
    )

    new_code = VerificationCode(
        email=email,

        code_hash=hmac_value(
            f"{email}:{code}"
        ),

        expires_at=(
            current
            + timedelta(
                minutes=CODE_TTL_MINUTES
            )
        ),
    )

    db.session.add(new_code)
    db.session.commit()

    try:

        send_verification_email(
            email,
            code
        )

    except RuntimeError as error:

        return json_error(
            str(error),
            503
        )

    return jsonify({
        "ok": True,
        "email": email,
        "expiresInSeconds":
            CODE_TTL_MINUTES * 60
    })


# ==================================================
# VERIFY CODE
# ==================================================

@app.post("/api/auth/verify-code")
def verify_code():

    body = request.get_json(
        silent=True
    ) or {}

    email = normalize_email(
        body.get("email")
    )

    code = str(
        body.get("code") or ""
    ).strip()

    if not is_temple_email(email):

        return json_error(
            "Only Temple University email addresses can access this website.",
            400
        )

    if not re.match(
        r"^\d{6}$",
        code
    ):

        return json_error(
            "Enter the 6-digit verification code.",
            400
        )

    code_entry = latest_usable_code(
        email
    )

    if (
        not code_entry
        or code_entry.attempts
        >= MAX_CODE_ATTEMPTS
    ):

        return json_error(
            "That verification code is invalid or expired.",
            400
        )

    submitted_hash = hmac_value(
        f"{email}:{code}"
    )

    if not secrets.compare_digest(
        submitted_hash,
        code_entry.code_hash
    ):

        code_entry.attempts += 1

        db.session.commit()

        return json_error(
            "That verification code is invalid or expired.",
            400
        )

    code_entry.used_at = now_utc()

    existing_user = find_user_by_email(
        email
    )

    db.session.commit()

    session.permanent = True

    # Existing account
    if existing_user:

        session["user_id"] = existing_user.id

        session.pop(
            "verified_email",
            None
        )

        print(
            "USER LOGGED IN:",
            existing_user.username
        )

        return jsonify({
            "ok": True,
            "needsUsername": False,
            "user":
                existing_user.to_public_dict()
        })

    # New account
    session["verified_email"] = email

    return jsonify({
        "ok": True,
        "needsUsername": True
    })


# ==================================================
# COMPLETE SIGNUP
# ==================================================

@app.post("/api/auth/complete-signup")
def complete_signup():

    email = session.get(
        "verified_email"
    )

    if not email:

        return json_error(
            "Your signup session expired. Verify your email again.",
            401
        )

    body = request.get_json(
        silent=True
    ) or {}

    username = normalize_username(
        body.get("username")
    )

    if not username:

        return json_error(
            "Username cannot be empty.",
            400
        )

    if len(username) > 32:

        return json_error(
            "Username must be 32 characters or fewer.",
            400
        )

    if find_user_by_email(email):

        return json_error(
            "An account already exists for this Temple email.",
            409
        )

    if find_user_by_username(username):

        return json_error(
            "That username is already taken.",
            409
        )

    # CREATE DATABASE USER
    user = User(
        email=email,
        username=username,
        username_lower=username.lower()
    )

    db.session.add(user)
    db.session.commit()

    if DEBUG_MODE:

        print("\n================================")
        print("NEW USER SAVED TO DATABASE")
        print("================================")

        print("ID:", user.id)
        print("USERNAME:", user.username)
        print("EMAIL:", user.email)

    session.permanent = True
    session["user_id"] = user.id

    session.pop(
        "verified_email",
        None
    )

    return jsonify({
        "ok": True,
        "user": user.to_public_dict()
    }), 201


# ==================================================
# LOGOUT
# ==================================================

@app.post("/api/auth/logout")
def logout():

    session.clear()

    return jsonify({
        "ok": True
    })


# ==================================================
# LOCATION HELPERS
# ==================================================

def location_age_seconds(location, current):

    try:
        updated = datetime.fromisoformat(
            location["updatedAt"]
        )
    except (KeyError, TypeError, ValueError):
        return None

    return (current - as_utc(updated)).total_seconds()


def has_location(user):

    loc = user.last_location

    return (
        isinstance(loc, dict)
        and "latitude" in loc
        and "longitude" in loc
    )


def active_party_member_rows(party_id):

    rows = (
        db.session.query(PartyMember, User)
        .join(User, PartyMember.user_id == User.id)
        .filter(
            PartyMember.party_id == party_id,
            *active_member_clause()
        )
        .all()
    )

    return sorted(
        rows,
        key=lambda row: (
            0 if row[0].role == PARTY_ROLE_HOST else 1,
            row[1].username_lower
        )
    )


def left_party_membership(user):

    current = now_utc()
    expire_old_parties(current)

    if current_party_membership(user):
        return None

    return (
        PartyMember.query
        .join(Party, PartyMember.party_id == Party.id)
        .filter(
            PartyMember.user_id == user.id,
            PartyMember.left_at.is_not(None),
            PartyMember.removed_at.is_(None),
            Party.status == PARTY_STATUS_ACTIVE,
            Party.expires_at > current,
        )
        .order_by(PartyMember.left_at.desc())
        .first()
    )


def party_summary(party):

    return {
        "id": party.id,
        "name": party.name,
        "joinCode": party.join_code,
        "status": party.status,
        "createdAt": as_utc(party.created_at).isoformat(),
        "expiresAt": as_utc(party.expires_at).isoformat(),
        "endedAt": (
            as_utc(party.ended_at).isoformat()
            if party.ended_at
            else None
        ),
        "destination": party_destination(party),
    }


def party_destination(party):

    if not any([
        party.destination_name,
        party.destination_address,
        party.destination_latitude is not None,
        party.destination_longitude is not None,
        party.destination_start_time,
        party.destination_source_url,
    ]):
        return None

    source = party.destination_source or "manual"

    return {
        "name": party.destination_name,
        "address": party.destination_address,
        "latitude": party.destination_latitude,
        "longitude": party.destination_longitude,
        "startTime": party.destination_start_time,
        "source": source,
        "sourceLabel": (
            "TU Parties"
            if source == "tuparties"
            else "Manual"
        ),
        "sourceUrl": party.destination_source_url,
    }


def party_location_inputs(rows, current):

    locations = []

    for member, member_user in rows:

        if not member.location_sharing_enabled:
            continue

        if not has_location(member_user):
            continue

        age = location_age_seconds(
            member_user.last_location,
            current
        )

        if age is None:
            continue

        loc = member_user.last_location

        try:
            latitude = float(loc["latitude"])
            longitude = float(loc["longitude"])
        except (TypeError, ValueError):
            continue

        locations.append({
            "id": member_user.id,
            "latitude": latitude,
            "longitude": longitude,
            "accuracy": loc.get("accuracy"),
            "age_seconds": age,
        })

    return locations


def fresh_party_location(member, member_user, current, statuses):

    if not member.location_sharing_enabled:
        return None, None

    if not has_location(member_user):
        return None, None

    age = location_age_seconds(
        member_user.last_location,
        current
    )

    if age is None:
        return None, None

    loc = member_user.last_location

    location_input = {
        "id": member_user.id,
        "latitude": loc.get("latitude"),
        "longitude": loc.get("longitude"),
        "accuracy": loc.get("accuracy"),
        "age_seconds": age,
    }

    if (
        age > FRESH_SECONDS
        or member_user.id not in statuses
        or not is_usable(location_input)
    ):
        return None, age

    return {
        "latitude": loc["latitude"],
        "longitude": loc["longitude"],
        "accuracy": loc.get("accuracy"),
    }, age


def meters_between_locations(origin, target):

    if (
        origin is None
        or target is None
        or target.get("latitude") is None
        or target.get("longitude") is None
    ):
        return None

    x, y = gps_to_xy(
        target["latitude"],
        target["longitude"],
        origin["latitude"],
        origin["longitude"]
    )

    return round(
        distance_from_party(
            x,
            y,
            0,
            0
        ),
        2
    )


def can_view_party_location(viewer, target_member, party):

    current = now_utc()

    viewer_member = get_member(
        party.id,
        viewer.id
    )

    return (
        party.status == PARTY_STATUS_ACTIVE
        and as_utc(party.expires_at) > current
        and viewer_member is not None
        and viewer_member.left_at is None
        and viewer_member.removed_at is None
        and target_member.left_at is None
        and target_member.removed_at is None
        and target_member.location_sharing_enabled
    )


def serialize_party(
    party,
    viewer,
    viewer_member,
    include_locations=True,
    current=None
):

    current = current or now_utc()
    rows = active_party_member_rows(party.id)
    locations = party_location_inputs(rows, current)
    snapshot = party_tracker.snapshot(
        party.id,
        locations,
        current
    )

    geofence = snapshot["geofence"] if snapshot else None
    statuses = snapshot["statuses"] if snapshot else {}
    destination = party_destination(party)

    members = []
    host_user = None
    my_status = "NOT_IN_PARTY"
    my_distance = None
    my_location = None

    for member, member_user in rows:

        if member.role == PARTY_ROLE_HOST:
            host_user = member_user

        location_payload, age = fresh_party_location(
            member,
            member_user,
            current,
            statuses
        )

        status_info = statuses.get(
            member_user.id,
            {}
        )

        if not member.location_sharing_enabled:
            member_status = "LOCATION_PAUSED"
        elif age is None:
            member_status = "NO_LOCATION"
        elif location_payload is None:
            member_status = "STALE_LOCATION"
        else:
            member_status = status_info.get(
                "status",
                "NOT_IN_PARTY"
            )

        distance_from_center = status_info.get(
            "distanceFromParty"
        )

        if member_user.id == viewer.id:
            my_status = (
                member_status
                if member_status in (
                    "INSIDE_PARTY",
                    "BUFFER_ZONE",
                    "WANDERING",
                    "FAR_FROM_PARTY",
                )
                else "NOT_IN_PARTY"
            )
            my_distance = distance_from_center
            my_location = location_payload

        members.append({
            "id": member_user.id,
            "username": member_user.username,
            "role": member.role,
            "isHost": member.role == PARTY_ROLE_HOST,
            "isSelf": member_user.id == viewer.id,
            "sharing": member.location_sharing_enabled,
            "checkInStatus": member.check_in_status,
            "checkInLabel": CHECK_IN_STATUSES.get(
                member.check_in_status,
                member.check_in_status
            ),
            "joinedAt": as_utc(member.joined_at).isoformat(),
            "status": member_status,
            "distanceFromParty": distance_from_center,
            "ageSeconds": age,
            "location": (
                location_payload
                if include_locations
                and can_view_party_location(viewer, member, party)
                else None
            ),
            "canRemove": (
                viewer_member.role == PARTY_ROLE_HOST
                and member_user.id != party.host_user_id
            ),
        })

    destination_location = (
        {
            "latitude": destination["latitude"],
            "longitude": destination["longitude"],
        }
        if destination
        and destination["latitude"] is not None
        and destination["longitude"] is not None
        else None
    )

    group_location = (
        geofence["center"]
        if geofence
        else None
    )

    return {
        **party_summary(party),
        "host": (
            {
                "id": host_user.id,
                "username": host_user.username,
            }
            if host_user
            else None
        ),
        "memberCount": len(members),
        "members": members,
        "geofence": geofence,
        "myRole": viewer_member.role,
        "myStatus": my_status,
        "myDistanceFromParty": my_distance,
        "mySharing": viewer_member.location_sharing_enabled,
        "timeRemainingSeconds": max(
            0,
            int(
                (
                    as_utc(party.expires_at)
                    - current
                ).total_seconds()
            )
        ),
        "inviteUrl": (
            request.url_root.rstrip("/")
            + "/join?code="
            + party.join_code
        ),
        "myDistanceToDestination": meters_between_locations(
            my_location,
            destination_location
        ),
        "groupDistanceToDestination": meters_between_locations(
            group_location,
            destination_location
        ),
    }


def map_payload(user):

    # Everything the map needs: the explicit party group, plus the
    # friends who normally chose to share their location with me.
    current = now_utc()
    expire_old_parties(current)

    membership = current_party_membership(user)
    active_party = None
    my_geofence = None
    my_status = "NOT_IN_PARTY"
    my_distance = None
    party_statuses = {}

    if membership:

        active_party = db.session.get(
            Party,
            membership.party_id
        )

        active_party = serialize_party(
            active_party,
            user,
            membership,
            include_locations=True,
            current=current
        )

        my_geofence = active_party["geofence"]
        my_status = active_party["myStatus"]
        my_distance = active_party["myDistanceFromParty"]

        party_statuses = {
            member["id"]: member
            for member in active_party["members"]
        }

    left_membership = (
        None
        if membership
        else left_party_membership(user)
    )

    left_party = (
        party_summary(
            db.session.get(
                Party,
                left_membership.party_id
            )
        )
        if left_membership
        else None
    )

    friends = []

    shared_with_me = (
        User.query
        .join(
            LocationShare,
            LocationShare.owner_id == User.id
        )
        .filter(LocationShare.viewer_id == user.id)
        .order_by(User.username_lower)
        .all()
    )

    for friend in shared_with_me:

        party_member_status = party_statuses.get(
            friend.id
        )

        entry = {
            "id": friend.id,
            "username": friend.username,
            "location": None,
            "ageSeconds": None,
            "status": (
                party_member_status["status"]
                if party_member_status
                else "NOT_IN_PARTY"
            ),
            "distanceFromParty": (
                party_member_status["distanceFromParty"]
                if party_member_status
                else None
            ),
            "sameParty": bool(party_member_status),
        }

        if has_location(friend):

            loc = friend.last_location

            entry["location"] = {
                "latitude": loc["latitude"],
                "longitude": loc["longitude"],
                "accuracy": loc.get("accuracy"),
            }
            entry["ageSeconds"] = location_age_seconds(
                loc,
                current
            )

        friends.append(entry)

    return {
        "me": {
            "party": my_geofence,
            "status": my_status,
            "distanceFromParty": my_distance,
            "leftParty": left_party,
        },
        "party": active_party,
        "friends": friends,
        "freshSeconds": FRESH_SECONDS,
        "clusterDistance": CLUSTER_DISTANCE,
    }


# ==================================================
# LOCATION
# ==================================================

@app.post("/location")
def location():

    data = request.get_json(
        silent=True
    ) or {}

    latitude = data.get("latitude")
    longitude = data.get("longitude")
    accuracy = data.get("accuracy")

    if latitude is None or longitude is None:

        return jsonify({
            "error": "Latitude and longitude are required"
        }), 400

    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        return json_error(
            "Latitude and longitude must be numbers.",
            400
        )

    if not (
        -90 <= latitude <= 90
        and -180 <= longitude <= 180
    ):
        return json_error(
            "Latitude or longitude is out of range.",
            400
        )

    # Accuracy is optional; ignore anything that isn't a
    # sensible number of meters.
    try:
        accuracy = float(accuracy)
        if not 0 <= accuracy < 100000:
            accuracy = None
    except (TypeError, ValueError):
        accuracy = None

    user = require_user()

    if not user:

        return jsonify({
            "error":
                "You must be signed in before sending location."
        }), 401

    # --------------------------------------------------
    # SAVE THIS PHONE'S LATEST LOCATION
    # --------------------------------------------------

    user.last_location = {
        "latitude": latitude,
        "longitude": longitude,
        "accuracy": accuracy,
        "updatedAt": iso_now()
    }

    db.session.commit()

    if DEBUG_MODE:
        print(
            "LOCATION:",
            user.username,
            round(latitude, 6),
            round(longitude, 6),
            "| accuracy:",
            accuracy,
            flush=True
        )
    else:
        print(
            "LOCATION UPDATED:",
            user.username,
            flush=True
        )

    return jsonify(map_payload(user))


@app.get("/api/map")
def map_data():

    user = require_user()

    if not user:
        return json_error("You must be signed in.", 401)

    return jsonify(map_payload(user))


def apply_destination(party, destination):

    if not destination:
        return

    party.destination_name = destination["name"]
    party.destination_address = destination["address"]
    party.destination_latitude = destination["latitude"]
    party.destination_longitude = destination["longitude"]
    party.destination_start_time = destination["start_time"]
    party.destination_source = destination["source"]
    party.destination_source_url = destination["source_url"]


@app.post("/api/parties")
def create_party():

    user = require_user()

    if not user:
        return json_error("You must be signed in.", 401)

    if current_party_membership(user):
        return json_error(
            "Leave or end your current party before creating another one.",
            409
        )

    body = request.get_json(silent=True) or {}

    try:
        name = clean_required_text(
            body.get("name"),
            "Party name",
            80
        )
        destination = normalize_destination(
            body.get("destination")
        )
    except ValueError as error:
        return json_error(str(error), 400)

    current = now_utc()

    party = Party(
        name=name,
        join_code=generate_join_code(),
        host_user_id=user.id,
        status=PARTY_STATUS_ACTIVE,
        expires_at=(
            current
            + timedelta(hours=PARTY_DURATION_HOURS)
        ),
    )

    apply_destination(party, destination)

    db.session.add(party)
    db.session.flush()

    member = PartyMember(
        party_id=party.id,
        user_id=user.id,
        role=PARTY_ROLE_HOST,
        location_sharing_enabled=bool(
            body.get("shareLocation", True)
        ),
        check_in_status=CHECK_IN_GOOD,
    )

    db.session.add(member)
    db.session.commit()

    return jsonify({
        "ok": True,
        "party": serialize_party(
            party,
            user,
            member
        )
    }), 201


@app.post("/api/parties/join")
def join_party():

    user = require_user()

    if not user:
        return json_error("You must be signed in.", 401)

    if not check_join_rate_limit():
        return json_error(
            "Too many join attempts. Try again in a few minutes.",
            429
        )

    if current_party_membership(user):
        return json_error(
            "Leave your current party before joining another one.",
            409
        )

    body = request.get_json(silent=True) or {}
    code = normalize_party_code(
        body.get("code")
    )

    if not PARTY_CODE_RE.match(code):
        return json_error(
            "Enter a valid party code like OWL-4827.",
            400
        )

    current = now_utc()
    expire_old_parties(current)

    party = Party.query.filter_by(
        join_code=code
    ).first()

    if not party:
        return json_error(
            "That party code was not found.",
            404
        )

    if party.status != PARTY_STATUS_ACTIVE:
        return json_error(
            "That party has ended.",
            409
        )

    if as_utc(party.expires_at) <= current:
        expire_old_parties(current)
        return json_error(
            "That party has expired.",
            409
        )

    existing = get_member(
        party.id,
        user.id
    )

    if existing:
        return json_error(
            "You already have a membership for that party. Use rejoin if you left.",
            409
        )

    member = PartyMember(
        party_id=party.id,
        user_id=user.id,
        role=PARTY_ROLE_MEMBER,
        location_sharing_enabled=bool(
            body.get("shareLocation", False)
        ),
        check_in_status=CHECK_IN_GOOD,
    )

    db.session.add(member)
    db.session.commit()

    return jsonify({
        "ok": True,
        "party": serialize_party(
            party,
            user,
            member
        ),
        "member": {
            "id": member.id,
            "role": member.role,
            "locationSharingEnabled":
                member.location_sharing_enabled,
        },
    }), 201


@app.get("/api/parties/current")
def current_party():

    user = require_user()

    if not user:
        return json_error("You must be signed in.", 401)

    member = current_party_membership(user)

    if not member:
        left_member = left_party_membership(user)
        left_party = (
            party_summary(
                db.session.get(
                    Party,
                    left_member.party_id
                )
            )
            if left_member
            else None
        )

        return jsonify({
            "party": None,
            "leftParty": left_party,
        })

    party = db.session.get(
        Party,
        member.party_id
    )

    return jsonify({
        "party": serialize_party(
            party,
            user,
            member
        ),
        "leftParty": None,
    })


@app.get("/api/parties/<party_id>")
def get_party(party_id):

    user, party, member, error = require_active_party_member(
        party_id
    )

    if error:
        return error

    return jsonify({
        "party": serialize_party(
            party,
            user,
            member
        )
    })


@app.get("/api/parties/<party_id>/locations")
def party_locations_api(party_id):

    user, party, member, error = require_active_party_member(
        party_id
    )

    if error:
        return error

    party_data = serialize_party(
        party,
        user,
        member,
        include_locations=True
    )

    return jsonify({
        "partyId": party.id,
        "geofence": party_data["geofence"],
        "members": party_data["members"],
        "freshSeconds": FRESH_SECONDS,
    })


@app.post("/api/parties/<party_id>/leave")
def leave_party_by_id(party_id):

    user, party, member, error = require_active_party_member(
        party_id
    )

    if error:
        return error

    if member.role == PARTY_ROLE_HOST:
        return json_error(
            "Hosts must end the party instead of leaving it.",
            409
        )

    current = now_utc()

    member.left_at = current
    member.location_sharing_enabled = False
    db.session.commit()

    return jsonify({
        "ok": True,
        "party": party_summary(party),
    })


@app.post("/api/parties/<party_id>/rejoin")
def rejoin_party_by_id(party_id):

    user = require_user()

    if not user:
        return json_error("You must be signed in.", 401)

    if current_party_membership(user):
        return json_error(
            "Leave your current party before rejoining another one.",
            409
        )

    current = now_utc()
    expire_old_parties(current)

    party = db.session.get(
        Party,
        party_id
    )

    if not party:
        return json_error("Party not found.", 404)

    if party.status != PARTY_STATUS_ACTIVE:
        return json_error(
            "That party has ended.",
            409
        )

    if as_utc(party.expires_at) <= current:
        expire_old_parties(current)
        return json_error(
            "That party has expired.",
            409
        )

    member = get_member(
        party.id,
        user.id
    )

    if not member or member.removed_at is not None:
        return json_error(
            "You cannot rejoin this party.",
            403
        )

    body = request.get_json(silent=True) or {}

    member.left_at = None
    member.location_sharing_enabled = bool(
        body.get("shareLocation", False)
    )
    db.session.commit()

    return jsonify({
        "ok": True,
        "party": serialize_party(
            party,
            user,
            member
        ),
    })


@app.post("/api/parties/<party_id>/end")
def end_party(party_id):

    user, party, member, error = require_party_host(
        party_id
    )

    if error:
        return error

    mark_party_ended(
        party,
        now_utc()
    )
    db.session.commit()

    return jsonify({
        "ok": True,
        "party": party_summary(party),
    })


@app.delete("/api/parties/<party_id>/members/<user_id>")
def remove_party_member(party_id, user_id):

    host, party, host_member, error = require_party_host(
        party_id
    )

    if error:
        return error

    if user_id == host.id:
        return json_error(
            "The host must end the party instead of removing themselves.",
            409
        )

    member = get_member(
        party.id,
        user_id
    )

    if (
        not member
        or member.left_at is not None
        or member.removed_at is not None
    ):
        return json_error(
            "That user is not a current party member.",
            404
        )

    current = now_utc()
    member.left_at = current
    member.removed_at = current
    member.removed_by_user_id = host.id
    member.location_sharing_enabled = False
    db.session.commit()

    removed_user = find_user_by_id(user_id)

    return jsonify({
        "ok": True,
        "removedUser": (
            {
                "id": removed_user.id,
                "username": removed_user.username,
            }
            if removed_user
            else {"id": user_id}
        ),
    })


@app.post("/api/parties/<party_id>/location-sharing")
def set_party_location_sharing(party_id):

    user, party, member, error = require_active_party_member(
        party_id
    )

    if error:
        return error

    body = request.get_json(silent=True) or {}

    if "enabled" not in body:
        return json_error(
            "enabled is required.",
            400
        )

    member.location_sharing_enabled = bool(
        body.get("enabled")
    )
    db.session.commit()

    return jsonify({
        "ok": True,
        "party": serialize_party(
            party,
            user,
            member
        ),
    })


@app.post("/api/parties/<party_id>/status")
def set_party_status(party_id):

    user, party, member, error = require_active_party_member(
        party_id
    )

    if error:
        return error

    body = request.get_json(silent=True) or {}
    status = str(body.get("status") or "").strip().upper()

    if status not in CHECK_IN_STATUSES:
        return json_error(
            "Choose a valid status.",
            400
        )

    member.check_in_status = status
    db.session.commit()

    return jsonify({
        "ok": True,
        "party": serialize_party(
            party,
            user,
            member
        ),
    })


@app.post("/api/party/leave")
def legacy_leave_party():

    user = require_user()

    if not user:
        return json_error("You must be signed in.", 401)

    member = current_party_membership(user)

    if not member:
        return jsonify(map_payload(user))

    response = leave_party_by_id(member.party_id)

    if isinstance(response, tuple):
        return response

    return jsonify(map_payload(user))


@app.post("/api/party/rejoin")
def legacy_rejoin_party():

    user = require_user()

    if not user:
        return json_error("You must be signed in.", 401)

    member = left_party_membership(user)

    if not member:
        return json_error(
            "That party has ended, so there is nothing to rejoin.",
            409
        )

    response = rejoin_party_by_id(member.party_id)

    if isinstance(response, tuple):
        return response

    return jsonify(map_payload(user))


# ==================================================
# LOCATION SHARING
# ==================================================

def share_entry(user, sharing_ids):

    return {
        "id": user.id,
        "username": user.username,
        "sharing": user.id in sharing_ids,
    }


def my_sharing_ids(user):

    return {
        share.viewer_id
        for share in LocationShare.query.filter_by(
            owner_id=user.id
        )
    }


@app.get("/api/users/search")
def search_users():

    user = require_user()

    if not user:
        return json_error("You must be signed in.", 401)

    query = str(request.args.get("q") or "").strip().lower()

    if len(query) < 2:
        return json_error(
            "Type at least 2 characters to search.",
            400
        )

    # Usernames match partially; emails only match exactly so
    # the search can't be used to list everyone's email.
    if "@" in query:
        condition = User.email == query
    else:
        escaped = (
            query
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        condition = User.username_lower.like(
            f"%{escaped}%",
            escape="\\"
        )

    matches = (
        User.query
        .filter(condition, User.id != user.id)
        .order_by(User.username_lower)
        .limit(10)
        .all()
    )

    sharing_ids = my_sharing_ids(user)

    return jsonify({
        "users": [
            share_entry(match, sharing_ids)
            for match in matches
        ]
    })


@app.get("/api/shares")
def list_shares():

    user = require_user()

    if not user:
        return json_error("You must be signed in.", 401)

    sharing_with = (
        User.query
        .join(
            LocationShare,
            LocationShare.viewer_id == User.id
        )
        .filter(LocationShare.owner_id == user.id)
        .order_by(User.username_lower)
        .all()
    )

    return jsonify({
        "sharingWith": [
            {"id": viewer.id, "username": viewer.username}
            for viewer in sharing_with
        ]
    })


@app.post("/api/shares")
def add_share():

    user = require_user()

    if not user:
        return json_error("You must be signed in.", 401)

    body = request.get_json(silent=True) or {}

    viewer = find_user_by_id(str(body.get("userId") or ""))

    if not viewer or viewer.id == user.id:
        return json_error("That account doesn't exist.", 404)

    if not LocationShare.query.filter_by(
        owner_id=user.id,
        viewer_id=viewer.id
    ).first():

        db.session.add(
            LocationShare(
                owner_id=user.id,
                viewer_id=viewer.id
            )
        )
        db.session.commit()

    return jsonify({
        "ok": True,
        "user": {"id": viewer.id, "username": viewer.username}
    }), 201


@app.delete("/api/shares/<viewer_id>")
def remove_share(viewer_id):

    user = require_user()

    if not user:
        return json_error("You must be signed in.", 401)

    LocationShare.query.filter_by(
        owner_id=user.id,
        viewer_id=viewer_id
    ).delete()

    db.session.commit()

    return jsonify({"ok": True})


# ==================================================
# GET MY LOCATION
# ==================================================

@app.get("/api/location/me")
def get_my_location():

    user = require_user()

    if not user:

        return json_error(
            "You must be signed in.",
            401
        )

    return jsonify({
        "ok": True,
        "user": user.to_public_dict(),
        "location": user.last_location
    })


# ==================================================
# DEBUG DATABASE
# ==================================================

@app.get("/api/debug/users")
def debug_users():

    # Lists every user's email and location, so it only
    # exists in debug mode and still requires a login.
    if not DEBUG_MODE:
        return json_error("Not found.", 404)

    if not require_user():
        return json_error("You must be signed in.", 401)

    users = User.query.all()

    stored_users = []

    for user in users:

        stored_users.append({
            "id":
                user.id,

            "email":
                user.email,

            "username":
                user.username,

            "last_location":
                user.last_location
        })

    print("\n================================")
    print("DATABASE USERS")
    print("================================")

    print(
        "Number of users:",
        len(stored_users)
    )

    for stored_user in stored_users:

        print(
            stored_user["username"],
            "|",
            stored_user["email"],
            "|",
            stored_user["last_location"]
        )

    return jsonify({
        "count": len(stored_users),
        "users": stored_users
    })


# ==================================================
# FRONTEND FILES
# Keep this AFTER the API routes
# ==================================================

@app.route("/<path:filename>")
def frontend_files(filename):

    return send_from_directory(
        FRONTEND_DIR,
        filename
    )


# ==================================================
# START SERVER
# ==================================================

if __name__ == "__main__":

    print(
        "Frontend folder:",
        FRONTEND_DIR
    )

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=DEBUG_MODE and not PRODUCTION_MODE
    )
