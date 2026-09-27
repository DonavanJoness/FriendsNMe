# calculations.py

import math


# ==================================================
# SETTINGS
# ==================================================

# Minimum number of nearby phones needed to
# recognize a possible party.
MIN_PARTY_USERS = 3

# How close users need to be to each other
# to count as part of the party cluster.
CLUSTER_DISTANCE = 30  # meters

# Smallest radius our party area can have.
MIN_PARTY_RADIUS = 30  # meters

# Distance beyond party boundary before
# we consider someone to be wandering.
WARNING_BUFFER = 25  # meters

# Distance beyond party boundary for stronger alert.
ALERT_BUFFER = 55  # meters


# ==================================================
# LIVE LOCATION STORAGE
# ==================================================

# Stores the previous GPS location received from
# the phone. For now this is one phone.
previous_location = None

# Keeps track of total distance moved.
total_distance_traveled = 0.0


# --------------------------------------------------
# CONVERT GPS COORDINATES TO X/Y DISTANCE IN METERS
# --------------------------------------------------

def gps_to_xy(latitude, longitude, reference_lat, reference_lon):

    delta_lat = latitude - reference_lat
    delta_lon = longitude - reference_lon

    # North/South distance in meters
    y = delta_lat * 111320

    # East/West distance in meters
    x = (
        delta_lon
        * 111320
        * math.cos(math.radians(reference_lat))
    )

    return x, y


# --------------------------------------------------
# DISTANCE FROM PARTY / GEOFENCE
# --------------------------------------------------

def distance_from_party(user_x, user_y, party_x, party_y):

    delta_x = user_x - party_x
    delta_y = user_y - party_y

    distance = math.sqrt(
        delta_x**2 + delta_y**2
    )

    return distance


# --------------------------------------------------
# TAXICAB DISTANCE
# --------------------------------------------------

def taxicab_distance(x1, y1, x2, y2):

    distance = (
        abs(x2 - x1)
        +
        abs(y2 - y1)
    )

    return distance


# --------------------------------------------------
# DETECT PARTY CLUSTER
# --------------------------------------------------

def detect_party_cluster(
    users,
    cluster_distance=CLUSTER_DISTANCE,
    min_users=MIN_PARTY_USERS
):

    clustered_users = []

    # Check every user.
    for user in users:

        # The current user counts as one person.
        nearby_count = 1

        # Compare this user to everybody else.
        for other_user in users:

            # Don't compare someone to themselves.
            if user["id"] == other_user["id"]:
                continue

            distance = distance_from_party(
                user["x"],
                user["y"],
                other_user["x"],
                other_user["y"]
            )

            # Count them if they're close enough.
            if distance <= cluster_distance:
                nearby_count += 1

        # If at least 3 people are nearby,
        # this user is part of the party cluster.
        if nearby_count >= min_users:
            clustered_users.append(user)

    return clustered_users


# --------------------------------------------------
# FIND PARTY CENTER
# --------------------------------------------------

def find_party_center(users):

    # Can't find a center without users.
    if len(users) == 0:
        return None

    total_x = 0
    total_y = 0

    # Add all user positions.
    for user in users:

        total_x += user["x"]
        total_y += user["y"]

    # Find average X and Y position.
    center_x = total_x / len(users)
    center_y = total_y / len(users)

    return center_x, center_y


# --------------------------------------------------
# CALCULATE PARTY RADIUS
# --------------------------------------------------

def calculate_party_radius(
    users,
    center_x,
    center_y
):

    if len(users) == 0:
        return 0

    distances = []

    # Find distance of every party member
    # from the calculated party center.
    for user in users:

        distance = distance_from_party(
            user["x"],
            user["y"],
            center_x,
            center_y
        )

        distances.append(distance)

    # Furthest party member gives us the
    # detected size of the cluster.
    detected_radius = max(distances)

    # Don't allow our party area to become
    # smaller than 30 meters.
    party_radius = max(
        detected_radius,
        MIN_PARTY_RADIUS
    )

    return party_radius


# --------------------------------------------------
# DETERMINE IF USER IS WANDERING
# --------------------------------------------------

def wandering_status(
    distance,
    party_radius
):

    warning_radius = (
        party_radius
        +
        WARNING_BUFFER
    )

    alert_radius = (
        party_radius
        +
        ALERT_BUFFER
    )

    # User is still within party area.
    if distance <= party_radius:

        return "INSIDE_PARTY"

    # User has left the main party,
    # but isn't far enough away for an alert.
    elif distance <= warning_radius:

        return "BUFFER_ZONE"

    # User is getting unusually far away.
    elif distance <= alert_radius:

        return "WANDERING"

    # User is far beyond the party.
    else:

        return "FAR_FROM_PARTY"


# --------------------------------------------------
# ARCHIMEDEAN SPIRAL SEARCH
# --------------------------------------------------

def spiral_search():

    # We will build the spiral/search-time
    # calculation after the geofence works.

    pass


# ==================================================
# LIVE GPS CALCULATIONS
# ==================================================

def calculate_movement(
    old_latitude,
    old_longitude,
    new_latitude,
    new_longitude
):

    # Treat the old GPS position as (0, 0).
    # Convert the new GPS position into meters
    # away from the old position.

    x, y = gps_to_xy(
        new_latitude,
        new_longitude,
        old_latitude,
        old_longitude
    )

    # Calculate straight-line movement.
    distance = distance_from_party(
        x,
        y,
        0,
        0
    )

    return distance


