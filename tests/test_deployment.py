import os
import subprocess
import sys


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
            "SMTP_HOST",
            "SMTP_PORT",
            "SMTP_FROM",
            "SMTP_USER",
            "SMTP_PASS",
            "SMTP_SECURE",
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
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_FROM": "friendsnme@example.com",
        "SMTP_USER": "smtp-user",
        "SMTP_PASS": "smtp-pass",
        "SMTP_SECURE": "false",
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


def test_require_email_delivery_rejects_missing_smtp(monkeypatch):
    from test_parties import app

    monkeypatch.setenv("FRIENDSNME_REQUIRE_EMAIL_DELIVERY", "true")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)

    client = app.test_client()
    response = client.post(
        "/api/auth/request-code",
        json={"email": "emaildeliverytest@temple.edu"},
    )

    assert response.status_code == 503
    assert "Email delivery is not configured" in response.get_json()["error"]
