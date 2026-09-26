function isProduction() {
  return process.env.NODE_ENV === "production";
}

function boolEnv(value) {
  return String(value).toLowerCase() === "true";
}

function getSmtpConfig() {
  const host = process.env.SMTP_HOST;
  const from = process.env.SMTP_FROM;

  if (!host || !from) {
    return null;
  }

  const user = process.env.SMTP_USER;
  const pass = process.env.SMTP_PASS;

  return {
    host,
    port: Number(process.env.SMTP_PORT || 587),
    secure: boolEnv(process.env.SMTP_SECURE),
    auth: user && pass ? { user, pass } : undefined,
    from
  };
}

async function sendVerificationEmail({ email, code }) {
  if (!isProduction() && boolEnv(process.env.AUTH_LOG_VERIFICATION_CODES)) {
    console.log(`[auth] Verification code for ${email}: ${code}`);
    return;
  }

  const config = getSmtpConfig();
  if (!config) {
    const error = new Error(
      "Email delivery is not configured. Set SMTP_HOST, SMTP_PORT, SMTP_FROM, and SMTP credentials."
    );
    error.code = "EMAIL_NOT_CONFIGURED";
    throw error;
  }

  const nodemailer = require("nodemailer");
  const transporter = nodemailer.createTransport({
    host: config.host,
    port: config.port,
    secure: config.secure,
    auth: config.auth
  });

  await transporter.sendMail({
    from: config.from,
    to: email,
    subject: "Your FriendsNMe verification code",
    text: `Your FriendsNMe verification code is ${code}. It expires in 10 minutes.`,
    html: `<p>Your FriendsNMe verification code is <strong>${code}</strong>.</p><p>It expires in 10 minutes.</p>`
  });
}

module.exports = { sendVerificationEmail };
