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


# --------------------------------------------------
# MAIN LOCATION ALGORITHM
# --------------------------------------------------

def analyze_location(latitude, longitude):

    # Keep this for the Flask connection.
    #
    # Later this function can call the party
    # detection/wandering functions automatically.

    return {
        "latitude_received": latitude,
        "longitude_received": longitude,
        "message": "Location received successfully"
    }


# ==================================================
# TESTING
# ==================================================

if __name__ == "__main__":

    # --------------------------------------------------
    # ORIGINAL GPS TEST
    # --------------------------------------------------

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

    # Calculate taxicab distance.
    taxi_distance = taxicab_distance(
        party_x,
        party_y,
        user_x,
        user_y
    )

    print(
        "User X:",
        user_x,
        "meters"
    )

    print(
        "User Y:",
        user_y,
        "meters"
    )

    print(
        "Straight-line distance from party:",
        party_distance,
        "meters"
    )

    print(
        "Taxicab distance:",
        taxi_distance,
        "meters"
    )


    # --------------------------------------------------
    # PARTY DETECTION TEST
    # --------------------------------------------------

    print("\n================================")
    print("PARTY DETECTION TEST")
    print("================================")

    # These are fake X/Y positions in meters.
    #
    # Users 1, 2, and 3 simulate the three
    # phones establishing the party.
    #
    # Users 4 and 5 simulate people moving
    # away from the party.

    users = [

        # Party phone 1
        {
            "id": 1,
            "x": 0,
            "y": 0
        },

        # Party phone 2
        {
            "id": 2,
            "x": 8,
            "y": 5
        },

        # Party phone 3
        {
            "id": 3,
            "x": -6,
            "y": 4
        },

        # Test phone 4
        # Should be around the buffer zone.
        {
            "id": 4,
            "x": 40,
            "y": 0
        },

        # Test phone 5
        # Should be wandering.
        {
            "id": 5,
            "x": 70,
            "y": 0
        }

    ]


    # --------------------------------------------------
    # STEP 1: DETECT PARTY
    # --------------------------------------------------

    party_users = detect_party_cluster(
        users
    )

    print(
        "Users detected as party members:",
        [user["id"] for user in party_users]
    )


    # --------------------------------------------------
    # STEP 2: PARTY EXISTS?
    # --------------------------------------------------

    if len(party_users) >= MIN_PARTY_USERS:

        print("\nPARTY DETECTED!")

        # ----------------------------------------------
        # STEP 3: FIND PARTY CENTER
        # ----------------------------------------------

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


        # ----------------------------------------------
        # STEP 4: CALCULATE PARTY RADIUS
        # ----------------------------------------------

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


        # ----------------------------------------------
        # STEP 5: CHECK EVERY USER
        # ----------------------------------------------

        print("\n================================")
        print("USER LOCATION STATUS")
        print("================================")

        for user in users:

            # Calculate this person's distance
            # from the party center.
            distance = distance_from_party(
                user["x"],
                user["y"],
                party_x,
                party_y
            )

            # Determine which zone they're in.
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


    # --------------------------------------------------
    # NO PARTY FOUND
    # --------------------------------------------------

    else:

        print(
            "No party detected."
        )