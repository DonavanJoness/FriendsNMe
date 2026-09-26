# FriendsNMe


Roles 
Main algorithm- this will be where calculations will be done for a user's gps location given from the website 
              - accounts and a buddy system (someone spli

alerts- once we receive the information from the calculations the alerts will connect back to an event that the website will go through 

UI- how the map will be set up basically front end (can be 2 or 3 people that works on this) 
  
- Duwayne: calculations/ alerts 
- Donavan: UI Design
- Gio: UI, Mapping
- Nymere: Accounts and Buddy System (Split)
- Austin: Calculations/alerts 

Node local server:
http://localhost:3000/

Flask local server:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
AUTH_LOG_VERIFICATION_CODES=true SESSION_SECRET=development-test-secret-development-test-secret python accounts.py
```

Then open:
http://localhost:5000/

When testing locally, verification codes print in the Flask terminal.

Flask local network server:

Use this when people on the same Wi-Fi/network need to open the website from
their own devices.

```bash
source .venv/bin/activate
HOST=10.109.29.222 AUTH_LOG_VERIFICATION_CODES=true SESSION_SECRET=development-test-secret-development-test-secret python accounts.py
```

Then share this link with people on the same network:
http://10.109.29.222:5000/


$env:AUTH_LOG_VERIFICATION_CODES="true"

$env:SESSION_SECRET="development-test-secret-development-test-secret"
node server/index.js

