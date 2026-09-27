// Map, location tracking and party display. Loaded after index.js,
// whose api() helper it uses to talk to Flask.

// Send our location at most every 10 s, unless we moved 10 m.
const SEND_INTERVAL_MS = 10000;
const SEND_MIN_MOVE_METERS = 10;
// Refresh friends and party status this often while signed in.
const POLL_INTERVAL_MS = 10000;

const STATUS_INFO = {
  INSIDE_PARTY: { label: "Inside the party", tone: "inside" },
  BUFFER_ZONE: { label: "Near the edge of the party", tone: "buffer" },
  WANDERING: { label: "Wandering from the party", tone: "wandering" },
  FAR_FROM_PARTY: { label: "Far from the party", tone: "far" },
  NOT_IN_PARTY: { label: "Not in a party", tone: "none" },
};

const mapEls = {
  locationButton: document.getElementById("locationButton"),
  locationText: document.getElementById("locationText"),
  partyStatus: document.getElementById("partyStatus"),
  partyStatusLabel: document.getElementById("partyStatusLabel"),
  partyStatusDetail: document.getElementById("partyStatusDetail"),
  leaveParty: document.getElementById("leaveParty"),
  friendsList: document.getElementById("friendsList"),
  friendsCount: document.getElementById("friendsCount"),
};

// Circle colors come from the --status-* tokens in style.css.
function toneColor(tone) {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(`--status-${tone}`)
    .trim();
}

// ==================================================
// MAP
// ==================================================

// OpenFreeMap (MapLibre GL) - MapLibre uses [lng, lat] order
const map = new maplibregl.Map({
  container: "map",
  style: "https://tiles.openfreemap.org/styles/dark",
  center: [-75.16, 39.98],
  zoom: 14,
});
map.addControl(new maplibregl.NavigationControl());

let mapLoaded = false;
let latestData = null;

map.on("load", () => {
  // Make all labels (street names, places, etc.) white
  for (const layer of map.getStyle().layers) {
    if (layer.type === "symbol" && layer.layout && layer.layout["text-field"]) {
      map.setPaintProperty(layer.id, "text-color", "#ffffff");
      map.setPaintProperty(layer.id, "text-halo-color", "rgba(0, 0, 0, 0.85)");
    }
  }

  map.addSource("party", { type: "geojson", data: emptyCollection() });
  map.addLayer({
    id: "party-fill",
    type: "fill",
    source: "party",
    paint: { "fill-color": toneColor("inside"), "fill-opacity": 0.15 },
  });
  map.addLayer({
    id: "party-outline",
    type: "line",
    source: "party",
    paint: { "line-color": toneColor("inside"), "line-width": 2 },
  });

  mapLoaded = true;
  if (latestData) renderParty(latestData.me);
});

function emptyCollection() {
  return { type: "FeatureCollection", features: [] };
}

// A circle in meters drawn as a 64-sided polygon.
function circlePolygon(latitude, longitude, radiusMeters, steps = 64) {
  const metersPerDegreeLat = 111320;
  const metersPerDegreeLng = 111320 * Math.cos((latitude * Math.PI) / 180);
  const ring = [];

  for (let i = 0; i <= steps; i++) {
    const angle = (i / steps) * 2 * Math.PI;
    ring.push([
      longitude + (radiusMeters * Math.cos(angle)) / metersPerDegreeLng,
      latitude + (radiusMeters * Math.sin(angle)) / metersPerDegreeLat,
    ]);
  }

  return {
    type: "Feature",
    properties: {},
    geometry: { type: "Polygon", coordinates: [ring] },
  };
}

function metersBetween(a, b) {
  const x = (b.longitude - a.longitude) * 111320 * Math.cos((a.latitude * Math.PI) / 180);
  const y = (b.latitude - a.latitude) * 111320;
  return Math.hypot(x, y);
}

function timeAgo(seconds) {
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} d ago`;
}

// ==================================================
// TRACKING MY LOCATION
// ==================================================

const userMarker = new maplibregl.Marker();
let userMarkerAdded = false;
let watchId = null;
let lastSent = null;

function getLocation() {
  // If we're already tracking, pressing the button stops tracking.
  if (watchId !== null) {
    stopTracking();
    return;
  }

  // Phones only allow location on https pages (or localhost).
  if (!window.isSecureContext) {
    mapEls.locationText.textContent =
      "Location only works over https or on localhost. See the README for testing on a phone.";
    return;
  }

  if (!navigator.geolocation) {
    mapEls.locationText.textContent = "Geolocation is not supported by this browser.";
    return;
  }

  mapEls.locationText.textContent = "Requesting location...";
  watchId = navigator.geolocation.watchPosition(success, error, {
    enableHighAccuracy: true,
    maximumAge: 5000,
    // If the phone cannot get GPS within 10 seconds, call error().
    timeout: 10000,
  });
  mapEls.locationButton.textContent = "Stop tracking";
}

function stopTracking(message = "Location tracking stopped.") {
  if (watchId !== null) {
    navigator.geolocation.clearWatch(watchId);
  }
  watchId = null;
  lastSent = null;
  mapEls.locationButton.textContent = "Use my location";
  mapEls.locationText.textContent = message;
}

function success(position) {
  const current = {
    latitude: position.coords.latitude,
    longitude: position.coords.longitude,
    accuracy: position.coords.accuracy,
  };

  mapEls.locationText.textContent =
    `Sharing your location (accurate to about ${Math.round(current.accuracy)} m).`;

  userMarker.setLngLat([current.longitude, current.latitude]);
  if (!userMarkerAdded) {
    userMarker.addTo(map);
    userMarkerAdded = true;
    // Only jump to the user on the first fix so the map doesn't
    // yank away while they are looking at a friend.
    map.easeTo({ center: [current.longitude, current.latitude], zoom: 16 });
  }

  const now = Date.now();
  const recentlySent = lastSent && now - lastSent.time < SEND_INTERVAL_MS;
  const barelyMoved = lastSent && metersBetween(lastSent, current) < SEND_MIN_MOVE_METERS;
  if (recentlySent && barelyMoved) return;

  lastSent = { ...current, time: now };

  api("/location", current)
    .then(render)
    .catch((sendError) => {
      console.error("Error sending location to Flask:", sendError);
      mapEls.locationText.textContent = sendError.message;
    });
}

function error(err) {
  console.error("Geolocation error:", err);
  stopTracking(`Location error ${err.code}: ${err.message}`);
}

mapEls.locationButton.addEventListener("click", getLocation);

// ==================================================
// PARTY AND FRIENDS
// ==================================================

function render(data) {
  latestData = data;
  renderParty(data.me);
  renderStatus(data.me);
  renderFriends(data.friends, data.freshSeconds);
  frameOnce(data);
}

// On the first load, zoom to the party and friends. After that the
// user controls the map (tracking also centers on the first fix).
let hasFramed = false;

function frameOnce(data) {
  if (hasFramed || userMarkerAdded) return;

  const points = data.friends
    .filter((friend) => friend.location)
    .map((friend) => [friend.location.longitude, friend.location.latitude]);
  if (data.me.party) {
    points.push([data.me.party.center.longitude, data.me.party.center.latitude]);
  }
  if (points.length === 0) return;

  hasFramed = true;
  const bounds = new maplibregl.LngLatBounds(points[0], points[0]);
  points.forEach((point) => bounds.extend(point));
  map.fitBounds(bounds, { padding: 60, maxZoom: 17, duration: 0 });
}

function renderParty(me) {
  if (!mapLoaded) return;

  const source = map.getSource("party");
  if (!me || !me.party) {
    source.setData(emptyCollection());
    return;
  }

  const { center, radius } = me.party;
  const color = toneColor(STATUS_INFO[me.status].tone);

  source.setData({
    type: "FeatureCollection",
    features: [circlePolygon(center.latitude, center.longitude, radius)],
  });
  map.setPaintProperty("party-fill", "fill-color", color);
  map.setPaintProperty("party-outline", "line-color", color);
}

function renderStatus(me) {
  const info = STATUS_INFO[me.status];

  mapEls.partyStatus.hidden = false;
  mapEls.partyStatus.dataset.tone = info.tone;
  mapEls.partyStatusLabel.textContent = info.label;
  mapEls.leaveParty.hidden = !me.party;

  if (me.party) {
    const people = me.party.memberCount === 1 ? "1 person" : `${me.party.memberCount} people`;
    mapEls.partyStatusDetail.textContent =
      `${Math.round(me.distanceFromParty)} m from the center · ` +
      `${Math.round(me.party.radius)} m radius · ${people}`;
  } else if (watchId === null) {
    mapEls.partyStatusDetail.textContent =
      "Press “Use my location” to find your party.";
  } else {
    mapEls.partyStatusDetail.textContent =
      "A party starts when you and someone else are within 30 m of each other.";
  }
}

function friendDetail(friend, freshSeconds) {
  if (!friend.location) return "Hasn't shared a location yet";

  const ago = timeAgo(friend.ageSeconds);
  if (friend.ageSeconds > freshSeconds) return `Last seen ${ago}`;
  if (friend.status === "NOT_IN_PARTY") return `Not in a party · ${ago}`;
  if (!friend.sameParty) return `At another party · ${ago}`;
  return `${STATUS_INFO[friend.status].label} · ${ago}`;
}

function friendTone(friend, freshSeconds) {
  if (!friend.location || friend.ageSeconds > freshSeconds) return "none";
  return STATUS_INFO[friend.status].tone;
}

const friendMarkers = new Map();

function renderFriends(friends, freshSeconds) {
  mapEls.friendsCount.textContent = friends.length === 1
    ? "1 person shares their location with you"
    : `${friends.length} people share their location with you`;

  mapEls.friendsList.replaceChildren();

  if (friends.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-share-state";
    empty.textContent =
      "Nobody shares their location with you yet. Friends add you from their Sharing page.";
    mapEls.friendsList.appendChild(empty);
  }

  const seen = new Set();

  friends.forEach((friend) => {
    const detail = friendDetail(friend, freshSeconds);
    const tone = friendTone(friend, freshSeconds);
    const stale = tone === "none";

    // --- Panel row (click to find them on the map) ---
    const row = document.createElement("button");
    row.type = "button";
    row.className = "shared-account-row friend-row";
    row.dataset.tone = tone;
    row.classList.toggle("is-stale", stale);
    row.disabled = !friend.location;

    const info = document.createElement("div");
    info.className = "friend-info";

    const avatar = document.createElement("span");
    avatar.className = "friend-avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = friend.username.charAt(0).toUpperCase();

    const text = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = friend.username;
    const status = document.createElement("span");
    status.textContent = detail;
    text.append(name, status);

    info.append(avatar, text);
    row.appendChild(info);
    mapEls.friendsList.appendChild(row);

    if (!friend.location) return;

    const lngLat = [friend.location.longitude, friend.location.latitude];
    row.addEventListener("click", () => {
      map.flyTo({ center: lngLat, zoom: 17 });
      friendMarkers.get(friend.id)?.togglePopup();
    });

    // --- Map marker ---
    seen.add(friend.id);
    let marker = friendMarkers.get(friend.id);

    if (!marker) {
      const element = document.createElement("div");
      element.className = "friend-marker";
      element.textContent = friend.username.charAt(0).toUpperCase();

      marker = new maplibregl.Marker({ element })
        .setLngLat(lngLat)
        .setPopup(new maplibregl.Popup({ offset: 18, closeButton: false }))
        .addTo(map);
      friendMarkers.set(friend.id, marker);
    }

    const element = marker.getElement();
    element.dataset.tone = tone;
    element.classList.toggle("is-stale", stale);
    element.setAttribute("aria-label", `${friend.username}: ${detail}`);
    marker.setLngLat(lngLat);
    marker.getPopup().setText(`${friend.username} · ${detail}`);
  });

  // Remove markers for people who stopped sharing with us.
  for (const [id, marker] of friendMarkers) {
    if (!seen.has(id)) {
      marker.remove();
      friendMarkers.delete(id);
    }
  }
}

mapEls.leaveParty.addEventListener("click", () => {
  mapEls.leaveParty.disabled = true;
  api("/api/party/leave", {})
    .then(render)
    .catch((leaveError) => {
      mapEls.locationText.textContent = leaveError.message;
    })
    .finally(() => {
      mapEls.leaveParty.disabled = false;
    });
});

// ==================================================
// SIGN IN / SIGN OUT (events come from index.js)
// ==================================================

let pollTimer = null;

function refresh() {
  api("/api/map")
    .then(render)
    .catch((refreshError) => {
      // Signed out elsewhere; index.js handles showing the login.
      if (refreshError.status === 401) stopPolling();
    });
}

function startPolling() {
  if (pollTimer !== null) return;
  refresh();
  pollTimer = setInterval(refresh, POLL_INTERVAL_MS);
}

function stopPolling() {
  clearInterval(pollTimer);
  pollTimer = null;
}

document.addEventListener("friendsnme:signed-in", startPolling);

document.addEventListener("friendsnme:signed-out", () => {
  stopPolling();
  if (watchId !== null) stopTracking("");

  latestData = null;
  hasFramed = false;
  userMarker.remove();
  userMarkerAdded = false;
  friendMarkers.forEach((marker) => marker.remove());
  friendMarkers.clear();
  renderParty(null);
  mapEls.partyStatus.hidden = true;
  mapEls.friendsList.replaceChildren();
  mapEls.friendsCount.textContent = "";
});

// In case index.js restored the session before this file loaded.
if (!document.body.classList.contains("auth-locked")) startPolling();
