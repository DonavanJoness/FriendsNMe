# calculations.py

#

def distance_from_party(pointA,pointB):
    # GPS distance / radius calculation 
    pass


def taxicab_distance(...):
    # estimate distance between two people
    pass


def spiral_search(...):
    # generate search/search-time estimate
    pass


def analyze_location(...):
    # MAIN ALGORITHM

    party_distance = distance_from_party(...)

    if party_distance <= PARTY_RADIUS:
        status = "SAFE"
    else:
        status = "OUTSIDE PARTY AREA"

    rescue_distance = taxicab_distance(...)

    search_time = spiral_search(...)

    return {
        "status": status,
        "party_distance": party_distance,
        "rescue_distance": rescue_distance,
        "search_time": search_time
    }
