# FriendsNMe

FriendsNMe is a Temple University student project that helps groups of friends stay together during parties and nights out. Students sign in with a Temple `@temple.edu` email, create a private temporary Party Group, invite friends with a short code, and share live location only with that party.

FriendsNMe is an independent student project and is not affiliated with or endorsed by Temple University or TU Parties.

## Phase 1 Party Workflow

1. A signed-in user creates a party and gives it a name.
2. FriendsNMe creates a short join code like `OWL-4827`.
3. The creator becomes the host and can invite friends with `/join?code=...`.
4. Other signed-in Temple users confirm the join code before joining.
5. Each member explicitly chooses whether to share live location with that party.
6. Party geofence and wandering status are calculated only from active members of that exact Party Group.
7. Members can pause sharing, set check-in status, leave, or rejoin while allowed.
8. The host can remove members or end the party.
9. Parties expire after about 12 hours by default, which stops party location sharing.

Permanent friend sharing still exists on the Sharing page. Joining a party does not add anyone to a normal sharing list.

## Run Locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
SESSION_SECRET=dev-secret flask --app server/data/app.py db upgrade
AUTH_LOG_VERIFICATION_CODES=true FRIENDSNME_DEBUG=true python server/data/app.py
```

Open:

```text
http://localhost:5000/
```

When testing locally, verification codes print in the Flask terminal.

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
$env:SESSION_SECRET="dev-secret"
flask --app server/data/app.py db upgrade
$env:AUTH_LOG_VERIFICATION_CODES="true"
$env:FRIENDSNME_DEBUG="true"
python server/data/app.py
```

## Environment Variables

- `SESSION_SECRET`: signs login cookies. Required in production. Local dev gets a temporary secret if unset, but using a fixed dev value avoids surprise sign-outs.
- `DATABASE_URL`: production database URL. Railway PostgreSQL provides this automatically.
- `FRIENDSNME_DATABASE_URI`: optional local/test SQLAlchemy database URI. Defaults to `server/data/friendsnme.db` when `DATABASE_URL` is not set.
- `FRIENDSNME_ENV=production` or `FLASK_ENV=production`: enables production config outside Railway. Railway is detected automatically through `RAILWAY_ENVIRONMENT`.
- `FRIENDSNME_DEBUG=true`: enables Flask debug mode, debug user logs, and `/api/debug/users`. Do not use this on a public or shared network.
- `AUTH_LOG_VERIFICATION_CODES=true`: prints verification codes in development only. It is ignored in production.
- `FRIENDSNME_REQUIRE_EMAIL_DELIVERY=true`: in development, require SMTP email delivery instead of falling back to terminal verification codes.
- `SMTP_HOST`, `SMTP_FROM`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_SECURE`: required in production for real email delivery.

Production requires:

```text
SESSION_SECRET
DATABASE_URL
SMTP_HOST
SMTP_PORT
SMTP_FROM
SMTP_USER
SMTP_PASS
SMTP_SECURE
```

Keep these off in production:

```text
FRIENDSNME_DEBUG
AUTH_LOG_VERIFICATION_CODES
```

## Sending Verification Codes by Email

For local testing with real email delivery:

1. Copy `.env.example` to `.env`.
2. Fill in real SMTP settings from your email provider.
3. Set `FRIENDSNME_REQUIRE_EMAIL_DELIVERY=true`.
4. Make sure `AUTH_LOG_VERIFICATION_CODES` is not set.
5. Restart Flask.

Example `.env` values:

```text
SESSION_SECRET=<your local secret>
FRIENDSNME_REQUIRE_EMAIL_DELIVERY=true
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_FROM=FriendsNMe <no-reply@example.com>
SMTP_USER=<smtp username>
SMTP_PASS=<smtp password>
SMTP_SECURE=false
```

Use `SMTP_SECURE=false` for SMTP with STARTTLS on port `587`. Use `SMTP_SECURE=true` for SMTP-over-SSL on port `465`.

Production always requires SMTP and never prints verification codes to the console.

## Database Migrations

FriendsNMe uses Flask-Migrate/Alembic. Do not rely on automatic `db.create_all()` for production.

Fresh local database:

```bash
SESSION_SECRET=dev-secret flask --app server/data/app.py db upgrade
```

Production/Railway database:

```bash
flask --app server/data/app.py db upgrade
```

If you already have a local SQLite database from before migrations, back it up first. If the schema already matches the initial migration, use `flask --app server/data/app.py db stamp head`; otherwise create a fresh local DB or write a one-off migration for that database.

## Testing With Multiple Phones

Phone browsers require HTTPS for location access unless the site is on `localhost`. For same-network phone testing, run Flask on the laptop and expose it through a temporary HTTPS tunnel:

```bash
source .venv/bin/activate
SESSION_SECRET=<your generated secret> flask --app server/data/app.py db upgrade
AUTH_LOG_VERIFICATION_CODES=true SESSION_SECRET=<your generated secret> python server/data/app.py
cloudflared tunnel --url http://localhost:5000
```

Open the `https://...trycloudflare.com` URL on each phone. Create separate accounts, create a party on one phone, join with the code on the others, then tap `Use my location`.

