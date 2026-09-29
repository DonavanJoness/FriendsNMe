// Wandering alerts. map.js calls checkForAlerts() with every map
// update; when you or someone in your party wanders off, this shows
// an on-screen banner, vibrates (Android) and, if allowed, sends a
// system notification.
//
// These only fire while the page is open: phones pause web pages
// when the screen is off or the browser is in the background.

// Higher = further from the party.
const ALERT_LEVEL = {
  INSIDE_PARTY: 0,
  BUFFER_ZONE: 1,
  WANDERING: 2,
  FAR_FROM_PARTY: 3,
};
const WANDERING_LEVEL = ALERT_LEVEL.WANDERING;

// GPS can flicker between "buffer" and "wandering"; don't repeat the
// same alert for the same person within this window.
const ALERT_COOLDOWN_MS = 2 * 60 * 1000;
const TOAST_MS = 8000;

const alertEls = {
  toast: document.getElementById("alertToast"),
  toastTitle: document.getElementById("alertToastTitle"),
  toastBody: document.getElementById("alertToastBody"),
  button: document.getElementById("alertsButton"),
};

// person id ("me" for you) -> { level, alertedLevel, alertedAt }
const alertState = new Map();
let toastTimer = null;

const canNotify = "Notification" in window && window.isSecureContext;

// ==================================================
// DECIDING WHEN TO ALERT
// ==================================================

function checkForAlerts(data) {
  const people = [];

  if (data.me.party) {
    people.push({ id: "me", status: data.me.status, distance: data.me.distanceFromParty });
  }

  // Only explicit party members with a fresh shared location.
  (data.party?.members || []).forEach((friend) => {
    if (!friend.isSelf && friend.location && friend.ageSeconds <= data.freshSeconds) {
      people.push({
        id: friend.id,
        name: friend.username,
        status: friend.status,
        distance: friend.distanceFromParty,
      });
    }
  });

  const now = Date.now();

  people.forEach((person) => {
    const level = ALERT_LEVEL[person.status];
    const state = alertState.get(person.id);

    // First time we see someone: remember where they are, no alert.
    if (!state) {
      alertState.set(person.id, { level, alertedLevel: 0, alertedAt: 0 });
      return;
    }

    const movedFurther = level >= WANDERING_LEVEL && level > state.level;
    const newAlert = level > state.alertedLevel || now - state.alertedAt > ALERT_COOLDOWN_MS;

    if (movedFurther && newAlert) {
      sendAlert(person, level);
      state.alertedLevel = level;
      state.alertedAt = now;
    } else if (level === ALERT_LEVEL.INSIDE_PARTY && state.alertedLevel >= WANDERING_LEVEL) {
      // Let everyone know they made it back.
      sendAlert(person, level);
      state.alertedLevel = 0;
    }

    state.level = level;
  });
}

function resetAlerts() {
  alertState.clear();
  hideToast();
}

// ==================================================
// SENDING AN ALERT
// ==================================================

function alertText(person, level) {
  const isMe = person.id === "me";
  const who = isMe ? "You're" : `${person.name} is`;
  const meters = Math.round(person.distance);

  if (level === ALERT_LEVEL.INSIDE_PARTY) {
    return { title: `${who} back at the party`, body: "" };
  }

  const where = level === ALERT_LEVEL.FAR_FROM_PARTY ? "far from the party" : "wandering from the party";
  return {
    title: `${who} ${where}`,
    body: `${isMe ? "You are" : `${person.name} is`} ${meters} m from the center of the party.`,
  };
}

function sendAlert(person, level) {
  const { title, body } = alertText(person, level);
  const tone = level === ALERT_LEVEL.FAR_FROM_PARTY ? "far" : level >= WANDERING_LEVEL ? "wandering" : "inside";

  showToast(title, body, tone);

  if (level >= WANDERING_LEVEL && navigator.vibrate) {
    navigator.vibrate([200, 100, 200]);
  }

  // One notification per person, replaced as their status changes.
  systemNotify(title, body, `friendsnme-${person.id}`);
}

async function systemNotify(title, body, tag) {
  if (!canNotify || Notification.permission !== "granted") return;

  const options = { body, tag, renotify: true };
  try {
    const registration = await navigator.serviceWorker?.getRegistration();
    if (registration) {
      await registration.showNotification(title, options);
    } else {
      new Notification(title, options);
    }
  } catch (notifyError) {
    console.error("Could not show notification:", notifyError);
  }
}

function showToast(title, body, tone) {
  alertEls.toast.dataset.tone = tone;
  alertEls.toastTitle.textContent = title;
  alertEls.toastBody.textContent = body;
  alertEls.toastBody.hidden = !body;
  alertEls.toast.hidden = false;

  clearTimeout(toastTimer);
  toastTimer = setTimeout(hideToast, TOAST_MS);
}

function hideToast() {
  clearTimeout(toastTimer);
  alertEls.toast.hidden = true;
}

alertEls.toast.addEventListener("click", hideToast);

// ==================================================
// NOTIFICATION PERMISSION
// ==================================================

function updateAlertsButton() {
  // Hidden once decided, or where notifications don't exist
  // (e.g. iPhone Safari unless the site is added to the home screen).
  alertEls.button.hidden = !canNotify || Notification.permission !== "default";
}

alertEls.button.addEventListener("click", async () => {
  const permission = await Notification.requestPermission();
  updateAlertsButton();
  if (permission === "granted") {
    showToast("Wandering alerts are on", "You'll get a notification when someone in your party wanders off.", "inside");
  }
});

if (canNotify && "serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch((swError) => {
    console.error("Service worker registration failed:", swError);
  });
}

updateAlertsButton();
