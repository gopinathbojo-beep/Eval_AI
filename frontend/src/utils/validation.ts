/** Format checks for sign-in and registration; they mirror backend/app/validation.py. Each returns a message or null. */

const EMAIL = /^[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$/;

export const emailProblem = (v: string) =>
  !v.trim() ? "Enter your email address." : EMAIL.test(v.trim()) && v.trim().length <= 254 ? null
    : "Enter a valid email address, like name@school.edu.";

/** Letters in any script (Tamil, Hindi…), spaces, dots, apostrophes and hyphens; at least two letters. */
export const nameProblem = (v: string, what = "Name") => {
  const s = v.trim();
  if ((s.match(/\p{L}/gu) ?? []).length < 2) return `${what} must have at least two letters.`;
  return /^[\p{L}\p{M} .'-]+$/u.test(s) ? null : `${what} can contain only letters, spaces, dots, apostrophes and hyphens.`;
};

export const placeProblem = (v: string, what: string) =>
  (v.trim().match(/\p{L}/gu) ?? []).length < 2 ? `${what} must have at least two letters.` : null;

/** 10 digits once spaces, dashes, brackets and a +91 / 0 prefix are removed (landlines included). */
export const phoneProblem = (v: string) => {
  const d = v.replace(/[\s\-()]/g, "").replace(/^(\+91|0091|91(?=\d{10}$)|0(?=\d{10}$))/, "");
  return /^\d{10}$/.test(d) ? null : "Enter a valid 10-digit phone number.";
};

export const pinProblem = (v: string) => (/^[1-9]\d{5}$/.test(v.replace(/\s/g, "")) ? null : "Enter a valid 6-digit PIN code.");

/** New-password rules, shown as a live checklist. The backend enforces the same (routes/registration.py). */
export const passwordRules: { label: string; ok: (v: string) => boolean; problem: string }[] = [
  { label: "At least 8 characters", ok: (v) => v.length >= 8, problem: "Use at least 8 characters for your password." },
  { label: "Starts with a capital letter", ok: (v) => /^\p{Lu}/u.test(v), problem: "Start your password with a capital letter." },
  { label: "At least one number", ok: (v) => /\d/.test(v), problem: "Add at least one number to your password." },
  { label: "At least one special character", ok: (v) => /[^\p{L}\p{N}]/u.test(v), problem: "Add at least one special character (like @, # or !) to your password." },
];

export const passwordProblem = (v: string) =>
  passwordRules.find((r) => !r.ok(v))?.problem
    ?? (new TextEncoder().encode(v).length > 72 ? "Your password is too long (72 bytes at most)." : null);
