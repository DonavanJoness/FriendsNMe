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

<<<<<<< HEAD
    return accounts
=======
 return accounts

def save_accounts(accounts):

    with open(ACCOUNTS_FILE, "w") as file:

        for email, info in accounts.items():

           file.write(f"{info['name']},{email},{info['phone']}\n")


accounts = load_accounts()

@app.route("/signup", methods=["POST"])
}
>>>>>>> a0a7f0a (Added functions within accounts.py)
