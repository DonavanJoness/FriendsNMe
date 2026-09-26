const crypto = require("node:crypto");

const SESSION_COOKIE = "fnm_session";
const SIGNUP_COOKIE = "fnm_signup";
const SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30;
const SIGNUP_MAX_AGE_SECONDS = 60 * 15;
const CODE_TTL_MS = 10 * 60 * 1000;
const MAX_CODES_PER_HOUR = 5;
const MIN_RESEND_INTERVAL_MS = 60 * 1000;
const MAX_CODE_ATTEMPTS = 5;

function getSecret() {
  const secret = process.env.SESSION_SECRET;
  if (process.env.NODE_ENV === "production" && (!secret || secret.length < 32)) {
    throw new Error("SESSION_SECRET must be at least 32 characters in production.");
  }

  return secret || "development-only-secret-change-me";
}

function normalizeEmail(email) {
  return String(email || "").trim().toLowerCase();
}

function isTempleEmail(email) {
  return /^[^\s@]+@temple\.edu$/.test(normalizeEmail(email));
}

function normalizeUsername(username) {
  return String(username || "").trim().replace(/\s+/g, " ");
}

function validateUsername(username) {
  const normalized = normalizeUsername(username);
  if (!normalized) {
    return "Username cannot be empty.";
  }

  if (normalized.length > 32) {
    return "Username must be 32 characters or fewer.";
  }

  if (!/^[A-Za-z0-9._ -]+$/.test(normalized)) {
    return "Username can only use letters, numbers, spaces, periods, underscores, and hyphens.";
  }

  return null;
}

function hmac(value) {
  return crypto.createHmac("sha256", getSecret()).update(value).digest("hex");
}

function randomToken() {
  return crypto.randomBytes(32).toString("base64url");
}

function randomCode() {
  return String(crypto.randomInt(100000, 1000000));
}

function safeEqualHex(a, b) {
  const left = Buffer.from(a, "hex");
  const right = Buffer.from(b, "hex");
  return left.length === right.length && crypto.timingSafeEqual(left, right);
}

function parseCookies(cookieHeader = "") {
  return cookieHeader.split(";").reduce((cookies, pair) => {
    const index = pair.indexOf("=");
    if (index === -1) {
      return cookies;
    }

    const key = pair.slice(0, index).trim();
    const value = pair.slice(index + 1).trim();
    if (key) {
      cookies[key] = decodeURIComponent(value);
    }
    return cookies;
  }, {});
}

function serializeCookie(name, value, options = {}) {
  const parts = [`${name}=${encodeURIComponent(value)}`, "Path=/", "HttpOnly", "SameSite=Lax"];

  if (process.env.NODE_ENV === "production") {
    parts.push("Secure");
  }

  if (options.maxAge !== undefined) {
    parts.push(`Max-Age=${options.maxAge}`);
  }

  if (options.expires) {
    parts.push(`Expires=${options.expires.toUTCString()}`);
  }

  return parts.join("; ");
}

function clearCookie(name) {
  return serializeCookie(name, "", { maxAge: 0, expires: new Date(0) });
}

function publicUser(user) {
  return {
    id: user.id,
    email: user.email,
    username: user.username,
    createdAt: user.createdAt
  };
}

function createSession(db, user) {
  const token = randomToken();
  db.createSession({
    sessionHash: hmac(token),
    userId: user.id,
    expiresAt: new Date(Date.now() + SESSION_MAX_AGE_SECONDS * 1000).toISOString()
  });

  return {
    token,
    cookie: serializeCookie(SESSION_COOKIE, token, { maxAge: SESSION_MAX_AGE_SECONDS })
  };
}

function getAuthenticatedUser(db, request) {
  const cookies = parseCookies(request.headers.cookie);
  const token = cookies[SESSION_COOKIE];
  if (!token) {
    return null;
  }

  const session = db.findSession(hmac(token));
  if (!session) {
    return null;
  }

  return db.findUserById(session.userId);
}

function deleteCurrentSession(db, request) {
  const cookies = parseCookies(request.headers.cookie);
  const token = cookies[SESSION_COOKIE];
  if (token) {
    db.deleteSession(hmac(token));
  }
}

function assertPostOrigin(request) {
  const origin = request.headers.origin;
  if (!origin) {
    return;
  }

  const host = request.headers.host;
  if (new URL(origin).host !== host) {
    const error = new Error("Invalid request origin.");
    error.status = 403;
    throw error;
  }
}

