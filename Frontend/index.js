// Client-side auth flow. There is no backend yet, so the verification code is
// generated in the browser and shown in the message box (demo mode).
// Replace sendCode/verifyCode/isUsernameTaken with real API calls later.

const $ = (id) => document.getElementById(id);

const els = {
  overlay: $("authOverlay"),
  message: $("authMessage"),
  subtitle: $("authSubtitle"),
  emailForm: $("emailForm"),
  email: $("templeEmail"),
  emailSubmit: $("emailSubmit"),
  codeForm: $("codeForm"),
  code: $("verificationCode"),
  codeSubmit: $("codeSubmit"),
  resend: $("resendCode"),
  changeEmail: $("changeEmail"),
  usernameForm: $("usernameForm"),
  username: $("username"),
  usernameSubmit: $("usernameSubmit"),
  verifiedEmail: $("verifiedEmail"),
  badge: $("userBadge"),
  logout: $("logoutButton"),
};

const STORAGE_KEY = "friendsnme.accounts";
const SESSION_KEY = "friendsnme.session";
const TEMPLE_EMAIL = /^[^\s@]+@temple\.edu$/i;

let pendingEmail = "";
let pendingCode = "";

function readJSON(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
}

function writeJSON(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable */
  }
}

function showMessage(text, success = false) {
  els.message.textContent = text;
  els.message.classList.toggle("success", success);
  els.message.hidden = !text;
}

function showStep(step) {
  els.emailForm.hidden = step !== "email";
  els.codeForm.hidden = step !== "code";
  els.usernameForm.hidden = step !== "username";
}

function unlock(session) {
  document.body.classList.remove("auth-locked");
  els.overlay.hidden = true;
  els.badge.textContent = session.username;
  els.badge.hidden = false;
  els.logout.hidden = false;
}

function lock() {
  document.body.classList.add("auth-locked");
  els.overlay.hidden = false;
  els.badge.hidden = true;
  els.logout.hidden = true;
  els.email.value = "";
  els.code.value = "";
  els.username.value = "";
  els.emailSubmit.disabled = true;
  els.codeSubmit.disabled = true;
  els.usernameSubmit.disabled = true;
  showMessage("");
  showStep("email");
}

function sendCode() {
  pendingCode = String(Math.floor(100000 + Math.random() * 900000));
  showMessage(`Demo mode: your verification code is ${pendingCode}`, true);
}

// Input validation -> enable/disable buttons
els.email.addEventListener("input", () => {
  els.emailSubmit.disabled = !TEMPLE_EMAIL.test(els.email.value.trim());
});
els.code.addEventListener("input", () => {
  els.code.value = els.code.value.replace(/\D/g, "");
  els.codeSubmit.disabled = els.code.value.length !== 6;
});
els.username.addEventListener("input", () => {
  els.usernameSubmit.disabled = els.username.value.trim().length < 3;
});

// Step 1: email
els.emailForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const email = els.email.value.trim().toLowerCase();
  if (!TEMPLE_EMAIL.test(email)) {
    showMessage("Please use a valid @temple.edu email address.");
    return;
  }
  pendingEmail = email;
  sendCode();
  els.subtitle.textContent = `Enter the 6-digit code for ${email}.`;
  showStep("code");
  els.code.focus();
});

// Step 2: code
els.codeForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (els.code.value !== pendingCode) {
    showMessage("That code is incorrect. Try again or resend the code.");
    return;
  }
  const accounts = readJSON(STORAGE_KEY, {});
  const existing = accounts[pendingEmail];
  if (existing) {
    writeJSON(SESSION_KEY, existing);
    showMessage("");
    unlock(existing);
    return;
  }
  els.verifiedEmail.textContent = pendingEmail;
  els.subtitle.textContent = "Pick a username to finish creating your account.";
  showMessage("");
  showStep("username");
  els.username.focus();
});

els.resend.addEventListener("click", () => {
  els.code.value = "";
  els.codeSubmit.disabled = true;
  sendCode();
});

els.changeEmail.addEventListener("click", () => {
  pendingCode = "";
  els.subtitle.textContent = "Use your Temple University email to access FriendsNMe.";
  showMessage("");
  showStep("email");
  els.email.focus();
});

