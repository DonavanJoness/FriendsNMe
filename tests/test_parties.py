import os
import sys
from datetime import timedelta
from types import SimpleNamespace

TEST_DB = "/private/tmp/friendsnme_pytest.db"

if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

os.environ["FRIENDSNME_DATABASE_URI"] = f"sqlite:///{TEST_DB}"
os.environ["SESSION_SECRET"] = "test-secret"
os.environ["AUTH_LOG_VERIFICATION_CODES"] = "true"

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "server", "data"))

import app as friends_app  # noqa: E402
from models import (  # noqa: E402
    User,
    Party,
    PartyMember,
    PARTY_STATUS_ENDED,
)


app = friends_app.app
db = friends_app.db


def make_user(username):
    user = User(
        email=f"{username.lower()}@temple.edu",
        username=username,
        username_lower=username.lower(),
    )
    db.session.add(user)
    db.session.commit()
    return SimpleNamespace(
        id=user.id,
        username=user.username,
        email=user.email,
    )


def login(client, user):
    with client.session_transaction() as session:
        session["user_id"] = user.id


def create_party(client, name="Friday Night"):
    return client.post(
        "/api/parties",
        json={
            "name": name,
            "shareLocation": True,
        },
    )


def join_party(client, code, share=True):
    return client.post(
        "/api/parties/join",
        json={
            "code": code,
            "shareLocation": share,
        },
    )


def send_location(client, latitude=39.981, longitude=-75.154):
    return client.post(
        "/location",
        json={
            "latitude": latitude,
            "longitude": longitude,
            "accuracy": 8,
        },
    )


def party_member_location(data, user_id):
    for member in data["members"]:
        if member["id"] == user_id:
            return member["location"]
    return None


def setup_module():
    with app.app_context():
        db.drop_all()
        db.create_all()


def setup_function():
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.create_all()
        friends_app.party_tracker.reset()


def test_authenticated_user_creates_party():
    with app.app_context():
        user = make_user("Donavan")

    client = app.test_client()
    login(client, user)

    response = create_party(client)

    assert response.status_code == 201
    data = response.get_json()
    assert data["party"]["name"] == "Friday Night"
    assert data["party"]["myRole"] == "HOST"
    assert data["party"]["mySharing"] is True


def test_unique_party_code_generated():
    with app.app_context():
        first = make_user("Mia")
        second = make_user("Gio")

    first_client = app.test_client()
    second_client = app.test_client()
    login(first_client, first)
    login(second_client, second)

    first_code = create_party(first_client, "One").get_json()["party"]["joinCode"]
    second_code = create_party(second_client, "Two").get_json()["party"]["joinCode"]

    assert first_code != second_code
    assert "-" in first_code


def test_user_joins_valid_party():
    with app.app_context():
        host = make_user("Host")
        member = make_user("Member")

    host_client = app.test_client()
    member_client = app.test_client()
    login(host_client, host)
    login(member_client, member)

    party = create_party(host_client).get_json()["party"]
    response = join_party(member_client, party["joinCode"])

    assert response.status_code == 201
    data = response.get_json()
    assert data["party"]["memberCount"] == 2
    assert data["member"]["role"] == "MEMBER"


def test_invalid_party_code_rejected():
    with app.app_context():
        user = make_user("Austin")

    client = app.test_client()
    login(client, user)

    response = join_party(client, "ZZZZ-0000")

    assert response.status_code == 404


def test_ended_party_cannot_be_joined():
    with app.app_context():
        host = make_user("Host")
        other = make_user("Other")

    host_client = app.test_client()
    other_client = app.test_client()
    login(host_client, host)
    login(other_client, other)

    party = create_party(host_client).get_json()["party"]
    host_client.post(f"/api/parties/{party['id']}/end", json={})

    response = join_party(other_client, party["joinCode"])

    assert response.status_code == 409


def test_duplicate_membership_rejected():
    with app.app_context():
        host = make_user("Host")
        member = make_user("Member")

    host_client = app.test_client()
    member_client = app.test_client()
    login(host_client, host)
    login(member_client, member)

    party = create_party(host_client).get_json()["party"]
    assert join_party(member_client, party["joinCode"]).status_code == 201

    response = join_party(member_client, party["joinCode"])

    assert response.status_code == 409


