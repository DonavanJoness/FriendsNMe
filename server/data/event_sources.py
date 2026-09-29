"""Destination/event input helpers.

FriendsNMe does not scrape TU Parties or try to access private event
data. These classes only normalize information the user typed or pasted
into FriendsNMe. If TU Parties later provides an approved API, the rest
of the app can keep using the same destination shape.
"""


class EventSource:
    source_name = "manual"

    def build_destination(self, data):
        return {
            "name": clean_text(data.get("name"), 120),
            "address": clean_text(data.get("address"), 240),
            "latitude": parse_optional_float(data.get("latitude")),
            "longitude": parse_optional_float(data.get("longitude")),
            "start_time": clean_text(data.get("startTime"), 40),
            "source": self.source_name,
            "source_url": clean_text(data.get("sourceUrl"), 500),
        }


class ManualEventSource(EventSource):
    source_name = "manual"


class TUPartiesSource(EventSource):
    source_name = "tuparties"


def clean_text(value, max_length):
    text = " ".join(str(value or "").strip().split())
    if not text:
        return None
    if len(text) > max_length:
        raise ValueError(f"Text must be {max_length} characters or fewer.")
    return text


def parse_optional_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Latitude and longitude must be numbers.") from error


def normalize_destination(data):
    if not isinstance(data, dict):
        return None

    source = str(data.get("source") or "manual").strip().lower()
    if source in ("tu parties", "tuparties", "tu_parties"):
        event_source = TUPartiesSource()
    else:
        event_source = ManualEventSource()

    destination = event_source.build_destination(data)

    if (
        destination["latitude"] is not None
        and not -90 <= destination["latitude"] <= 90
    ):
        raise ValueError("Destination latitude is out of range.")

    if (
        destination["longitude"] is not None
        and not -180 <= destination["longitude"] <= 180
    ):
        raise ValueError("Destination longitude is out of range.")

    url = destination["source_url"]
    if url and not (
        url.startswith("https://")
        or url.startswith("http://")
    ):
        raise ValueError("Destination URL must start with http:// or https://.")

    has_any_value = any(
        destination[key] is not None
        for key in (
            "name",
            "address",
            "latitude",
            "longitude",
            "start_time",
            "source_url",
        )
    )

    if not has_any_value:
        return None

    return destination
