"""Explicit party geofence tracking.

Earlier versions of FriendsNMe formed parties automatically by looking
for nearby phones. Phase 1 parties are explicit: the database decides who
belongs to a party, and this module only calculates that one party's
geofence from those members' fresh shared locations.

The math still comes from calculations.py: GPS points are converted to
meters, the center/radius use median-based robust calculations, stale
locations are ignored, GPS accuracy is considered before warning, and
members receive INSIDE_PARTY / BUFFER_ZONE / WANDERING /
FAR_FROM_PARTY statuses.
"""

import math
import threading
from dataclasses import dataclass
from datetime import datetime

from calculations import (
    gps_to_xy,
    xy_to_gps,
    distance_from_party,
    robust_center,
    robust_radius,
    confident_distance,
    wandering_status,
    MIN_PARTY_USERS,
    MIN_PARTY_RADIUS,
)


# A location older than this no longer counts toward a party.
FRESH_SECONDS = 120

# Readings with worse accuracy than this don't shape parties.
MAX_ACCURACY = 100  # meters

# Members needed inside the circle before it can move or resize.
ADAPT_MIN_USERS = 3

# How quickly the circle catches up to where the group is.
SMOOTHING_SECONDS = 30


@dataclass
class PartyState:
    id: str
    center_latitude: float
    center_longitude: float
    radius: float
    created_at: datetime
    last_adjusted: datetime
    member_count: int = 0

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
            "memberCount": self.member_count,
        }


def is_usable(location):
    accuracy = location.get("accuracy")
    return accuracy is None or accuracy <= MAX_ACCURACY


def is_fresh(location):
    return (
        location.get("age_seconds") is not None
        and location["age_seconds"] <= FRESH_SECONDS
        and is_usable(location)
    )


class PartyTracker:
    """Keeps short-lived geofence state for explicit Party records."""

    def __init__(self):
        self.states = {}
        self.lock = threading.Lock()

    def reset(self):
        with self.lock:
            self.states.clear()

    def forget(self, party_id):
        with self.lock:
            self.states.pop(party_id, None)

    def snapshot(self, party_id, locations, now):
        """Return geofence and member statuses for one explicit party.

        locations must already be permission-filtered by the caller. The
        tracker never looks up users or memberships on its own.
        """

        fresh_locations = [
            location
            for location in locations
            if is_fresh(location)
        ]

        with self.lock:
            if not fresh_locations:
                return None

            state = self.states.get(party_id)

            if state is None:
                state = self._create_state(
                    party_id,
                    fresh_locations,
                    now
                )
                self.states[party_id] = state
            else:
                self._adjust_state(
                    state,
                    fresh_locations,
                    now
                )

            state.member_count = len(locations)

            statuses = {}

            for location in fresh_locations:
                distance = state.distance_to(location)
                statuses[location["id"]] = {
                    "status": wandering_status(
                        confident_distance(
                            distance,
                            location.get("accuracy")
                        ),
                        state.radius
                    ),
                    "distanceFromParty": round(distance, 2),
                }

            return {
                "geofence": state.to_public_dict(),
                "statuses": statuses,
            }

    def _create_state(self, party_id, fresh_locations, now):
        reference = fresh_locations[0]
        points = self._points_from_reference(
            fresh_locations,
            reference["latitude"],
            reference["longitude"]
        )

        center_x, center_y = robust_center(points)
        center_latitude, center_longitude = xy_to_gps(
            center_x,
            center_y,
            reference["latitude"],
            reference["longitude"]
        )

        if len(points) >= MIN_PARTY_USERS:
            radius = robust_radius(points, center_x, center_y)
        else:
            radius = MIN_PARTY_RADIUS

        return PartyState(
            id=party_id,
            center_latitude=center_latitude,
            center_longitude=center_longitude,
            radius=radius,
            created_at=now,
            last_adjusted=now,
            member_count=len(fresh_locations),
        )

    def _adjust_state(self, state, fresh_locations, now):
        points = []
        inside = []

        for location in fresh_locations:
            x, y = state.to_xy(location)
            point = {
                "id": location["id"],
                "x": x,
                "y": y,
            }
            points.append(point)

            if distance_from_party(x, y, 0, 0) <= state.radius:
                inside.append(point)

        # A one-person explicit party should follow that person until
        # more people are actively sharing. With larger groups, avoid
        # letting one wandering phone drag the circle.
        if state.member_count <= 1 and len(points) == 1:
            state.center_latitude = fresh_locations[0]["latitude"]
            state.center_longitude = fresh_locations[0]["longitude"]
            state.radius = MIN_PARTY_RADIUS
            state.last_adjusted = now
            return

        if len(inside) < ADAPT_MIN_USERS:
            return

        target_x, target_y = robust_center(inside)
        target_radius = robust_radius(inside, target_x, target_y)

        elapsed = (now - state.last_adjusted).total_seconds()
        weight = 1 - math.exp(-elapsed / SMOOTHING_SECONDS)

        state.center_latitude, state.center_longitude = xy_to_gps(
            target_x * weight,
            target_y * weight,
            state.center_latitude,
            state.center_longitude
        )
        state.radius += (target_radius - state.radius) * weight
        state.last_adjusted = now

    def _points_from_reference(
        self,
        locations,
        reference_latitude,
        reference_longitude
    ):
        points = []

        for location in locations:
            x, y = gps_to_xy(
                location["latitude"],
                location["longitude"],
                reference_latitude,
                reference_longitude
            )

            points.append({
                "id": location["id"],
                "x": x,
                "y": y,
            })

        return points
