import os
import subprocess
import sys
from types import SimpleNamespace


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_PATH = os.path.join(ROOT, "server", "data")


def run_import_with_env(extra_env):
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {
            "DATABASE_URL",
            "FRIENDSNME_DATABASE_URI",
            "SESSION_SECRET",
            "FLASK_ENV",
            "FRIENDSNME_ENV",
            "RAILWAY_ENVIRONMENT",
            "RESEND_API_KEY",
            "EMAIL_FROM",
            "AUTH_LOG_VERIFICATION_CODES",
            "FRIENDSNME_DEBUG",
        }
    }
    env.update(extra_env)
    env["PYTHONPATH"] = APP_PATH
    env["PYTHONPYCACHEPREFIX"] = "/private/tmp/friendsnme_pycache"

    return subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import app; "
                "print(app.app.config['SQLALCHEMY_DATABASE_URI']); "
                "print(app.app.config['SESSION_COOKIE_SECURE'])"
            ),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_app_starts_with_sqlite_fallback():
    result = run_import_with_env({
        "SESSION_SECRET": "test-secret",
    })

    assert result.returncode == 0
    assert "sqlite:///" in result.stdout
    assert "False" in result.stdout


def test_app_uses_database_url_and_normalizes_postgres_scheme():
    result = run_import_with_env({
        "SESSION_SECRET": "test-secret",
        "DATABASE_URL": "postgres://user:pass@example.com:5432/friendsnme",
    })

    assert result.returncode == 0
    assert "postgresql://user:pass@example.com:5432/friendsnme" in result.stdout


def test_production_requires_session_secret_and_database_url():
    result = run_import_with_env({
        "FLASK_ENV": "production",
    })

    assert result.returncode != 0
    assert "Missing required production environment variables" in result.stderr
    assert "SESSION_SECRET" in result.stderr
    assert "DATABASE_URL" in result.stderr


def test_production_enables_secure_session_cookie():
    result = run_import_with_env({
        "FLASK_ENV": "production",
        "SESSION_SECRET": "test-secret",
        "DATABASE_URL": "postgresql://user:pass@example.com:5432/friendsnme",
    })

    assert result.returncode == 0
    assert "True" in result.stdout


def test_health_endpoint_reports_database_ok():
    from test_parties import app, db

    with app.app_context():
        db.create_all()

    client = app.test_client()
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "database": "ok",
    }


def test_auth_session_requires_login():
    from test_parties import app

    client = app.test_client()
    response = client.get("/api/auth/session")

    assert response.status_code == 401


def test_verification_request_rejects_missing_resend_config(monkeypatch):
    from test_parties import app

    monkeypatch.delenv("AUTH_LOG_VERIFICATION_CODES", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("EMAIL_FROM", raising=False)

    client = app.test_client()
    response = client.post(
        "/api/auth/request-code",
        json={"email": "missingresend@temple.edu"},
    )

    assert response.status_code == 503
    assert response.get_json()["error"] == (
        "Verification email delivery is not configured."
    )


def test_verification_email_sends_with_resend(monkeypatch):
    from test_parties import app

    sent = {}

    class FakeEmails:
        @staticmethod
        def send(params):
            sent["params"] = params
            return {"id": "email_123"}

    fake_resend = SimpleNamespace(
        api_key=None,
        Emails=FakeEmails,
    )

    monkeypatch.setitem(sys.modules, "resend", fake_resend)
    monkeypatch.delenv("AUTH_LOG_VERIFICATION_CODES", raising=False)
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("EMAIL_FROM", "FriendsNMe <no-reply@example.com>")

    client = app.test_client()
    response = client.post(
        "/api/auth/request-code",
        json={"email": "resendsuccess@temple.edu"},
    )

    assert response.status_code == 200
    assert fake_resend.api_key == "re_test_key"
    assert sent["params"]["from"] == "FriendsNMe <no-reply@example.com>"
    assert sent["params"]["to"] == ["resendsuccess@temple.edu"]
    assert sent["params"]["subject"] == "FriendsNMe verification code"
    assert "FriendsNMe" in sent["params"]["text"]
    assert "Your Temple verification code is:" in sent["params"]["text"]
    assert "This code expires in 10 minutes." in sent["params"]["text"]


def test_invalid_temple_email_is_rejected_before_email_send(monkeypatch):
    from test_parties import app

    monkeypatch.delenv("AUTH_LOG_VERIFICATION_CODES", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("EMAIL_FROM", raising=False)

    client = app.test_client()
    response = client.post(
        "/api/auth/request-code",
        json={"email": "student@example.com"},
    )

    assert response.status_code == 400
    assert "Temple University" in response.get_json()["error"]


def test_local_logging_mode_prints_code(monkeypatch, capsys):
    from test_parties import app

    monkeypatch.setenv("AUTH_LOG_VERIFICATION_CODES", "true")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("EMAIL_FROM", raising=False)

    client = app.test_client()
    response = client.post(
        "/api/auth/request-code",
        json={"email": "localprint@temple.edu"},
    )

    captured = capsys.readouterr()

    assert response.status_code == 200
    assert "[AUTH] Verification code for localprint@temple.edu:" in captured.out
