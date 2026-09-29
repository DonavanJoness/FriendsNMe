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
pip install -r requirements.txt
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
$env:AUTH_LOG_VERIFICATION_CODES="true"
$env:FRIENDSNME_DEBUG="true"
python server/data/app.py
```

## Environment Variables

- `SESSION_SECRET`: signs login cookies. Set this for any shared testing. If unset, the server creates a random secret and everyone is signed out on restart.
- `FRIENDSNME_DATABASE_URI`: optional SQLAlchemy database URI. Defaults to `server/data/friendsnme.db`.
- `FRIENDSNME_DEBUG=true`: enables Flask debug mode, debug user logs, and `/api/debug/users`. Do not use this on a public or shared network.
- `AUTH_LOG_VERIFICATION_CODES=true`: prints verification codes in the terminal instead of emailing them.
- `SMTP_HOST`, `SMTP_FROM`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_SECURE`: optional SMTP settings for real email delivery.

## Testing With Multiple Phones

Phone browsers require HTTPS for location access unless the site is on `localhost`. For same-network phone testing, run Flask on the laptop and expose it through a temporary HTTPS tunnel:

```bash
source .venv/bin/activate
AUTH_LOG_VERIFICATION_CODES=true SESSION_SECRET=<your generated secret> python server/data/app.py
cloudflared tunnel --url http://localhost:5000
```

Open the `https://...trycloudflare.com` URL on each phone. Create separate accounts, create a party on one phone, join with the code on the others, then tap `Use my location`.

## Tests

```bash
source .venv/bin/activate
pytest
```

The tests use an isolated SQLite database path configured through `FRIENDSNME_DATABASE_URI`.

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