async function requestVerificationCode({ db, email, sendVerificationEmail }) {
  const normalizedEmail = normalizeEmail(email);
  if (!isTempleEmail(normalizedEmail)) {
    const error = new Error("Only Temple University email addresses can access this website.");
    error.status = 400;
    throw error;
  }

  const now = Date.now();
  const recentCodes = db.getRecentVerificationCodes(normalizedEmail, now - 60 * 60 * 1000);
  if (recentCodes.length >= MAX_CODES_PER_HOUR) {
    const error = new Error("Too many verification codes requested. Please try again later.");
    error.status = 429;
    throw error;
  }

  const latestCode = recentCodes.sort((a, b) => {
    return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
  })[0];

  if (latestCode && now - new Date(latestCode.createdAt).getTime() < MIN_RESEND_INTERVAL_MS) {
    const error = new Error("Please wait before requesting another verification code.");
    error.status = 429;
    throw error;
  }

  const code = randomCode();
  db.createVerificationCode({
    email: normalizedEmail,
    codeHash: hmac(`${normalizedEmail}:${code}`),
    expiresAt: new Date(now + CODE_TTL_MS).toISOString()
  });

  await sendVerificationEmail({ email: normalizedEmail, code });

  return {
    email: normalizedEmail,
    expiresInSeconds: CODE_TTL_MS / 1000
  };
}

function verifyCode({ db, email, code }) {
  const normalizedEmail = normalizeEmail(email);
  if (!isTempleEmail(normalizedEmail)) {
    const error = new Error("Only Temple University email addresses can access this website.");
    error.status = 400;
    throw error;
  }

  const normalizedCode = String(code || "").trim();
  if (!/^\d{6}$/.test(normalizedCode)) {
    const error = new Error("Enter the 6-digit verification code.");
    error.status = 400;
    throw error;
  }

  const codeEntry = db.getLatestUsableVerificationCode(normalizedEmail);
  if (!codeEntry || codeEntry.attempts >= MAX_CODE_ATTEMPTS) {
    const error = new Error("That verification code is invalid or expired.");
    error.status = 400;
    throw error;
  }

  const submittedHash = hmac(`${normalizedEmail}:${normalizedCode}`);
  if (!safeEqualHex(submittedHash, codeEntry.codeHash)) {
    db.incrementVerificationAttempts(codeEntry.id);
    const error = new Error("That verification code is invalid or expired.");
    error.status = 400;
    throw error;
  }

  db.markVerificationCodeUsed(codeEntry.id);
  const existingUser = db.findUserByEmail(normalizedEmail);

  if (existingUser) {
    return {
      user: existingUser,
      needsUsername: false
    };
  }

  const signupToken = randomToken();
  db.createSignupToken({
    tokenHash: hmac(signupToken),
    email: normalizedEmail,
    expiresAt: new Date(Date.now() + SIGNUP_MAX_AGE_SECONDS * 1000).toISOString()
  });

  return {
    needsUsername: true,
    signupCookie: serializeCookie(SIGNUP_COOKIE, signupToken, { maxAge: SIGNUP_MAX_AGE_SECONDS })
  };
}

function completeSignup({ db, request, username }) {
  const normalizedUsername = normalizeUsername(username);
  const validationError = validateUsername(normalizedUsername);
  if (validationError) {
    const error = new Error(validationError);
    error.status = 400;
    throw error;
  }

  if (db.findUserByUsername(normalizedUsername)) {
    const error = new Error("That username is already taken.");
    error.status = 409;
    throw error;
  }

  const cookies = parseCookies(request.headers.cookie);
  const signupToken = cookies[SIGNUP_COOKIE];
  if (!signupToken) {
    const error = new Error("Your signup session expired. Please verify your email again.");
    error.status = 401;
    throw error;
  }

  const pendingSignup = db.consumeSignupToken(hmac(signupToken));
  if (!pendingSignup) {
    const error = new Error("Your signup session expired. Please verify your email again.");
    error.status = 401;
    throw error;
  }

  let user;
  try {
    user = db.createUser({
      email: pendingSignup.email,
      username: normalizedUsername
    });
  } catch (error) {
    if (error.code === "USERNAME_TAKEN") {
      error.status = 409;
    }
    throw error;
  }

  return user;
}

module.exports = {
  SESSION_COOKIE,
  SIGNUP_COOKIE,
  assertPostOrigin,
  clearCookie,
  completeSignup,
  createSession,
  deleteCurrentSession,
  getAuthenticatedUser,
  publicUser,
  requestVerificationCode,
  verifyCode
};