def test_party_a_members_cannot_see_party_b_locations():
    with app.app_context():
        host_a = make_user("HostA")
        host_b = make_user("HostB")

    client_a = app.test_client()
    client_b = app.test_client()
    login(client_a, host_a)
    login(client_b, host_b)

    party_a = create_party(client_a, "A").get_json()["party"]
    create_party(client_b, "B")
    send_location(client_a, 39.981, -75.154)
    send_location(client_b, 39.981, -75.154)

    data = client_a.get(f"/api/parties/{party_a['id']}/locations").get_json()

    assert party_member_location(data, host_b.id) is None
    assert party_member_location(data, host_a.id) is not None


def test_non_member_cannot_request_party_locations():
    with app.app_context():
        host = make_user("Host")
        stranger = make_user("Stranger")

    host_client = app.test_client()
    stranger_client = app.test_client()
    login(host_client, host)
    login(stranger_client, stranger)

    party = create_party(host_client).get_json()["party"]

    response = stranger_client.get(f"/api/parties/{party['id']}/locations")

    assert response.status_code == 403


def test_member_who_disables_location_stops_appearing():
    with app.app_context():
        host = make_user("Host")
        member = make_user("Member")

    host_client = app.test_client()
    member_client = app.test_client()
    login(host_client, host)
    login(member_client, member)

    party = create_party(host_client).get_json()["party"]
    join_party(member_client, party["joinCode"])
    send_location(member_client, 39.981, -75.154)

    member_client.post(
        f"/api/parties/{party['id']}/location-sharing",
        json={"enabled": False},
    )

    data = host_client.get(f"/api/parties/{party['id']}/locations").get_json()

    assert party_member_location(data, member.id) is None


def test_member_leaving_loses_access():
    with app.app_context():
        host = make_user("Host")
        member = make_user("Member")

    host_client = app.test_client()
    member_client = app.test_client()
    login(host_client, host)
    login(member_client, member)

    party = create_party(host_client).get_json()["party"]
    join_party(member_client, party["joinCode"])

    leave_response = member_client.post(f"/api/parties/{party['id']}/leave", json={})
    location_response = member_client.get(f"/api/parties/{party['id']}/locations")

    assert leave_response.status_code == 200
    assert location_response.status_code == 403


def test_host_can_end_party():
    with app.app_context():
        host = make_user("Host")

    client = app.test_client()
    login(client, host)

    party = create_party(client).get_json()["party"]
    response = client.post(f"/api/parties/{party['id']}/end", json={})

    assert response.status_code == 200
    with app.app_context():
        ended = db.session.get(Party, party["id"])
        assert ended.status == PARTY_STATUS_ENDED


def test_non_host_cannot_end_party():
    with app.app_context():
        host = make_user("Host")
        member = make_user("Member")

    host_client = app.test_client()
    member_client = app.test_client()
    login(host_client, host)
    login(member_client, member)

    party = create_party(host_client).get_json()["party"]
    join_party(member_client, party["joinCode"])

    response = member_client.post(f"/api/parties/{party['id']}/end", json={})

    assert response.status_code == 403


def test_expired_party_stops_sharing():
    with app.app_context():
        host = make_user("Host")

    client = app.test_client()
    login(client, host)

    party = create_party(client).get_json()["party"]
    send_location(client, 39.981, -75.154)

    with app.app_context():
        stored = db.session.get(Party, party["id"])
        stored.expires_at = friends_app.now_utc() - timedelta(minutes=1)
        db.session.commit()

    response = client.get(f"/api/parties/{party['id']}/locations")

    assert response.status_code == 409
    with app.app_context():
        member = PartyMember.query.filter_by(party_id=party["id"], user_id=host.id).first()
        assert member.location_sharing_enabled is False


def test_two_nearby_parties_remain_separate():
    with app.app_context():
        first = make_user("First")
        second = make_user("Second")

    first_client = app.test_client()
    second_client = app.test_client()
    login(first_client, first)
    login(second_client, second)

    first_party = create_party(first_client, "Party A").get_json()["party"]
    second_party = create_party(second_client, "Party B").get_json()["party"]
    send_location(first_client, 39.981, -75.154)
    send_location(second_client, 39.981, -75.154)

    first_data = first_client.get(f"/api/parties/{first_party['id']}/locations").get_json()
    second_data = second_client.get(f"/api/parties/{second_party['id']}/locations").get_json()

    assert party_member_location(first_data, first.id) is not None
    assert party_member_location(first_data, second.id) is None
    assert party_member_location(second_data, second.id) is not None
    assert party_member_location(second_data, first.id) is None


def test_malformed_coordinates_rejected():
    with app.app_context():
        user = make_user("BadGps")

    client = app.test_client()
    login(client, user)

    response = client.post(
        "/location",
        json={
            "latitude": "north",
            "longitude": -75.154,
        },
    )

    assert response.status_code == 400
