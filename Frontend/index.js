// Client-side auth flow. All account state lives on the Flask server
// (SQLite + signed session cookie); this file only drives the UI.

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
  friendsList: $("friendsList"),
  friendsCount: $("friendsCount"),
};

// Same list the Sharing page writes to.
const FRIENDS_KEY = "friendsnme.sharedAccounts";
const TEMPLE_EMAIL = /^[^\s@]+@temple\.edu$/i;

let pendingEmail = "";

function readJSON(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) || fallback;
  } catch {
    return fallback;
  }
}

// POST/GET JSON to the Flask API. Same-origin, so the session cookie
// is sent automatically; "same-origin" makes that explicit.
async function api(path, body) {
  const options = { credentials: "same-origin" };
  if (body !== undefined) {
    options.method = "POST";
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new Error("Could not reach the server. Is Flask running?");
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || `Server returned HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return data;
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

function renderFriends() {
  const friends = readJSON(FRIENDS_KEY, []);
  els.friendsList.innerHTML = "";
  els.friendsCount.textContent = friends.length === 1
    ? "1 friend"
    : `${friends.length} friends`;

  if (friends.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-share-state";
    empty.textContent = "No friends yet. Add people from the Sharing page.";
    els.friendsList.appendChild(empty);
    return;
  }

  friends.forEach((friend) => {
    const row = document.createElement("article");
    row.className = "shared-account-row";

    const info = document.createElement("div");
    info.className = "friend-info";

    const avatar = document.createElement("span");
    avatar.className = "friend-avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = friend.username.charAt(0).toUpperCase();

    const text = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = friend.username;
    const email = document.createElement("span");
    email.textContent = friend.email;
    text.append(name, email);

    info.append(avatar, text);
    row.appendChild(info);
    els.friendsList.appendChild(row);
  });
}

function unlock(user) {
  renderFriends();
  document.body.classList.remove("auth-locked");
  els.overlay.hidden = true;
  els.badge.textContent = user.username;
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
  els.subtitle.textContent = "Use your Temple University email to access FriendsNMe.";
  showMessage("");
  showStep("email");
}

// Disable a button while a request is in flight
async function withBusy(button, task) {
  button.disabled = true;
  try {
    await task();
  } finally {
    button.disabled = false;
  }
}

async function sendCode() {
  await api("/api/auth/request-code", { email: pendingEmail });
  showMessage(`A verification code was sent to ${pendingEmail}.`, true);
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

  withBusy(els.emailSubmit, async () => {
    pendingEmail = email;
    try {
      await sendCode();
    } catch (error) {
      showMessage(error.message);
      // 429 "please wait" still means a code is out there — let them enter it
      if (error.status !== 429) return;
    }
    els.subtitle.textContent = `Enter the 6-digit code for ${email}.`;
    showStep("code");
    els.code.focus();
  });
});

// Step 2: code
els.codeForm.addEventListener("submit", (event) => {
  event.preventDefault();

  withBusy(els.codeSubmit, async () => {
    let data;
    try {
      data = await api("/api/auth/verify-code", {
        email: pendingEmail,
        code: els.code.value,
      });
    } catch (error) {
      showMessage(error.message);
      return;
    }

    if (!data.needsUsername) {
      showMessage("");
      unlock(data.user);
      return;
    }

    els.verifiedEmail.textContent = pendingEmail;
    els.subtitle.textContent = "Pick a username to finish creating your account.";
    showMessage("");
    showStep("username");
    els.username.focus();
  });
});

els.resend.addEventListener("click", () => {
  els.code.value = "";
  els.codeSubmit.disabled = true;
  withBusy(els.resend, async () => {
    try {
      await sendCode();
    } catch (error) {
      showMessage(error.message);
    }
  });
});

els.changeEmail.addEventListener("click", () => {
  pendingEmail = "";
  els.subtitle.textContent = "Use your Temple University email to access FriendsNMe.";
  showMessage("");
  showStep("email");
  els.email.focus();
});

// Step 3: username
els.usernameForm.addEventListener("submit", (event) => {
  event.preventDefault();

  withBusy(els.usernameSubmit, async () => {
    try {
      const data = await api("/api/auth/complete-signup", {
        username: els.username.value.trim(),
      });
      showMessage("");
      unlock(data.user);
    } catch (error) {
      showMessage(error.message);
      // Signup window expired on the server — start over
      if (error.status === 401) showStep("email");
    }
  });
});

els.logout.addEventListener("click", async () => {
  try {
    await api("/api/auth/logout", {});
  } catch {
    /* clear the UI regardless */
  }
  lock();
});

// Keep the list in sync if the Sharing page is open in another tab
window.addEventListener("storage", (event) => {
  if (event.key === FRIENDS_KEY) renderFriends();
});

renderFriends();

// Restore an existing server session on page load
api("/api/auth/session")
  .then((data) => unlock(data.user))
  .catch(() => lock());
