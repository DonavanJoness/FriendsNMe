const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

const DEFAULT_DATA = {
  users: [],
  verificationCodes: [],
  sessions: [],
  signupTokens: []
};

class Database {
  constructor(filePath = path.join(__dirname, "data", "auth-db.json")) {
    this.filePath = filePath;
    this.data = this.load();
  }

  load() {
    fs.mkdirSync(path.dirname(this.filePath), { recursive: true });

    if (!fs.existsSync(this.filePath)) {
      this.write(DEFAULT_DATA);
      return structuredClone(DEFAULT_DATA);
    }

    const parsed = JSON.parse(fs.readFileSync(this.filePath, "utf8"));
    return {
      ...structuredClone(DEFAULT_DATA),
      ...parsed
    };
  }

  write(data = this.data) {
    const tempPath = `${this.filePath}.${process.pid}.tmp`;
    fs.writeFileSync(tempPath, JSON.stringify(data, null, 2));
    fs.renameSync(tempPath, this.filePath);
  }

  save() {
    this.write(this.data);
  }

  cleanup(now = Date.now()) {
    this.data.verificationCodes = this.data.verificationCodes.filter((entry) => {
      return !entry.usedAt && new Date(entry.expiresAt).getTime() > now - 60 * 60 * 1000;
    });
    this.data.sessions = this.data.sessions.filter((entry) => {
      return new Date(entry.expiresAt).getTime() > now;
    });
    this.data.signupTokens = this.data.signupTokens.filter((entry) => {
      return new Date(entry.expiresAt).getTime() > now;
    });
    this.save();
  }

  findUserByEmail(email) {
    return this.data.users.find((user) => user.email === email) || null;
  }

  findUserById(id) {
    return this.data.users.find((user) => user.id === id) || null;
  }

  findUserByUsername(username) {
    const usernameLower = username.toLowerCase();
    return this.data.users.find((user) => user.usernameLower === usernameLower) || null;
  }

  updateUserLocation(userId, location) {
    const user = this.findUserById(userId);
    if (!user) {
      return null;
    }

    user.lastLocation = {
      latitude: location.latitude,
      longitude: location.longitude,
      accuracy: location.accuracy,
      capturedAt: location.capturedAt,
      updatedAt: new Date().toISOString()
    };
    this.save();
    return user.lastLocation;
  }

  createUser({ email, username }) {
    if (this.findUserByEmail(email)) {
      const error = new Error("An account already exists for this Temple email.");
      error.code = "EMAIL_TAKEN";
      throw error;
    }

    if (this.findUserByUsername(username)) {
      const error = new Error("That username is already taken.");
      error.code = "USERNAME_TAKEN";
      throw error;
    }

    const user = {
      id: crypto.randomUUID(),
      email,
      username,
      usernameLower: username.toLowerCase(),
      lastLocation: null,
      createdAt: new Date().toISOString()
    };

    this.data.users.push(user);
    this.save();
    return user;
  }

  createVerificationCode({ email, codeHash, expiresAt }) {
    const entry = {
      id: crypto.randomUUID(),
      email,
      codeHash,
      expiresAt,
      createdAt: new Date().toISOString(),
      attempts: 0,
      usedAt: null
    };

    this.data.verificationCodes.push(entry);
    this.save();
    return entry;
  }

  getRecentVerificationCodes(email, sinceMs) {
    return this.data.verificationCodes.filter((entry) => {
      return entry.email === email && new Date(entry.createdAt).getTime() >= sinceMs;
    });
  }

  getLatestUsableVerificationCode(email) {
    const now = Date.now();
    return this.data.verificationCodes
      .filter((entry) => {
        return (
          entry.email === email &&
          !entry.usedAt &&
          new Date(entry.expiresAt).getTime() > now
        );
      })
      .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())[0] || null;
  }

  incrementVerificationAttempts(id) {
    const entry = this.data.verificationCodes.find((code) => code.id === id);
    if (entry) {
      entry.attempts += 1;
      this.save();
    }
    return entry;
  }

  markVerificationCodeUsed(id) {
    const entry = this.data.verificationCodes.find((code) => code.id === id);
    if (entry) {
      entry.usedAt = new Date().toISOString();
      this.save();
    }
    return entry;
  }

  createSession({ sessionHash, userId, expiresAt }) {
    const session = {
      sessionHash,
      userId,
      createdAt: new Date().toISOString(),
      lastSeenAt: new Date().toISOString(),
      expiresAt
    };

    this.data.sessions.push(session);
    this.save();
    return session;
  }

  findSession(sessionHash) {
    const now = Date.now();
    const session = this.data.sessions.find((entry) => entry.sessionHash === sessionHash);

    if (!session || new Date(session.expiresAt).getTime() <= now) {
      return null;
    }

    session.lastSeenAt = new Date().toISOString();
    this.save();
    return session;
  }

  deleteSession(sessionHash) {
    const before = this.data.sessions.length;
    this.data.sessions = this.data.sessions.filter((entry) => entry.sessionHash !== sessionHash);
    if (this.data.sessions.length !== before) {
      this.save();
    }
  }

  createSignupToken({ tokenHash, email, expiresAt }) {
    this.data.signupTokens = this.data.signupTokens.filter((entry) => entry.email !== email);

    const token = {
      tokenHash,
      email,
      createdAt: new Date().toISOString(),
      expiresAt
    };

    this.data.signupTokens.push(token);
    this.save();
    return token;
  }

  consumeSignupToken(tokenHash) {
    const now = Date.now();
    const token = this.data.signupTokens.find((entry) => {
      return entry.tokenHash === tokenHash && new Date(entry.expiresAt).getTime() > now;
    });

    if (!token) {
      return null;
    }

    this.data.signupTokens = this.data.signupTokens.filter((entry) => entry.tokenHash !== tokenHash);
    this.save();
    return token;
  }
}

module.exports = { Database };
