/** Which ADEM portal this app is: one sign-in for school management and the teachers they invite. */
export const PORTAL = "web" as const;
export const APP_NAME = "for Schools";
export const APP_TAGLINE = "Read every script. Mark it fairly. Return it faster.";

// The backend this app talks to. To switch, comment out one API_BASE line and uncomment the other.
// Under `npm run dev` calls go to this dev server's /api, and vite.config.ts forwards them to the URL on the live line,
// so the browser never makes a cross-site call in development.
export const API_BASE = import.meta.env.DEV ? `${window.location.origin}/api` : "http://localhost:8000/api";
// export const API_BASE = import.meta.env.DEV ? `${window.location.origin}/api` : "https://api.example.com/api"; // live: put the real backend domain here

// The other ADEM apps, for links between them. Switch together with API_BASE.
export const WEB_URL = "http://localhost:5173";
export const ADMIN_URL = "http://localhost:5174";
export const PARENT_URL = "http://localhost:5175";
// export const WEB_URL = "https://app.example.com";
// export const ADMIN_URL = "https://admin.example.com";
// export const PARENT_URL = "https://parents.example.com";