## Tests

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

The tests use an isolated SQLite database path configured through `FRIENDSNME_DATABASE_URI`.

## Deploying FriendsNMe to Railway

FriendsNMe deploys as one Flask app that serves both the frontend and API from the same Railway domain.

1. Create a Railway project.
2. Connect the GitHub repository.
3. Add a Railway PostgreSQL service to the project.
4. Confirm the web service has `DATABASE_URL` from the PostgreSQL service.
5. Add production environment variables:

```text
SESSION_SECRET=<generate a long random value>
SMTP_HOST=<your SMTP host>
SMTP_PORT=587
SMTP_FROM=<verified sender address>
SMTP_USER=<SMTP username>
SMTP_PASS=<SMTP password>
SMTP_SECURE=false
```

6. Make sure these are not set in production:

```text
FRIENDSNME_DEBUG
AUTH_LOG_VERIFICATION_CODES
```

7. Use the Railway start command from `railway.json`:

```bash
gunicorn --chdir server/data --bind 0.0.0.0:$PORT app:app
```

8. Run the migration command in a Railway shell or one-off command:

```bash
flask --app server/data/app.py db upgrade
```

9. Generate the Railway public domain.
10. Open `/api/health`; it should return:

```json
{
  "status": "ok",
  "database": "ok"
}
```

11. Test Temple email verification using a real `@temple.edu` address.
12. Create a party on one account.
13. Join the party from a second account using the invite URL or code.
14. Test location sharing with two phones over the Railway HTTPS URL.

Railway rollback:

1. Open the Railway service deployments.
2. Select the last known good deployment.
3. Choose Redeploy/Rollback for that deployment.
4. If a database migration caused the issue, deploy code compatible with the current schema or run the matching Alembic downgrade only after confirming it will not destroy needed data.

## Party API

- `POST /api/parties`
- `POST /api/parties/join`
- `GET /api/parties/current`
- `GET /api/parties/<party_id>`
- `GET /api/parties/<party_id>/locations`
- `POST /api/parties/<party_id>/leave`
- `POST /api/parties/<party_id>/rejoin`
- `POST /api/parties/<party_id>/end`
- `DELETE /api/parties/<party_id>/members/<user_id>`
- `POST /api/parties/<party_id>/location-sharing`
- `POST /api/parties/<party_id>/status`

Authorization is server-side. The frontend never proves identity by sending a viewer ID.

## Database Changes

New tables:

- `parties`: party name, unique join code, host, status, expiration, end time, and optional destination fields.
- `party_members`: one row per party/user pair, role, joined/left/removed timestamps, temporary location sharing flag, and latest check-in status.

Existing user location storage remains "latest location only" on the `users` table.

## TU Parties Behavior

FriendsNMe does not scrape TU Parties, bypass authentication, copy private addresses, collect cookies, or claim affiliation. The Create Party modal includes a `Find on TU Parties` link that opens `https://www.tuparties.com/` in a new tab. Users can then manually enter an event name, address, start time, optional URL, and mark the source as TU Parties.

The backend normalizes manual and TU Parties-sourced destination data through `server/data/event_sources.py`, so an approved API can later replace the manual step without changing the rest of the app.

## Privacy Assumptions

- Party locations are returned only to active members of the same active party.
- A member must have party location sharing enabled.
- Stale party locations are not returned as live coordinates.
- Leaving, being removed, party expiration, or host ending immediately disables party sharing.
- Public search and profile responses do not include coordinates.
- Exact coordinates are only printed in debug mode.
- FriendsNMe is not an emergency service. Call 911 in an emergency.

## Geofence Settings

Production-style settings live in `server/data/calculations.py`:

- `MIN_PARTY_USERS`
- `CLUSTER_DISTANCE`
- `MIN_PARTY_RADIUS`
- `WARNING_BUFFER`
- `ALERT_BUFFER`
- `MAX_PARTY_RADIUS`
- `MAX_ACCURACY_MARGIN`

Production values are the default. For short-distance two-phone testing, start Flask with:

```bash
FRIENDSNME_SMALL_RADIUS_TESTING=true AUTH_LOG_VERIFICATION_CODES=true python server/data/app.py
```

Do not set `FRIENDSNME_SMALL_RADIUS_TESTING=true` for real-world use.