// Step 3: username
els.usernameForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const username = els.username.value.trim();
  const accounts = readJSON(STORAGE_KEY, {});
  const taken = Object.values(accounts).some(
    (a) => a.username.toLowerCase() === username.toLowerCase()
  );
  if (taken) {
    showMessage("That username is already taken.");
    return;
  }
  const account = { email: pendingEmail, username };
  accounts[pendingEmail] = account;
  writeJSON(STORAGE_KEY, accounts);
  writeJSON(SESSION_KEY, account);
  showMessage("");
  unlock(account);
});

els.logout.addEventListener("click", () => {
  try {
    localStorage.removeItem(SESSION_KEY);
  } catch {
    /* ignore */
  }
  lock();
});

// Restore an existing session
const session = readJSON(SESSION_KEY, null);
if (session?.username) unlock(session);
const authOverlay = document.querySelector("#authOverlay");
const authTitle = document.querySelector("#authTitle");
const authSubtitle = document.querySelector("#authSubtitle");
const authMessage = document.querySelector("#authMessage");
const emailForm = document.querySelector("#emailForm");
const codeForm = document.querySelector("#codeForm");
const usernameForm = document.querySelector("#usernameForm");
const emailInput = document.querySelector("#templeEmail");
const codeInput = document.querySelector("#verificationCode");
const usernameInput = document.querySelector("#username");
const emailSubmit = document.querySelector("#emailSubmit");
const codeSubmit = document.querySelector("#codeSubmit");
const usernameSubmit = document.querySelector("#usernameSubmit");
const resendButton = document.querySelector("#resendCode");
const changeEmailButton = document.querySelector("#changeEmail");
const logoutButton = document.querySelector("#logoutButton");
const userBadge = document.querySelector("#userBadge");
const verifiedEmail = document.querySelector("#verifiedEmail");
const emailHint = document.querySelector("#emailHint");
const campusMap = document.querySelector("#campusMap");
const locationButton = document.querySelector("#locationButton");
const locationStatus = document.querySelector("#locationStatus");

const state = {
  email: "",
  step: "loading",
  resendTimer: null,
  resendSeconds: 0,
  locationWatchId: null,
  locationSaveInProgress: false,
  pendingLocation: null,
  lastLocationSavedAt: 0
};

const LOCATION_SAVE_INTERVAL_MS = 3000;

function isTempleEmail(email) {
  return /^[^\s@]+@temple\.edu$/i.test(email.trim());
}

function setLocked(locked) {
  document.body.classList.toggle("auth-locked", locked);
  authOverlay.hidden = !locked;
}

function setBusy(button, busy, label) {
  button.disabled = busy;
  button.dataset.originalText ||= button.textContent;
  button.textContent = busy ? label : button.dataset.originalText;
}

function showMessage(message = "", type = "error") {
  authMessage.textContent = message;
  authMessage.className = `auth-message ${type}`;
  authMessage.hidden = !message;
}

function showForm(step) {
  state.step = step;
  emailForm.hidden = step !== "email";
  codeForm.hidden = step !== "code";
  usernameForm.hidden = step !== "username";
  showMessage("");

  if (step === "email") {
    authTitle.textContent = "Temple sign in";
    authSubtitle.textContent = "Use your Temple University email to access FriendsNMe.";
    emailInput.focus();
  }

  if (step === "code") {
    authTitle.textContent = "Enter verification code";
    authSubtitle.textContent = `We sent a 6-digit code to ${state.email}.`;
    codeInput.value = "";
    codeInput.focus();
    startResendCooldown(60);
  }

  if (step === "username") {
    authTitle.textContent = "Choose a username";
    authSubtitle.textContent = "This name will identify you in FriendsNMe.";
    verifiedEmail.textContent = state.email;
    usernameInput.focus();
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    const error = new Error(payload.error || "Something went wrong. Please try again.");
    error.status = response.status;
    throw error;
  }

  return payload;
}

function updateEmailSubmit() {
  const email = emailInput.value.trim();
  emailSubmit.disabled = !isTempleEmail(email);

  if (!email) {
    emailHint.textContent = "Enter your @temple.edu email address.";
    return;
  }

  emailHint.textContent = isTempleEmail(email)
    ? "We will send a one-time verification code."
    : "Only Temple University email addresses can access this website.";
}

