import math
import statistics


# ==================================================
# SETTINGS
# ==================================================

# TEMPORARY TEST SETTING
# Change this back to 3 after testing with two phones.
MIN_PARTY_USERS = 2

# Users must be within this distance to count
# as being together.
CLUSTER_DISTANCE = 30  # meters

# Minimum size of the party geofence.
MIN_PARTY_RADIUS = 30  # meters

# Distance outside party radius before wandering warning.
WARNING_BUFFER = 25  # meters

# Distance outside party radius for stronger alert.
ALERT_BUFFER = 55  # meters

# Largest the party geofence can grow to.
MAX_PARTY_RADIUS = 150  # meters

# Radius = RADIUS_SCALE x the median member distance from the
# center. For people spread evenly over a circle, the median
# distance is about 0.7 x the circle's radius, so 1.5 puts the
# edge just outside the crowd.
RADIUS_SCALE = 1.5

# Most GPS error we give someone the benefit of the doubt for.
MAX_ACCURACY_MARGIN = 25  # meters


# ==================================================
# GPS -> X/Y METERS
# ==================================================

def gps_to_xy(
    latitude,
    longitude,
    reference_lat,
    reference_lon
):

    latitude = float(latitude)
    longitude = float(longitude)

    reference_lat = float(reference_lat)
    reference_lon = float(reference_lon)

    delta_lat = latitude - reference_lat
    delta_lon = longitude - reference_lon

    # North/South distance
    y = delta_lat * 111320

    # East/West distance
    x = (
        delta_lon
        * 111320
        * math.cos(
            math.radians(reference_lat)
        )
    )

    return x, y


# ==================================================
# STRAIGHT-LINE DISTANCE
# ==================================================

def distance_from_party(
    user_x,
    user_y,
    party_x,
    party_y
):

    delta_x = user_x - party_x
    delta_y = user_y - party_y

    distance = math.sqrt(
        delta_x ** 2
        +
        delta_y ** 2
    )

    return distance


# ==================================================
# TAXICAB DISTANCE
# ==================================================

def taxicab_distance(
    x1,
    y1,
    x2,
    y2
):

    return (
        abs(x2 - x1)
        +
        abs(y2 - y1)
    )


# ==================================================
# DETECT PARTY CLUSTER
# ==================================================

def detect_party_cluster(
    users,
    cluster_distance=CLUSTER_DISTANCE,
    min_users=MIN_PARTY_USERS
):

    clustered_users = []

    # Look at each user.
    for user in users:

        # Count themselves.
        nearby_count = 1

        # Compare against every other user.
        for other_user in users:

            if user["id"] == other_user["id"]:
                continue

            distance = distance_from_party(
                user["x"],
                user["y"],
                other_user["x"],
                other_user["y"]
            )

            if distance <= cluster_distance:
                nearby_count += 1

        # User belongs to a cluster if enough
        # people are nearby.
        if nearby_count >= min_users:

            clustered_users.append(
                user
            )

    return clustered_users


# ==================================================
# FIND PARTY CENTER
# ==================================================

def find_party_center(users):

    if len(users) == 0:
        return None

    total_x = 0
    total_y = 0

    for user in users:

        total_x += user["x"]
        total_y += user["y"]

    center_x = (
        total_x / len(users)
    )

    center_y = (
        total_y / len(users)
    )

    return center_x, center_y


# ==================================================
# CALCULATE PARTY RADIUS
# ==================================================

def calculate_party_radius(
    users,
    center_x,
    center_y
):

    if len(users) == 0:
        return 0

    distances = []

    for user in users:

        distance = distance_from_party(
            user["x"],
            user["y"],
            center_x,
            center_y
        )

        distances.append(
            distance
        )

    detected_radius = max(
        distances
    )

    # Never make the party area smaller than 30m.
    party_radius = max(
        detected_radius,
        MIN_PARTY_RADIUS
    )

    return party_radius


# ==================================================
# WANDERING STATUS
# ==================================================

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

    if distance <= party_radius:

        return "INSIDE_PARTY"

    elif distance <= warning_radius:

        return "BUFFER_ZONE"

    elif distance <= alert_radius:

        return "WANDERING"

    else:

        return "FAR_FROM_PARTY"


# ==================================================
# X/Y METERS -> GPS
# ==================================================

def xy_to_gps(
    x,
    y,
    reference_lat,
    reference_lon
):

    # Reverse of gps_to_xy.
    latitude = reference_lat + y / 111320

    longitude = reference_lon + x / (
        111320
        * math.cos(
            math.radians(reference_lat)
        )
    )

    return latitude, longitude


# ==================================================
# FIND SEPARATE GROUPS
# ==================================================

