"""Tracks parties: groups of phones that are together.

How the geofence works with any number of phones:

- A party forms when MIN_PARTY_USERS phones are chained together
  within CLUSTER_DISTANCE. Separate groups form separate parties.
- The circle is the median position of the members currently
  inside it, with radius RADIUS_SCALE x their median distance
  (kept between MIN_PARTY_RADIUS and MAX_PARTY_RADIUS). Medians
  mean one person walking away can't drag the circle along.
- The circle only adapts while ADAPT_MIN_USERS or more members
  are inside it. With just two, there is no way to tell who
  wandered, so the circle stays where it was founded.
- Changes are smoothed over SMOOTHING_SECONDS so GPS jumps don't
  make the circle jitter, but a group that walks somewhere
  together takes the circle with it.
- Parties whose circles overlap are merged into one.
- A party ends after PARTY_IDLE_SECONDS without at least
  MIN_PARTY_USERS fresh members inside it.

State lives in memory, so restarting the server clears parties.
"""

import math
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime

from calculations import (
    gps_to_xy,
    xy_to_gps,
    distance_from_party,
    find_clusters,
    robust_center,
    robust_radius,
    confident_distance,
    wandering_status,
    MIN_PARTY_USERS,
)


# A location older than this no longer counts toward a party.
FRESH_SECONDS = 120

# Readings with worse accuracy than this don't shape parties.
MAX_ACCURACY = 100  # meters

# Members needed inside the circle before it can move or resize.
ADAPT_MIN_USERS = 3

# How quickly the circle catches up to where the group is.
SMOOTHING_SECONDS = 30

# A party with too few members together for this long ends.
PARTY_IDLE_SECONDS = 15 * 60


@dataclass
class Party:
    id: str
    center_latitude: float
    center_longitude: float
    radius: float
    created_at: datetime
    last_active: datetime
    last_adjusted: datetime
    member_ids: set = field(default_factory=set)
    founder_ids: list = field(default_factory=list)
    # People who chose to leave aren't pulled back in just
    # because they are still standing inside the circle.
    left_ids: set = field(default_factory=set)

    def to_xy(self, location):
        return gps_to_xy(
            location["latitude"],
            location["longitude"],
            self.center_latitude,
            self.center_longitude
        )

    def distance_to(self, location):
        x, y = self.to_xy(location)
        return distance_from_party(x, y, 0, 0)

    def to_public_dict(self):
        return {
            "id": self.id,
            "center": {
                "latitude": round(self.center_latitude, 7),
                "longitude": round(self.center_longitude, 7),
            },
            "radius": round(self.radius, 2),
            "memberCount": len(self.member_ids),
        }


def is_usable(location):
    accuracy = location.get("accuracy")
    return accuracy is None or accuracy <= MAX_ACCURACY