function updateCodeSubmit() {
  codeSubmit.disabled = !/^\d{6}$/.test(codeInput.value.trim());
}

function updateUsernameSubmit() {
  usernameSubmit.disabled = usernameInput.value.trim().length === 0;
}

function startResendCooldown(seconds) {
  clearInterval(state.resendTimer);
  state.resendSeconds = seconds;
  resendButton.disabled = true;
  resendButton.textContent = `Resend code (${state.resendSeconds}s)`;

  state.resendTimer = setInterval(() => {
    state.resendSeconds -= 1;
    if (state.resendSeconds <= 0) {
      clearInterval(state.resendTimer);
      resendButton.disabled = false;
      resendButton.textContent = "Resend code";
      return;
    }
    resendButton.textContent = `Resend code (${state.resendSeconds}s)`;
  }, 1000);
}

async function checkSession() {
  setLocked(true);
  authTitle.textContent = "Checking session";
  authSubtitle.textContent = "Please wait while we confirm your sign-in.";
  emailForm.hidden = true;
  codeForm.hidden = true;
  usernameForm.hidden = true;

  try {
    const payload = await fetchJson("/api/auth/session", { method: "GET" });
    unlock(payload.user);
  } catch {
    showForm("email");
  }
}

function unlock(user) {
  userBadge.textContent = user.username;
  userBadge.hidden = false;
  logoutButton.hidden = false;
  setLocked(false);
}

function showSuccessThenUnlock(user) {
  emailForm.hidden = true;
  codeForm.hidden = true;
  usernameForm.hidden = true;
  authTitle.textContent = "Success";
  authSubtitle.textContent = "You are signed in.";
  showMessage("Opening FriendsNMe...", "success");
  setTimeout(() => unlock(user), 600);
}

function setLocationStatus(message, type = "") {
  locationStatus.textContent = message;
  locationStatus.className = type ? `location-${type}` : "";
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function formatPosition(position) {
  const { latitude, longitude, accuracy } = position.coords;
  const accuracyText = Number.isFinite(accuracy) ? ` | Accuracy: ${Math.round(accuracy)}m` : "";
  return `Latitude: ${latitude.toFixed(6)} | Longitude: ${longitude.toFixed(6)}${accuracyText}`;
}

async function saveLocation(position) {
  const { latitude, longitude, accuracy } = position.coords;
  return fetchJson("/api/location", {
    method: "POST",
    body: JSON.stringify({
      latitude,
      longitude,
      accuracy,
      capturedAt: new Date(position.timestamp).toISOString()
    })
  });
}

async function flushPendingLocation() {
  if (state.locationSaveInProgress) {
    return;
  }

  state.locationSaveInProgress = true;

  while (state.pendingLocation) {
    const position = state.pendingLocation;
    state.pendingLocation = null;

    const elapsed = Date.now() - state.lastLocationSavedAt;
    if (elapsed < LOCATION_SAVE_INTERVAL_MS) {
      await wait(LOCATION_SAVE_INTERVAL_MS - elapsed);
    }

    try {
      await saveLocation(position);
      state.lastLocationSavedAt = Date.now();
      setLocationStatus(`${formatPosition(position)} | Live and saved`, "success");
    } catch (error) {
      if (error.status === 401) {
        stopLiveLocation();
        setLocked(true);
        showForm("email");
      }
      setLocationStatus(`${formatPosition(position)} | Could not save: ${error.message}`, "error");
    }
  }

  state.locationSaveInProgress = false;
}

function showLiveLocation(position) {
  const { latitude, longitude } = position.coords;

  campusMap.setAttribute("center", `${latitude},${longitude}`);
  campusMap.setAttribute("zoom", "16");
  setLocationStatus(`${formatPosition(position)} | Live update received`, "success");

  state.pendingLocation = position;
  flushPendingLocation();
}

function showLocationError(error) {
  const denied = error && error.code === error.PERMISSION_DENIED;
  setLocationStatus(
    denied
      ? "Location permission was denied. You can enable it in your browser settings."
      : "Sorry, no position available.",
    "error"
  );
  locationButton.disabled = false;
  stopLiveLocation();
}

function startLiveLocation() {
  if (!navigator.geolocation) {
    setLocationStatus("Geolocation is not supported by this browser.", "error");
    return;
  }

  locationButton.disabled = true;
  locationButton.textContent = "Requesting...";
  setLocationStatus("Waiting for browser location permission...");

  state.locationWatchId = navigator.geolocation.watchPosition(showLiveLocation, showLocationError, {
    enableHighAccuracy: true,
    timeout: 10000,
    maximumAge: 5000
  });
  locationButton.disabled = false;
  locationButton.textContent = "Stop live location";
}

function stopLiveLocation() {
  if (state.locationWatchId !== null && navigator.geolocation) {
    navigator.geolocation.clearWatch(state.locationWatchId);
  }

  state.locationWatchId = null;
  state.pendingLocation = null;
  locationButton.disabled = false;
  locationButton.textContent = "Start live location";
}

function toggleLiveLocation() {
  if (state.locationWatchId === null) {
    startLiveLocation();
    return;
  }

  stopLiveLocation();
  setLocationStatus("Live location stopped.");
}

emailInput.addEventListener("input", updateEmailSubmit);
codeInput.addEventListener("input", () => {
  codeInput.value = codeInput.value.replace(/\D/g, "").slice(0, 6);
  updateCodeSubmit();
});
usernameInput.addEventListener("input", updateUsernameSubmit);

emailForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const email = emailInput.value.trim().toLowerCase();

  if (!isTempleEmail(email)) {
    showMessage("Only Temple University email addresses can access this website.");
    return;
  }

  setBusy(emailSubmit, true, "Sending...");
  showMessage("");

  try {
    const payload = await fetchJson("/api/auth/request-code", {
      method: "POST",
      body: JSON.stringify({ email })
    });
    state.email = payload.email;
    showForm("code");
  } catch (error) {
    showMessage(error.message);
  } finally {
    setBusy(emailSubmit, false);
    updateEmailSubmit();
  }
});

codeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const code = codeInput.value.trim();

  setBusy(codeSubmit, true, "Verifying...");
  showMessage("");

  try {
    const payload = await fetchJson("/api/auth/verify-code", {
      method: "POST",
      body: JSON.stringify({ email: state.email, code })
    });

    if (payload.needsUsername) {
      showForm("username");
      return;
    }

    showSuccessThenUnlock(payload.user);
  } catch (error) {
    showMessage(error.message);
  } finally {
    setBusy(codeSubmit, false);
    updateCodeSubmit();
  }
});

usernameForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const username = usernameInput.value.trim();

  setBusy(usernameSubmit, true, "Creating...");
  showMessage("");

  try {
    const payload = await fetchJson("/api/auth/complete-signup", {
      method: "POST",
      body: JSON.stringify({ username })
    });
    showSuccessThenUnlock(payload.user);
  } catch (error) {
    showMessage(error.message);
    if (error.message === "Your signup session expired. Please verify your email again.") {
      showForm("email");
    }
  } finally {
    setBusy(usernameSubmit, false);
    updateUsernameSubmit();
  }
});

resendButton.addEventListener("click", async () => {
  resendButton.disabled = true;
  showMessage("");

  try {
    await fetchJson("/api/auth/request-code", {
      method: "POST",
      body: JSON.stringify({ email: state.email })
    });
    showMessage("A new verification code was sent.", "success");
    startResendCooldown(60);
  } catch (error) {
    showMessage(error.message);
    resendButton.disabled = false;
  }
});

changeEmailButton.addEventListener("click", () => {
  state.email = "";
  clearInterval(state.resendTimer);
  showForm("email");
});

logoutButton.addEventListener("click", async () => {
  stopLiveLocation();
  await fetchJson("/api/auth/logout", { method: "POST", body: "{}" }).catch(() => {});
  userBadge.hidden = true;
  logoutButton.hidden = true;
  showForm("email");
  setLocked(true);
});

locationButton.addEventListener("click", toggleLiveLocation);

updateEmailSubmit();
updateCodeSubmit();
updateUsernameSubmit();
checkSession();
