from flask import Flask, request, jsonify

app = Flask(__name__)

ACCOUNTS_FILE = "accounts.txt"

    # When the server starts it reads txt file abd turns it into a py dictionary

def load_accounts():
    # Empty dictionary so data can pass through
    accounts = {}

    try:
        with open (ACCOUNTS_FILE, "r") as file:
        # Loop for to search file line by line
            for line in file:

                line = line.strip()

        if line:

            name, phone, email = line.split(",")
            # Turns above fields into separate variables for better readility

            accounts[email] = {"name": name, "phone":  phone}
    except FileNotFoundError:
        pass

    return accounts
