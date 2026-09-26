const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

const { Database } = require("./database");
const { sendVerificationEmail } = require("./email");
const {
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
} = require("./auth");

const PORT = Number(process.env.PORT || 3000);
const FRONTEND_DIR = path.join(__dirname, "..", "Frontend");
const db = new Database();

setInterval(() => db.cleanup(), 5 * 60 * 1000).unref();
db.cleanup();

function sendJson(response, status, payload, headers = {}) {
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    ...headers
  });
  response.end(JSON.stringify(payload));
}

function sendError(response, error) {
  const status = error.status || (error.code === "EMAIL_NOT_CONFIGURED" ? 503 : 500);
  const message = status === 500 ? "Something went wrong. Please try again." : error.message;
  if (status === 500) {
    console.error(error);
  }
  sendJson(response, status, { error: message });
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(chunk);
    if (Buffer.concat(chunks).length > 1024 * 1024) {
      const error = new Error("Request body is too large.");
      error.status = 413;
      throw error;
    }
  }

  if (!chunks.length) {
    return {};
  }

  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    const error = new Error("Invalid JSON request.");
    error.status = 400;
    throw error;
  }
}

function setCookies(...cookies) {
  return { "Set-Cookie": cookies };
}

function getRequiredUser(request) {
  const user = getAuthenticatedUser(db, request);
  if (!user) {
    const error = new Error("You must be signed in to use this feature.");
    error.status = 401;
    throw error;
  }
  return user;
}

function parseCoordinate(value, { min, max, name }) {
  const number = Number(value);
  if (!Number.isFinite(number) || number < min || number > max) {
    const error = new Error(`${name} must be a number between ${min} and ${max}.`);
    error.status = 400;
    throw error;
  }
  return number;
}

function parseAccuracy(value) {
  if (value === undefined || value === null) {
    return null;
  }

  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) {
    const error = new Error("Accuracy must be a positive number.");
    error.status = 400;
    throw error;
  }
  return number;
}

function parseCapturedAt(value) {
  if (!value) {
    return new Date().toISOString();
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    const error = new Error("capturedAt must be a valid date.");
    error.status = 400;
    throw error;
  }

  return date.toISOString();
}

async function handleApi(request, response, url) {
  try {
    if (request.method !== "GET") {
      assertPostOrigin(request);
    }

    if (request.method === "GET" && url.pathname === "/api/auth/session") {
      const user = getAuthenticatedUser(db, request);
      if (!user) {
        return sendJson(response, 401, { authenticated: false });
      }

      return sendJson(response, 200, {
        authenticated: true,
        user: publicUser(user)
      });
    }

    if (request.method === "POST" && url.pathname === "/api/auth/request-code") {
      const body = await readJson(request);
      const result = await requestVerificationCode({
        db,
        email: body.email,
        sendVerificationEmail
      });
      return sendJson(response, 200, {
        ok: true,
        email: result.email,
        expiresInSeconds: result.expiresInSeconds
      });
    }

    if (request.method === "POST" && url.pathname === "/api/auth/verify-code") {
      const body = await readJson(request);
      const result = verifyCode({
        db,
        email: body.email,
        code: body.code
      });

      if (result.needsUsername) {
        return sendJson(
          response,
          200,
          { ok: true, needsUsername: true },
          setCookies(result.signupCookie)
        );
      }

      const session = createSession(db, result.user);
      return sendJson(
        response,
        200,
        {
          ok: true,
          needsUsername: false,
          user: publicUser(result.user)
        },
        setCookies(session.cookie, clearCookie(SIGNUP_COOKIE))
      );
    }

    if (request.method === "POST" && url.pathname === "/api/auth/complete-signup") {
      const body = await readJson(request);
      const user = completeSignup({
        db,
        request,
        username: body.username
      });
      const session = createSession(db, user);
      return sendJson(
        response,
        201,
        {
          ok: true,
          user: publicUser(user)
        },
        setCookies(session.cookie, clearCookie(SIGNUP_COOKIE))
      );
    }

    if (request.method === "POST" && url.pathname === "/api/auth/logout") {
      deleteCurrentSession(db, request);
      return sendJson(response, 200, { ok: true }, setCookies(clearCookie("fnm_session"), clearCookie(SIGNUP_COOKIE)));
    }

    if (request.method === "POST" && url.pathname === "/api/location") {
      const user = getRequiredUser(request);
      const body = await readJson(request);
      const location = db.updateUserLocation(user.id, {
        latitude: parseCoordinate(body.latitude, { min: -90, max: 90, name: "Latitude" }),
        longitude: parseCoordinate(body.longitude, { min: -180, max: 180, name: "Longitude" }),
        accuracy: parseAccuracy(body.accuracy),
        capturedAt: parseCapturedAt(body.capturedAt)
      });

      return sendJson(response, 200, {
        ok: true,
        location
      });
    }

    if (request.method === "GET" && url.pathname === "/api/location/me") {
      const user = getRequiredUser(request);
      return sendJson(response, 200, {
        ok: true,
        location: user.lastLocation || null
      });
    }

    return sendJson(response, 404, { error: "Not found." });
  } catch (error) {
    return sendError(response, error);
  }
}

function contentType(filePath) {
  const ext = path.extname(filePath);
  return {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml"
  }[ext] || "application/octet-stream";
}

function serveStatic(request, response, url) {
  const requestedPath = url.pathname === "/" ? "/index.html" : url.pathname;
  const filePath = path.normalize(path.join(FRONTEND_DIR, requestedPath));
  const relativePath = path.relative(FRONTEND_DIR, filePath);

  if (relativePath.startsWith("..") || path.isAbsolute(relativePath)) {
    response.writeHead(403);
    response.end("Forbidden");
    return;
  }

  fs.readFile(filePath, (error, data) => {
    if (error) {
      response.writeHead(404);
      response.end("Not found");
      return;
    }

    response.writeHead(200, {
      "Content-Type": contentType(filePath),
      "Cache-Control": filePath.endsWith(".html") ? "no-store" : "public, max-age=300"
    });
    response.end(data);
  });
}

const server = http.createServer((request, response) => {
  const url = new URL(request.url, `http://${request.headers.host}`);
  if (url.pathname.startsWith("/api/")) {
    handleApi(request, response, url);
    return;
  }

  serveStatic(request, response, url);
});

server.listen(PORT, () => {
  console.log(`FriendsNMe running at http://localhost:${PORT}`);
});
