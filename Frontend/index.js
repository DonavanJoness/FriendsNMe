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
  resendSeconds: 0
};

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

async function showLocation(position) {
  const { latitude, longitude } = position.coords;
  const lat = latitude.toFixed(6);
  const lng = longitude.toFixed(6);

  campusMap.setAttribute("center", `${latitude},${longitude}`);
  campusMap.setAttribute("zoom", "16");

  try {
    await saveLocation(position);
    setLocationStatus(`Latitude: ${lat} | Longitude: ${lng} saved for backend calculations.`, "success");
  } catch (error) {
    if (error.status === 401) {
      setLocked(true);
      showForm("email");
    }
    setLocationStatus(`Latitude: ${lat} | Longitude: ${lng}. Could not save: ${error.message}`, "error");
  } finally {
    locationButton.disabled = false;
    locationButton.textContent = "Update location";
  }
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
  locationButton.textContent = "Try again";
}

function getLocation() {
  if (!navigator.geolocation) {
    setLocationStatus("Geolocation is not supported by this browser.", "error");
    return;
  }

  locationButton.disabled = true;
  locationButton.textContent = "Requesting...";
  setLocationStatus("Waiting for browser location permission...");

  navigator.geolocation.getCurrentPosition(showLocation, showLocationError, {
    enableHighAccuracy: true,
    timeout: 10000,
    maximumAge: 60000
  });
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
  await fetchJson("/api/auth/logout", { method: "POST", body: "{}" }).catch(() => {});
  userBadge.hidden = true;
  logoutButton.hidden = true;
  showForm("email");
  setLocked(true);
});

locationButton.addEventListener("click", getLocation);

updateEmailSubmit();
updateCodeSubmit();
updateUsernameSubmit();
checkSession();