class PartyTracker:

    def __init__(self):
        self.parties = {}
        # Flask serves requests on several threads.
        self.lock = threading.Lock()

    # ----------------------------------------------
    # Lookups
    # ----------------------------------------------

    def party_for(self, user_id):
        for party in self.parties.values():
            if user_id in party.member_ids:
                return party
        return None

    def status_for(self, user_id, location):
        """Where a user stands relative to their party."""

        with self.lock:
            party = self.party_for(user_id)

            if not party or not location:
                return {
                    "party": None,
                    "status": "NOT_IN_PARTY",
                    "distanceFromParty": None,
                }

            distance = party.distance_to(location)

            return {
                "party": party.to_public_dict(),
                "status": wandering_status(
                    confident_distance(
                        distance,
                        location.get("accuracy")
                    ),
                    party.radius
                ),
                "distanceFromParty": round(distance, 2),
            }

    # ----------------------------------------------
    # Changes
    # ----------------------------------------------

    def leave(self, user_id):
        with self.lock:
            party = self.party_for(user_id)
            if party:
                party.member_ids.discard(user_id)
                party.left_ids.add(user_id)

    def expire(self, now):
        with self.lock:
            self._expire(now)

    def update(self, locations, now):
        """Recalculate parties from everyone's latest location.

        locations: list of dicts with id, latitude, longitude,
        accuracy (meters or None) and age_seconds.
        """

        fresh = {
            location["id"]: location
            for location in locations
            if location["age_seconds"] <= FRESH_SECONDS
            and is_usable(location)
        }

        with self.lock:
            self._adjust_parties(fresh, now)
            self._expire(now)
            self._join_parties(fresh)
            self._form_parties(fresh, now)
            self._merge_parties(fresh)

    def _adjust_parties(self, fresh, now):

        for party in self.parties.values():

            inside = []

            for member_id in party.member_ids:
                location = fresh.get(member_id)
                if not location:
                    continue

                x, y = party.to_xy(location)
                if distance_from_party(x, y, 0, 0) <= party.radius:
                    inside.append({"x": x, "y": y})

            if len(inside) >= MIN_PARTY_USERS:
                party.last_active = now

            if len(inside) < ADAPT_MIN_USERS:
                continue

            # The current center is (0, 0) in these coordinates,
            # so the target center is also the offset to move.
            target_x, target_y = robust_center(inside)
            target_radius = robust_radius(inside, target_x, target_y)

            # Move part of the way based on elapsed time, so the
            # speed doesn't depend on how often phones report.
            elapsed = (now - party.last_adjusted).total_seconds()
            weight = 1 - math.exp(-elapsed / SMOOTHING_SECONDS)

            party.center_latitude, party.center_longitude = xy_to_gps(
                target_x * weight,
                target_y * weight,
                party.center_latitude,
                party.center_longitude
            )
            party.radius += (target_radius - party.radius) * weight
            party.last_adjusted = now

    def _expire(self, now):

        for party_id, party in list(self.parties.items()):
            idle = (now - party.last_active).total_seconds()
            if idle > PARTY_IDLE_SECONDS or not party.member_ids:
                del self.parties[party_id]

    def _join_parties(self, fresh):

        for user_id, location in fresh.items():

            if self.party_for(user_id):
                continue

            # Join the closest party whose circle they are in.
            best = None
            best_distance = None

            for party in self.parties.values():
                if user_id in party.left_ids:
                    continue

                distance = party.distance_to(location)
                if distance <= party.radius and (
                    best is None or distance < best_distance
                ):
                    best = party
                    best_distance = distance

            if best:
                best.member_ids.add(user_id)

    def _form_parties(self, fresh, now):

        loners = [
            location
            for user_id, location in fresh.items()
            if not self.party_for(user_id)
        ]

        if len(loners) < MIN_PARTY_USERS:
            return

        reference = loners[0]

        points = []
        for location in loners:
            x, y = gps_to_xy(
                location["latitude"],
                location["longitude"],
                reference["latitude"],
                reference["longitude"]
            )
            points.append({"id": location["id"], "x": x, "y": y})

        for group in find_clusters(points):

            center_x, center_y = robust_center(group)
            center_latitude, center_longitude = xy_to_gps(
                center_x,
                center_y,
                reference["latitude"],
                reference["longitude"]
            )

            member_ids = [point["id"] for point in group]

            party = Party(
                id=secrets.token_hex(8),
                center_latitude=center_latitude,
                center_longitude=center_longitude,
                radius=robust_radius(group, center_x, center_y),
                created_at=now,
                last_active=now,
                last_adjusted=now,
                member_ids=set(member_ids),
                founder_ids=member_ids,
            )

            self.parties[party.id] = party

            print(
                "PARTY FORMED:",
                party.id,
                "| members:", len(member_ids),
                "| radius:", round(party.radius, 1), "m",
                flush=True
            )

    def _merge_parties(self, fresh):

        # A spread-out crowd can form two parties whose circles
        # overlap. That is really one event, so combine them.
        merged = True

        while merged:
            merged = False
            parties = sorted(
                self.parties.values(),
                key=lambda party: party.created_at
            )

            for index, older in enumerate(parties):
                for newer in parties[index + 1:]:

                    gap = older.distance_to({
                        "latitude": newer.center_latitude,
                        "longitude": newer.center_longitude,
                    })

                    if gap < older.radius + newer.radius:
                        self._combine(older, newer, fresh)
                        merged = True
                        break

                if merged:
                    break

    def _combine(self, older, newer, fresh):

        older.member_ids |= newer.member_ids
        older.founder_ids += newer.founder_ids
        older.left_ids |= newer.left_ids
        older.last_active = max(older.last_active, newer.last_active)
        del self.parties[newer.id]

        points = []
        for member_id in older.member_ids:
            location = fresh.get(member_id)
            if location:
                x, y = older.to_xy(location)
                points.append({"x": x, "y": y})

        if len(points) < MIN_PARTY_USERS:
            return

        center_x, center_y = robust_center(points)
        older.radius = robust_radius(points, center_x, center_y)
        older.center_latitude, older.center_longitude = xy_to_gps(
            center_x,
            center_y,
            older.center_latitude,
            older.center_longitude
        )

        print("PARTIES MERGED into", older.id, flush=True)
