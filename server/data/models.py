from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

import uuid

db = SQLAlchemy()

# We want to be able to generate a unique id for each account record

def generate_uuid():
    return str(uuid.uuid4())

def utc_now():
    return datetime.now(timezone.utc)


PARTY_STATUS_ACTIVE = "ACTIVE"
PARTY_STATUS_ENDED = "ENDED"

PARTY_ROLE_HOST = "HOST"
PARTY_ROLE_MEMBER = "MEMBER"

CHECK_IN_GOOD = "IM_GOOD"
CHECK_IN_HEADING_HOME = "HEADING_HOME"
CHECK_IN_NEED_HELP = "NEED_HELP"


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.String, primary_key=True, default=generate_uuid)

    email = db.Column(db.String(120), unique=True, nullable=False)

    username = db.Column(db.String(32), nullable=False)

    username_lower = db.Column(db.String(32), unique=True, nullable=False)

    # We can do last location in the database
    last_location = db.Column(db.JSON, nullable=True)
    # We can use a JSON blob to store Users most recent location
    # (Lat, Long, Accur, Timestamps bundled)

    created_at = db.Column(db.DateTime(timezone=True), default=utc_now)

    def to_public_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "username": self.username,
            # SQLite returns naive datetimes; they are stored as UTC
            "createdAt": self.created_at.replace(tzinfo=timezone.utc).isoformat(),
        }


class LocationShare(db.Model):
    # owner shares their location with viewer. One direction only:
    # each person decides who can see them.
    __tablename__ = "location_shares"
    __table_args__ = (db.UniqueConstraint("owner_id", "viewer_id"),)

    id = db.Column(db.String, primary_key=True, default=generate_uuid)

    owner_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False, index=True)

    viewer_id = db.Column(db.String, db.ForeignKey("users.id"), nullable=False, index=True)

    created_at = db.Column(db.DateTime(timezone=True), default=utc_now)


class Party(db.Model):
    __tablename__ = "parties"

    id = db.Column(db.String, primary_key=True, default=generate_uuid)

    name = db.Column(db.String(80), nullable=False)

    join_code = db.Column(db.String(16), unique=True, nullable=False, index=True)

    host_user_id = db.Column(
        db.String,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    status = db.Column(
        db.String(16),
        nullable=False,
        default=PARTY_STATUS_ACTIVE,
        index=True
    )

    created_at = db.Column(db.DateTime(timezone=True), default=utc_now)

    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)

    ended_at = db.Column(db.DateTime(timezone=True), nullable=True)

    destination_name = db.Column(db.String(120), nullable=True)

    destination_address = db.Column(db.String(240), nullable=True)

    destination_latitude = db.Column(db.Float, nullable=True)

    destination_longitude = db.Column(db.Float, nullable=True)

    destination_start_time = db.Column(db.String(40), nullable=True)

    destination_source = db.Column(db.String(40), nullable=True)

    destination_source_url = db.Column(db.String(500), nullable=True)


class PartyMember(db.Model):
    __tablename__ = "party_members"
    __table_args__ = (
        db.UniqueConstraint(
            "party_id",
            "user_id",
            name="uq_party_member_user"
        ),
    )

    id = db.Column(db.String, primary_key=True, default=generate_uuid)

    party_id = db.Column(
        db.String,
        db.ForeignKey("parties.id"),
        nullable=False,
        index=True
    )

    user_id = db.Column(
        db.String,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    role = db.Column(
        db.String(16),
        nullable=False,
        default=PARTY_ROLE_MEMBER
    )

    joined_at = db.Column(db.DateTime(timezone=True), default=utc_now)

    left_at = db.Column(db.DateTime(timezone=True), nullable=True)

    removed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    removed_by_user_id = db.Column(
        db.String,
        db.ForeignKey("users.id"),
        nullable=True
    )

    location_sharing_enabled = db.Column(db.Boolean, nullable=False, default=False)

    check_in_status = db.Column(
        db.String(24),
        nullable=False,
        default=CHECK_IN_GOOD
    )


class VerificationCode(db.Model):
    __tablename__ = "verification_codes"

    id = db.Column(db.String, primary_key=True, default=generate_uuid)

    email = db.Column(db.String(120), nullable=False, index=True)

    code_hash = db.Column(db.String(64), nullable=False)

    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), default=utc_now)

    attempts = db.Column(db.Integer, default=0)

    used_at = db.Column(db.DateTime(timezone=True), nullable=True)