# --------------------------------------------------
# MAIN LIVE LOCATION ALGORITHM
# --------------------------------------------------

def analyze_location(latitude, longitude):

    global previous_location
    global total_distance_traveled

    # Make sure incoming values are numbers.
    latitude = float(latitude)
    longitude = float(longitude)

    print("\n================================")
    print("LIVE LOCATION RECEIVED")
    print("================================")

    print("Latitude:", latitude)
    print("Longitude:", longitude)


    # ----------------------------------------------
    # FIRST GPS READING
    # ----------------------------------------------

    if previous_location is None:

        previous_location = {
            "latitude": latitude,
            "longitude": longitude
        }

        print("First GPS position saved.")
        print("Waiting for movement...")

        return {
            "latitude": latitude,
            "longitude": longitude,
            "distance_moved": 0,
            "total_distance": 0,
            "message": "First GPS position saved"
        }


    # ----------------------------------------------
    # GET PREVIOUS POSITION
    # ----------------------------------------------

    old_latitude = previous_location["latitude"]
    old_longitude = previous_location["longitude"]


    # ----------------------------------------------
    # CALCULATE MOVEMENT
    # ----------------------------------------------

    distance_moved = calculate_movement(
        old_latitude,
        old_longitude,
        latitude,
        longitude
    )


    # ----------------------------------------------
    # UPDATE TOTAL DISTANCE
    # ----------------------------------------------

    total_distance_traveled += distance_moved


    # ----------------------------------------------
    # PRINT RESULTS
    # ----------------------------------------------

    print(
        "Previous location:",
        old_latitude,
        old_longitude
    )

    print(
        "Current location:",
        latitude,
        longitude
    )

    print(
        "Distance since last update:",
        round(distance_moved, 2),
        "meters"
    )

    print(
        "Total distance traveled:",
        round(total_distance_traveled, 2),
        "meters"
    )


    # ----------------------------------------------
    # SAVE CURRENT POSITION FOR NEXT UPDATE
    # ----------------------------------------------

    previous_location = {
        "latitude": latitude,
        "longitude": longitude
    }


    # ----------------------------------------------
    # SEND RESULTS BACK TO FLASK
    # ----------------------------------------------

    return {
        "latitude": latitude,
        "longitude": longitude,

        "previous_latitude": old_latitude,
        "previous_longitude": old_longitude,

        "distance_moved": round(
            distance_moved,
            2
        ),

        "total_distance": round(
            total_distance_traveled,
            2
        ),

        "message": "Live location analyzed successfully"
    }


# ==================================================
# TESTING
# ==================================================

if __name__ == "__main__":

    print("\n================================")
    print("GPS CALCULATION TEST")
    print("================================")

    # Fake party location
    party_lat = 39.981000
    party_lon = -75.154000

    # Fake user's location
    user_lat = 39.981234
    user_lon = -75.153456

    # Party is our reference point (0, 0)
    party_x = 0
    party_y = 0

    # Convert user's GPS coordinates to X/Y meters.
    user_x, user_y = gps_to_xy(
        user_lat,
        user_lon,
        party_lat,
        party_lon
    )

    # Calculate straight-line distance from party.
    party_distance = distance_from_party(
        user_x,
        user_y,
        party_x,
        party_y
    )

    print(
        "User X:",
        round(user_x, 2),
        "meters"
    )

    print(
        "User Y:",
        round(user_y, 2),
        "meters"
    )

    print(
        "Straight-line distance from party:",
        round(party_distance, 2),
        "meters"
    )


    # --------------------------------------------------
    # PARTY DETECTION TEST
    # --------------------------------------------------

    print("\n================================")
    print("PARTY DETECTION TEST")
    print("================================")

    users = [

        {
            "id": 1,
            "x": 0,
            "y": 0
        },

        {
            "id": 2,
            "x": 8,
            "y": 5
        },

        {
            "id": 3,
            "x": -6,
            "y": 4
        },

        {
            "id": 4,
            "x": 40,
            "y": 0
        },

        {
            "id": 5,
            "x": 70,
            "y": 0
        }

    ]


    # Detect party members.
    party_users = detect_party_cluster(
        users
    )

    print(
        "Users detected as party members:",
        [user["id"] for user in party_users]
    )


    # If enough users exist, calculate party information.
    if len(party_users) >= MIN_PARTY_USERS:

        print("\nPARTY DETECTED!")

        party_center = find_party_center(
            party_users
        )

        party_x = party_center[0]
        party_y = party_center[1]

        print(
            "Party center:",
            round(party_x, 2),
            round(party_y, 2)
        )

        party_radius = calculate_party_radius(
            party_users,
            party_x,
            party_y
        )

        print(
            "Party radius:",
            round(party_radius, 2),
            "meters"
        )

        print(
            "Warning boundary:",
            round(
                party_radius + WARNING_BUFFER,
                2
            ),
            "meters"
        )

        print(
            "Alert boundary:",
            round(
                party_radius + ALERT_BUFFER,
                2
            ),
            "meters"
        )


        print("\n================================")
        print("USER LOCATION STATUS")
        print("================================")

        for user in users:

            distance = distance_from_party(
                user["x"],
                user["y"],
                party_x,
                party_y
            )

            status = wandering_status(
                distance,
                party_radius
            )

            print(
                "User",
                user["id"],
                "| Distance:",
                round(distance, 2),
                "meters",
                "| Status:",
                status
            )

    else:

        print(
            "No party detected."
        )