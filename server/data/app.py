from flask import Flask, request, jsonify, send_from_directory
from calculations import analyze_location
import os


# ==================================================
# FOLDERS
# ==================================================

# Folder containing this app.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Go from:
# server/data -> server -> FriendsNMe -> Frontend
FRONTEND_DIR = os.path.abspath(
    os.path.join(BASE_DIR, "..", "..", "Frontend")
)

app = Flask(__name__)


# ==================================================
# WEBSITE
# ==================================================

@app.route("/")
def home():
    return send_from_directory(FRONTEND_DIR, "index.html")


# Serve frontend files such as:
# style.css
# index.js
# script.js
# map.html
@app.route("/<path:filename>")
def frontend_files(filename):
    return send_from_directory(FRONTEND_DIR, filename)


# ==================================================
# LOCATION API
# ==================================================

@app.route("/location", methods=["POST"])
def location():

    data = request.get_json()

    if not data:
        return jsonify({
            "error": "No location data received"
        }), 400

    latitude = data.get("latitude")
    longitude = data.get("longitude")

    if latitude is None or longitude is None:
        return jsonify({
            "error": "Latitude and longitude are required"
        }), 400

    # Send GPS coordinates to calculations.py
    result = analyze_location(
        latitude,
        longitude
    )

    # Send calculations.py result back to browser
    return jsonify(result)


# ==================================================
# START SERVER
# ==================================================

if __name__ == "__main__":

    print("Frontend folder:", FRONTEND_DIR)

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )