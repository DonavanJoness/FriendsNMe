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
  LOCATION_PAUSED: { label: "Location sharing paused", tone: "none" },
  NO_LOCATION: { label: "No location yet", tone: "none" },
  STALE_LOCATION: { label: "Location is stale", tone: "none" },
  LOW_ACCURACY: { label: "Location accuracy is low", tone: "none" },
  NOT_IN_PARTY: { label: "Not in a party", tone: "none" },
};

const mapEls = {
  locationButton: document.getElementById("locationButton"),
  locationText: document.getElementById("locationText"),
  partyStatus: document.getElementById("partyStatus"),
  partyStatusLabel: document.getElementById("partyStatusLabel"),
  partyStatusDetail: document.getElementById("partyStatusDetail"),
  leaveParty: document.getElementById("leaveParty"),
  rejoinParty: document.getElementById("rejoinParty"),
  friendsList: document.getElementById("friendsList"),
  friendsCount: document.getElementById("friendsCount"),
  partyPanelTitle: document.getElementById("partyPanelTitle"),
  partyPanelDetail: document.getElementById("partyPanelDetail"),
  noPartyActions: document.getElementById("noPartyActions"),
  activePartyContent: document.getElementById("activePartyContent"),
  leftPartyContent: document.getElementById("leftPartyContent"),
  leftPartyText: document.getElementById("leftPartyText"),
  partyPanelMessage: document.getElementById("partyPanelMessage"),
  createPartyOpen: document.getElementById("createPartyOpen"),
  joinPartyOpen: document.getElementById("joinPartyOpen"),
  partyCodeText: document.getElementById("partyCodeText"),
  copyPartyCode: document.getElementById("copyPartyCode"),
  partyHostText: document.getElementById("partyHostText"),
  partyMemberCount: document.getElementById("partyMemberCount"),
  partyTimeLeft: document.getElementById("partyTimeLeft"),
  partyDestination: document.getElementById("partyDestination"),
  partyDestinationName: document.getElementById("partyDestinationName"),
  partyDestinationDetail: document.getElementById("partyDestinationDetail"),
  partyDestinationDistance: document.getElementById("partyDestinationDistance"),
  partyDirections: document.getElementById("partyDirections"),
  partySharingState: document.getElementById("partySharingState"),
  togglePartySharing: document.getElementById("togglePartySharing"),
  partyCheckIn: document.getElementById("partyCheckIn"),
  partyMembersList: document.getElementById("partyMembersList"),
  inviteParty: document.getElementById("inviteParty"),
  leavePartyPanel: document.getElementById("leavePartyPanel"),
  endPartyPanel: document.getElementById("endPartyPanel"),
  rejoinPartyPanel: document.getElementById("rejoinPartyPanel"),
  partyModal: document.getElementById("partyModal"),
  partyModalTitle: document.getElementById("partyModalTitle"),
  partyModalSubtitle: document.getElementById("partyModalSubtitle"),
  partyModalClose: document.getElementById("partyModalClose"),
  createPartyForm: document.getElementById("createPartyForm"),
  joinPartyForm: document.getElementById("joinPartyForm"),
  partyName: document.getElementById("partyName"),
  destinationName: document.getElementById("destinationName"),
  destinationAddress: document.getElementById("destinationAddress"),
  destinationStartTime: document.getElementById("destinationStartTime"),
  destinationLatitude: document.getElementById("destinationLatitude"),
  destinationLongitude: document.getElementById("destinationLongitude"),
  destinationUrl: document.getElementById("destinationUrl"),
  destinationIsTuParties: document.getElementById("destinationIsTuParties"),
  createShareLocation: document.getElementById("createShareLocation"),
  createPartySubmit: document.getElementById("createPartySubmit"),
  partyJoinCode: document.getElementById("partyJoinCode"),
  joinShareLocation: document.getElementById("joinShareLocation"),
  joinPartySubmit: document.getElementById("joinPartySubmit"),
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
  if (latestData) {
    renderParty(latestData.me);
    renderDestination(latestData.party);
  }
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
  if (seconds === null || seconds === undefined) return "no location yet";
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} d ago`;
}

function distanceText(meters) {
  if (meters === null || meters === undefined) return "";
  if (meters < 1609.344) return `${Math.round(meters * 3.28084)} ft`;
  const miles = meters / 1609.344;
  return `${miles.toFixed(miles < 10 ? 1 : 0)} mi`;
}

function timeRemaining(seconds) {
  if (seconds === null || seconds === undefined) return "";
  if (seconds <= 0) return "Expired";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.round((seconds % 3600) / 60);
  if (hours <= 0) return `${minutes} min`;
  if (minutes === 0) return `${hours} h`;
  return `${hours} h ${minutes} min`;
}

function memberStatusText(member) {
  const info = STATUS_INFO[member.status] || STATUS_INFO.NOT_IN_PARTY;
  if (member.status === "LOCATION_PAUSED") return "location sharing paused";
  if (member.status === "NO_LOCATION") return "no location yet";
  if (member.status === "STALE_LOCATION") return `location ${timeAgo(member.ageSeconds)} old`;
  return `${info.label.toLowerCase()} · updated ${timeAgo(member.ageSeconds)}`;
}

function destinationMapsUrl(destination) {
  if (!destination) return "";
  let target = "";
  if (destination.latitude !== null && destination.longitude !== null) {
    target = `${destination.latitude},${destination.longitude}`;
  } else if (destination.address) {
    target = destination.address;
  } else if (destination.name) {
    target = destination.name;
  }
  if (!target) return "";
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(target)}`;
}

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return true;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();

  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {
    copied = false;
  }

  textarea.remove();
  return copied;
}

function showPartyMessage(text) {
  mapEls.partyPanelMessage.textContent = text || "";
}

async function apiDelete(path) {
  const response = await fetch(path, { method: "DELETE", credentials: "same-origin" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || `Server returned HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

// ==================================================
// TRACKING MY LOCATION
// ==================================================

// GPS can take well over 10 s indoors or on a laptop, so a timeout
// only means "no reading yet": we keep watching instead of stopping.
const WATCH_OPTIONS = { enableHighAccuracy: true, maximumAge: 10000, timeout: 20000 };
// One quick, less exact reading (Wi-Fi / cell towers) so the map
// shows something while GPS warms up.
const QUICK_FIX_OPTIONS = { enableHighAccuracy: false, maximumAge: 60000, timeout: 15000 };

const userMarker = new maplibregl.Marker();
let userMarkerAdded = false;
let watchId = null;
let hasFix = false;
let lastSent = null;

function startWatch() {
  watchId = navigator.geolocation.watchPosition(success, error, WATCH_OPTIONS);
}

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
  startWatch();
  navigator.geolocation.getCurrentPosition(
    (position) => {
      // Ignore it if GPS already answered or tracking was stopped.
      if (!hasFix && watchId !== null) success(position);
    },
    () => {
      /* the watch reports real problems */
    },
    QUICK_FIX_OPTIONS
  );
  mapEls.locationButton.textContent = "Stop tracking";
}

function stopTracking(message = "Location tracking stopped.") {
  if (watchId !== null) {
    navigator.geolocation.clearWatch(watchId);
  }
  watchId = null;
  hasFix = false;
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

  hasFix = true;
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

  if (err.code === err.TIMEOUT) {
    // Not a failure: no new reading yet. Restart the watch in case
    // the browser ended it, and keep the last location on the map.
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
    startWatch();
    if (!hasFix) {
      mapEls.locationText.textContent =
        "Still looking for your location... Moving near a window or outside helps.";
    }
    return;
  }

  if (err.code === err.PERMISSION_DENIED) {
    stopTracking(
      "Location permission is blocked. Allow location for this site in your browser settings, then try again."
    );
    return;
  }

  // POSITION_UNAVAILABLE: the device couldn't work out a location.
  stopTracking(
    "Your device couldn't find a location. Make sure Location is turned on " +
      "(on Windows: Settings > Privacy & security > Location), then try again."
  );
}

mapEls.locationButton.addEventListener("click", getLocation);

// ==================================================
// PARTY AND FRIENDS
// ==================================================

function render(data) {
  latestData = data;
  renderParty(data.me);
  renderDestination(data.party);
  renderStatus(data);
  renderPartyPanel(data.party, data.me.leftParty);
  renderFriends(data.friends, data.freshSeconds);
  renderPartyMemberMarkers(data.party);
  frameOnce(data);
  checkForAlerts(data); // alerts.js
}

// On the first load, zoom to the party and friends. After that the
// user controls the map (tracking also centers on the first fix).
let hasFramed = false;

function frameOnce(data) {
  if (hasFramed || userMarkerAdded) return;

  const points = data.friends
    .filter((friend) => friend.location)
    .map((friend) => [friend.location.longitude, friend.location.latitude]);
  if (data.party) {
    data.party.members
      .filter((member) => member.location)
      .forEach((member) => points.push([member.location.longitude, member.location.latitude]));
    const destination = data.party.destination;
    if (
      destination &&
      destination.latitude !== null &&
      destination.longitude !== null
    ) {
      points.push([destination.longitude, destination.latitude]);
    }
  }
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
  // A party we left stays on the map in gray so we can find it.
  const party = me && (me.party || me.leftParty);
  if (!party) {
    source.setData(emptyCollection());
    return;
  }

  const { center, radius } = party;
  const statusInfo = STATUS_INFO[me.status] || STATUS_INFO.NOT_IN_PARTY;
  const color = toneColor(me.party ? statusInfo.tone : "none");

  source.setData({
    type: "FeatureCollection",
    features: [circlePolygon(center.latitude, center.longitude, radius)],
  });
  map.setPaintProperty("party-fill", "fill-color", color);
  map.setPaintProperty("party-outline", "line-color", color);
}

let destinationMarker = null;

function renderDestination(party) {
  if (!mapLoaded) return;

  const destination = party && party.destination;
  const hasCoordinates =
    destination &&
    destination.latitude !== null &&
    destination.longitude !== null;

  if (!hasCoordinates) {
    if (destinationMarker) {
      destinationMarker.remove();
      destinationMarker = null;
    }
    return;
  }

  const lngLat = [destination.longitude, destination.latitude];
  const popupLines = ["Party Destination"];
  if (destination.name) popupLines.push(destination.name);
  if (destination.address) popupLines.push(destination.address);
  if (destination.startTime) popupLines.push(destination.startTime);
  if (party.myDistanceToDestination !== null) {
    popupLines.push(`${distanceText(party.myDistanceToDestination)} away`);
  }

  if (!destinationMarker) {
    const element = document.createElement("div");
    element.className = "destination-marker";
    element.textContent = "D";
    destinationMarker = new maplibregl.Marker({ element })
      .setPopup(new maplibregl.Popup({ offset: 18, closeButton: false }))
      .addTo(map);
  }

  destinationMarker.setLngLat(lngLat);
  destinationMarker.getPopup().setText(popupLines.join("\n"));
}

function renderStatus(data) {
  const me = data.me;
  const info = STATUS_INFO[me.status] || STATUS_INFO.NOT_IN_PARTY;

  mapEls.partyStatus.hidden = false;
  mapEls.partyStatus.dataset.tone = info.tone;
  mapEls.partyStatusLabel.textContent = info.label;
  mapEls.leaveParty.hidden = !data.party || data.party.myRole === "HOST";
  mapEls.rejoinParty.hidden = !me.leftParty;

  if (me.party) {
    const people = me.party.memberCount === 1 ? "1 person" : `${me.party.memberCount} people`;
    mapEls.partyStatusDetail.textContent =
      `${Math.round(me.distanceFromParty)} m from the center · ` +
      `${Math.round(me.party.radius)} m radius · ${people}`;
  } else if (me.leftParty) {
    mapEls.partyStatusLabel.textContent = "You left the party";
    mapEls.partyStatusDetail.textContent =
      "It's shown in gray on the map. Rejoin any time while it's still going.";
  } else if (data.party) {
    mapEls.partyStatusLabel.textContent = "In party group";
    mapEls.partyStatusDetail.textContent =
      data.party.mySharing
        ? "Waiting for a fresh location fix."
        : "Location sharing is paused for this party.";
  } else if (watchId === null) {
    mapEls.partyStatusDetail.textContent =
      "Create or join a party, then press Use my location.";
  } else {
    mapEls.partyStatusDetail.textContent =
      "Create or join a party to share your location with that group.";
  }
}

function renderPartyPanel(party, leftParty) {
  showPartyMessage("");
  mapEls.noPartyActions.hidden = Boolean(party || leftParty);
  mapEls.activePartyContent.hidden = !party;
  mapEls.leftPartyContent.hidden = !leftParty || Boolean(party);

  if (!party && !leftParty) {
    mapEls.partyPanelTitle.textContent = "Start a party";
    mapEls.partyPanelDetail.textContent =
      "Create or join a private temporary group before the night starts.";
    mapEls.partyMembersList.replaceChildren();
    return;
  }

  if (leftParty && !party) {
    mapEls.partyPanelTitle.textContent = "You left the party";
    mapEls.partyPanelDetail.textContent = leftParty.name;
    mapEls.leftPartyText.textContent =
      `${leftParty.name} is still active. Rejoin only if you want this group to see your location again.`;
    return;
  }

  mapEls.partyPanelTitle.textContent = party.name;
  mapEls.partyPanelDetail.textContent =
    party.destination && party.destination.name
      ? party.destination.name
      : "Private temporary party group";
  mapEls.partyCodeText.textContent = party.joinCode;
  mapEls.partyHostText.textContent = party.host ? party.host.username : "Unknown";
  mapEls.partyMemberCount.textContent = `${party.memberCount}`;
  mapEls.partyTimeLeft.textContent = timeRemaining(party.timeRemainingSeconds);
  mapEls.partySharingState.textContent = party.mySharing
    ? "Sharing location"
    : "Location sharing paused";
  mapEls.partySharingState.style.color = party.mySharing ? "var(--success)" : "var(--muted)";
  mapEls.togglePartySharing.textContent = party.mySharing
    ? "Stop Sharing Location"
    : "Share Location";
  mapEls.partyCheckIn.value =
    party.members.find((member) => member.isSelf)?.checkInStatus || "IM_GOOD";
  mapEls.endPartyPanel.hidden = party.myRole !== "HOST";
  mapEls.leavePartyPanel.hidden = party.myRole === "HOST";

  renderPartyDestinationPanel(party);
  renderPartyMembersList(party);
}

function renderPartyDestinationPanel(party) {
  const destination = party.destination;
  mapEls.partyDestination.hidden = !destination;
  if (!destination) return;

  mapEls.partyDestinationName.textContent = destination.name || "Party Destination";

  const details = [];
  if (destination.address) details.push(destination.address);
  if (destination.startTime) details.push(destination.startTime);
  if (destination.sourceLabel) details.push(destination.sourceLabel);
  mapEls.partyDestinationDetail.textContent = details.join(" · ");

  const distances = [];
  if (party.myDistanceToDestination !== null) {
    distances.push(`${distanceText(party.myDistanceToDestination)} from you`);
  }
  if (party.groupDistanceToDestination !== null) {
    distances.push(`Group is ${distanceText(party.groupDistanceToDestination)} from destination`);
  }
  mapEls.partyDestinationDistance.textContent = distances.join(" · ");

  const directionsUrl = destinationMapsUrl(destination);
  mapEls.partyDirections.hidden = !directionsUrl;
  mapEls.partyDirections.onclick = () => {
    if (directionsUrl) window.open(directionsUrl, "_blank", "noopener,noreferrer");
  };
}

function renderPartyMembersList(party) {
  mapEls.partyMembersList.replaceChildren();

  party.members.forEach((member) => {
    const statusInfo = STATUS_INFO[member.status] || STATUS_INFO.NOT_IN_PARTY;

    const row = document.createElement("article");
    row.className = "party-member-row";
    row.dataset.tone = statusInfo.tone;
    row.dataset.help = member.checkInStatus === "NEED_HELP" ? "true" : "false";

    const avatar = document.createElement("span");
    avatar.className = "friend-avatar";
    avatar.textContent = member.username.charAt(0).toUpperCase();

    const text = document.createElement("div");
    text.className = "party-member-text";

    const name = document.createElement("strong");
    name.textContent = `${member.username}${member.isSelf ? " (you)" : ""}`;

    const status = document.createElement("span");
    status.textContent = `${member.checkInLabel} · ${memberStatusText(member)}`;

    text.append(name, status);

    const actions = document.createElement("div");
    actions.className = "party-member-actions";

    if (member.location) {
      const viewButton = document.createElement("button");
      viewButton.className = "share-add-button";
      viewButton.type = "button";
      viewButton.textContent = "View";
      viewButton.addEventListener("click", () => {
        map.flyTo({
          center: [member.location.longitude, member.location.latitude],
          zoom: 17,
        });
      });
      actions.appendChild(viewButton);
    }

    if (member.canRemove) {
      const removeButton = document.createElement("button");
      removeButton.className = "share-remove-button";
      removeButton.type = "button";
      removeButton.textContent = "Remove";
      removeButton.addEventListener("click", () => removePartyMember(member, removeButton));
      actions.appendChild(removeButton);
    }

    row.append(avatar, text, actions);
    mapEls.partyMembersList.appendChild(row);
  });
}

function friendDetail(friend, freshSeconds) {
  if (!friend.location) return "Hasn't shared a location yet";

  const ago = timeAgo(friend.ageSeconds);
  if (friend.ageSeconds > freshSeconds) return `Last seen ${ago}`;
  if (friend.status === "NOT_IN_PARTY") return `Not in a party · ${ago}`;
  if (!friend.sameParty) return `At another party · ${ago}`;
  const info = STATUS_INFO[friend.status] || STATUS_INFO.NOT_IN_PARTY;
  return `${info.label} · ${ago}`;
}

function friendTone(friend, freshSeconds) {
  if (!friend.location || friend.ageSeconds > freshSeconds) return "none";
  const info = STATUS_INFO[friend.status] || STATUS_INFO.NOT_IN_PARTY;
  return info.tone;
}

const friendMarkers = new Map();
const partyMarkers = new Map();

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

    if (!friend.location || friend.sameParty) return;

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

function renderPartyMemberMarkers(party) {
  const seen = new Set();

  if (party) {
    party.members.forEach((member) => {
      if (member.isSelf || !member.location) return;

      const statusInfo = STATUS_INFO[member.status] || STATUS_INFO.NOT_IN_PARTY;
      const lngLat = [member.location.longitude, member.location.latitude];
      seen.add(member.id);

      let marker = partyMarkers.get(member.id);
      if (!marker) {
        const element = document.createElement("div");
        element.className = "friend-marker";
        element.textContent = member.username.charAt(0).toUpperCase();

        marker = new maplibregl.Marker({ element })
          .setLngLat(lngLat)
          .setPopup(new maplibregl.Popup({ offset: 18, closeButton: false }))
          .addTo(map);
        partyMarkers.set(member.id, marker);
      }

      const detail = `${member.checkInLabel} · ${memberStatusText(member)}`;
      const element = marker.getElement();
      element.dataset.tone = statusInfo.tone;
      element.classList.toggle("is-stale", member.status === "STALE_LOCATION");
      element.setAttribute("aria-label", `${member.username}: ${detail}`);
      marker.setLngLat(lngLat);
      marker.getPopup().setText(`${member.username} · ${detail}`);
    });
  }

  for (const [id, marker] of partyMarkers) {
    if (!seen.has(id)) {
      marker.remove();
      partyMarkers.delete(id);
    }
  }
}

async function runPartyAction(button, task) {
  button.disabled = true;
  try {
    await task();
    await refresh();
  } catch (partyError) {
    await refresh().catch(() => {});
    showPartyMessage(partyError.message);
  } finally {
    button.disabled = false;
  }
}

function currentPartyId() {
  return latestData && latestData.party ? latestData.party.id : null;
}

function leftPartyId() {
  return latestData && latestData.me.leftParty ? latestData.me.leftParty.id : null;
}

function leaveCurrentParty(button) {
  const partyId = currentPartyId();
  if (!partyId) return;
  if (!window.confirm("Leave this party? Your location will stop being shared with the group.")) return;

  runPartyAction(button, async () => {
    await api(`/api/parties/${encodeURIComponent(partyId)}/leave`, {});
  });
}

function rejoinLeftParty(button) {
  const partyId = leftPartyId();
  if (!partyId) return;
  if (!window.confirm("Rejoin this party and share your location if enabled?")) return;

  runPartyAction(button, async () => {
    await api(`/api/parties/${encodeURIComponent(partyId)}/rejoin`, {
      shareLocation: true,
    });
  });
}

function endCurrentParty() {
  const partyId = currentPartyId();
  if (!partyId) return;
  if (!window.confirm("End this party for everyone? Location sharing and wandering alerts will stop.")) return;

  runPartyAction(mapEls.endPartyPanel, async () => {
    await api(`/api/parties/${encodeURIComponent(partyId)}/end`, {});
  });
}

function removePartyMember(member, button) {
  const partyId = currentPartyId();
  if (!partyId) return;
  if (!window.confirm(`Remove ${member.username} from this party?`)) return;

  runPartyAction(button, async () => {
    await apiDelete(
      `/api/parties/${encodeURIComponent(partyId)}/members/${encodeURIComponent(member.id)}`
    );
  });
}

mapEls.leaveParty.addEventListener("click", () => leaveCurrentParty(mapEls.leaveParty));
mapEls.leavePartyPanel.addEventListener("click", () => leaveCurrentParty(mapEls.leavePartyPanel));
mapEls.rejoinParty.addEventListener("click", () => rejoinLeftParty(mapEls.rejoinParty));
mapEls.rejoinPartyPanel.addEventListener("click", () => rejoinLeftParty(mapEls.rejoinPartyPanel));
mapEls.endPartyPanel.addEventListener("click", endCurrentParty);

// ==================================================
// CREATE / JOIN PARTY UI
// ==================================================

const inviteCodeFromUrl = new URLSearchParams(window.location.search).get("code");
let invitePrompted = false;

function openPartyModal(mode, code = "") {
  const creating = mode === "create";
  mapEls.partyModal.hidden = false;
  mapEls.createPartyForm.hidden = !creating;
  mapEls.joinPartyForm.hidden = creating;
  mapEls.partyModalTitle.textContent = creating ? "Create Party" : "Join Party";
  mapEls.partyModalSubtitle.textContent = creating
    ? "Name the party, optionally add a destination, and choose whether to share your location."
    : "Confirm the code and choose whether this party can see your live location.";

  if (creating) {
    mapEls.partyName.focus();
  } else {
    mapEls.partyJoinCode.value = code;
    mapEls.partyJoinCode.focus();
  }
}

function closePartyModal() {
  mapEls.partyModal.hidden = true;
  mapEls.createPartyForm.reset();
  mapEls.joinPartyForm.reset();
  mapEls.createShareLocation.checked = true;
  mapEls.joinShareLocation.checked = true;
}

function optionalValue(input) {
  const value = input.value.trim();
  return value || null;
}

function destinationBody() {
  const destination = {
    name: optionalValue(mapEls.destinationName),
    address: optionalValue(mapEls.destinationAddress),
    startTime: optionalValue(mapEls.destinationStartTime),
    latitude: optionalValue(mapEls.destinationLatitude),
    longitude: optionalValue(mapEls.destinationLongitude),
    source: mapEls.destinationIsTuParties.checked ? "tuparties" : "manual",
    sourceUrl: optionalValue(mapEls.destinationUrl),
  };

  const hasDestination = Object.entries(destination).some(([key, value]) => {
    if (key === "source") return false;
    return value !== null;
  });

  return hasDestination ? destination : null;
}

mapEls.createPartyOpen.addEventListener("click", () => openPartyModal("create"));
mapEls.joinPartyOpen.addEventListener("click", () => openPartyModal("join"));
mapEls.partyModalClose.addEventListener("click", closePartyModal);
mapEls.partyModal.addEventListener("click", (event) => {
  if (event.target === mapEls.partyModal) closePartyModal();
});

mapEls.createPartyForm.addEventListener("submit", (event) => {
  event.preventDefault();

  runPartyAction(mapEls.createPartySubmit, async () => {
    await api("/api/parties", {
      name: mapEls.partyName.value.trim(),
      destination: destinationBody(),
      shareLocation: mapEls.createShareLocation.checked,
    });
    closePartyModal();
  });
});

mapEls.joinPartyForm.addEventListener("submit", (event) => {
  event.preventDefault();

  runPartyAction(mapEls.joinPartySubmit, async () => {
    await api("/api/parties/join", {
      code: mapEls.partyJoinCode.value.trim(),
      shareLocation: mapEls.joinShareLocation.checked,
    });
    closePartyModal();
    window.history.replaceState({}, "", window.location.pathname);
  });
});

mapEls.copyPartyCode.addEventListener("click", async () => {
  const party = latestData && latestData.party;
  if (!party) return;
  const copied = await copyText(`${party.joinCode}\n${party.inviteUrl}`);
  showPartyMessage(copied ? "Party code copied." : `Code: ${party.joinCode}`);
});

mapEls.inviteParty.addEventListener("click", async () => {
  const party = latestData && latestData.party;
  if (!party) return;

  const text = `Join ${party.name} on FriendsNMe with code ${party.joinCode}.`;

  if (navigator.share) {
    try {
      await navigator.share({
        title: "FriendsNMe party invite",
        text,
        url: party.inviteUrl,
      });
      return;
    } catch {
      /* fall back to clipboard */
    }
  }

  const copied = await copyText(`${text}\n${party.inviteUrl}`);
  showPartyMessage(copied ? "Invite copied." : `${party.joinCode} · ${party.inviteUrl}`);
});

mapEls.togglePartySharing.addEventListener("click", () => {
  const party = latestData && latestData.party;
  if (!party) return;

  const enabled = !party.mySharing;
  runPartyAction(mapEls.togglePartySharing, async () => {
    await api(`/api/parties/${encodeURIComponent(party.id)}/location-sharing`, {
      enabled,
    });
  });
});

mapEls.partyCheckIn.addEventListener("change", () => {
  const party = latestData && latestData.party;
  if (!party) return;

  runPartyAction(mapEls.partyCheckIn, async () => {
    await api(`/api/parties/${encodeURIComponent(party.id)}/status`, {
      status: mapEls.partyCheckIn.value,
    });
  });
});

// ==================================================
// SIGN IN / SIGN OUT (events come from index.js)
// ==================================================

let pollTimer = null;

function refresh() {
  return api("/api/map")
    .then(render)
    .catch((refreshError) => {
      // Signed out elsewhere; index.js handles showing the login.
      if (refreshError.status === 401) stopPolling();
      throw refreshError;
    });
}

function startPolling() {
  if (pollTimer !== null) return;
  refresh().catch(() => {});
  pollTimer = setInterval(() => refresh().catch(() => {}), POLL_INTERVAL_MS);

  if (inviteCodeFromUrl && !invitePrompted) {
    invitePrompted = true;
    openPartyModal("join", inviteCodeFromUrl.toUpperCase());
  }
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
  resetAlerts(); // alerts.js
  userMarker.remove();
  userMarkerAdded = false;
  friendMarkers.forEach((marker) => marker.remove());
  friendMarkers.clear();
  partyMarkers.forEach((marker) => marker.remove());
  partyMarkers.clear();
  if (destinationMarker) {
    destinationMarker.remove();
    destinationMarker = null;
  }
  renderParty(null);
  renderPartyPanel(null, null);
  closePartyModal();
  mapEls.partyStatus.hidden = true;
  mapEls.friendsList.replaceChildren();
  mapEls.friendsCount.textContent = "";
});

// In case index.js restored the session before this file loaded.
if (!document.body.classList.contains("auth-locked")) startPolling();
