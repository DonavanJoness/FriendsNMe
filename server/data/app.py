import hashlib
import hmac
import os
import random
import re
import secrets
import smtplib

from datetime import timedelta, timezone, datetime
from email.message import EmailMessage

from flask import Flask, request, jsonify, send_from_directory, session

from models import db, User, VerificationCode
from calculations import analyze_location


# ==================================================
# FOLDERS
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FRONTEND_DIR = os.path.abspath(
    os.path.join(BASE_DIR, "..", "..", "Frontend")
)


# ==================================================
# FLASK APP
# ==================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SESSION_SECRET",
    "development-only-secret-change-me"
)

app.permanent_session_lifetime = timedelta(days=30)


# ==================================================
# DATABASE
# ==================================================

DATABASE_PATH = os.path.join(BASE_DIR, "friendsnme.db")

app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DATABASE_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():

    db.create_all()

    print("\n================================")
    print("DATABASE STARTED")
    print("================================")

    print("Database:", DATABASE_PATH)

    users = User.query.all()

    print("Users currently stored:", len(users))

    for user in users:

        print(
            "USER:",
            user.id,
            user.username,
            user.email,
            user.last_location
        )


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


# ==================================================
# HELPERS
# ==================================================

def now_utc():
    return datetime.now(timezone.utc)


def iso_now():
    return now_utc().isoformat()


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


# ==================================================
# EMAIL VERIFICATION
# ==================================================

def send_verification_email(email, code):

    should_log = (
        os.environ.get(
            "AUTH_LOG_VERIFICATION_CODES",
            ""
        ).lower() == "true"
    )

    is_production = (
        os.environ.get("FLASK_ENV")
        == "production"
    )

    # During development, print verification code
    # directly into terminal if SMTP is not configured.

    if (
        should_log
        or (
            not is_production
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
            "Email delivery is not configured."
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

        latest_created = recent_codes[0].created_at

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

    if (
        latitude is None
        or longitude is None
    ):

        return jsonify({
            "error":
                "Latitude and longitude are required"
        }), 400

    print("\n================================")
    print("LOCATION RECEIVED")
    print("================================")

    print("Latitude:", latitude)
    print("Longitude:", longitude)
    print("Accuracy:", accuracy)

    # Find the logged-in user

    user = require_user()

    if not user:

        print(
            "ERROR: No logged-in user found."
        )

        print(
            "SESSION:",
            dict(session)
        )

        return jsonify({
            "error":
                "You must be signed in before sending location."
        }), 401

    print(
        "Logged-in user:",
        user.username
    )

    print(
        "User ID:",
        user.id
    )

    # SAVE LOCATION TO DATABASE

    user.last_location = {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "accuracy": accuracy,
        "updatedAt": iso_now()
    }

    db.session.commit()

    print(
        "LOCATION SAVED TO DATABASE"
    )

    print(
        "Stored location:",
        user.last_location
    )

    # Existing calculations.py

    result = analyze_location(
        latitude,
        longitude
    )

    return jsonify(result)


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

    users = User.query.all()

    stored_users = []

    for user in users:

        stored_users.append({
            "id": user.id,
            "email": user.email,
            "username": user.username,
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
        port=5000,
        debug=True
    )