def find_clusters(
    users,
    cluster_distance=CLUSTER_DISTANCE,
    min_users=MIN_PARTY_USERS
):

    # Unlike detect_party_cluster, this keeps separate groups
    # apart. Two people are in the same group if a chain of
    # people, each within cluster_distance of the next,
    # connects them.

    groups = []
    unvisited = list(users)

    while unvisited:

        group = [unvisited.pop()]

        index = 0

        while index < len(group):

            current = group[index]

            nearby = [
                other_user
                for other_user in unvisited
                if distance_from_party(
                    current["x"],
                    current["y"],
                    other_user["x"],
                    other_user["y"]
                ) <= cluster_distance
            ]

            for other_user in nearby:
                unvisited.remove(other_user)

            group.extend(nearby)

            index += 1

        if len(group) >= min_users:
            groups.append(group)

    return groups


# ==================================================
# ROBUST CENTER AND RADIUS
# ==================================================

def robust_center(users):

    # Median instead of average: one person standing far
    # away barely moves the center.
    center_x = statistics.median(
        user["x"] for user in users
    )

    center_y = statistics.median(
        user["y"] for user in users
    )

    return center_x, center_y


def robust_radius(
    users,
    center_x,
    center_y
):

    distances = [
        distance_from_party(
            user["x"],
            user["y"],
            center_x,
            center_y
        )
        for user in users
    ]

    radius = (
        RADIUS_SCALE
        * statistics.median(distances)
    )

    return min(
        max(radius, MIN_PARTY_RADIUS),
        MAX_PARTY_RADIUS
    )


def confident_distance(
    distance,
    accuracy
):

    # Subtract the phone's GPS error so a jumpy reading
    # does not set off a wandering alert.
    margin = min(
        float(accuracy or 0),
        MAX_ACCURACY_MARGIN
    )

    return max(0.0, distance - margin)


# ==================================================
# MOVEMENT BETWEEN TWO GPS LOCATIONS
# ==================================================

def calculate_movement(
    old_latitude,
    old_longitude,
    new_latitude,
    new_longitude
):

    x, y = gps_to_xy(
        new_latitude,
        new_longitude,
        old_latitude,
        old_longitude
    )

    distance = distance_from_party(
        x,
        y,
        0,
        0
    )

    return distance


# ==================================================
# FUTURE SPIRAL SEARCH
# ==================================================

def spiral_search():

    # We'll build this after the basic
    # geofence/wandering system works.
    pass


# ==================================================
# CALCULATIONS.PY TEST
# ==================================================

if __name__ == "__main__":

    print("\n================================")
    print("FRIENDSNME CALCULATION TEST")
    print("================================")

    # Fake GPS coordinates representing two phones
    # standing close to each other.

    fake_users = [
        {
            "id": "phone1",
            "username": "Phone 1",
            "latitude": 39.981000,
            "longitude": -75.154000
        },

        {
            "id": "phone2",
            "username": "Phone 2",
            "latitude": 39.981050,
            "longitude": -75.153950
        }
    ]

    # Use Phone 1 as our (0, 0) reference.
    reference_lat = fake_users[0]["latitude"]
    reference_lon = fake_users[0]["longitude"]

    calculation_users = []

    # Convert fake GPS positions into meters.
    for user in fake_users:

        x, y = gps_to_xy(
            user["latitude"],
            user["longitude"],
            reference_lat,
            reference_lon
        )

        calculation_users.append({
            "id": user["id"],
            "username": user["username"],
            "x": x,
            "y": y
        })

        print(
            user["username"],
            "| X:",
            round(x, 2),
            "| Y:",
            round(y, 2)
        )

    # Look for a party.
    party_users = detect_party_cluster(
        calculation_users
    )

    print(
        "\nDetected party users:",
        [
            user["username"]
            for user in party_users
        ]
    )

    if len(party_users) >= MIN_PARTY_USERS:

        print("\nPARTY DETECTED!")

        party_center = find_party_center(
            party_users
        )

        party_x = party_center[0]
        party_y = party_center[1]

        party_radius = calculate_party_radius(
            party_users,
            party_x,
            party_y
        )

        print(
            "Party center:",
            round(party_x, 2),
            round(party_y, 2)
        )

        print(
            "Party radius:",
            round(party_radius, 2),
            "meters"
        )

        print(
            "Warning boundary:",
            round(
                party_radius
                +
                WARNING_BUFFER,
                2
            ),
            "meters"
        )

        print(
            "Alert boundary:",
            round(
                party_radius
                +
                ALERT_BUFFER,
                2
            ),
            "meters"
        )

        print("\n================================")
        print("USER STATUS")
        print("================================")

        for user in calculation_users:

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
                user["username"],
                "| Distance:",
                round(distance, 2),
                "meters",
                "| Status:",
                status
            )

    else:

        print("\nNO PARTY DETECTED")