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
