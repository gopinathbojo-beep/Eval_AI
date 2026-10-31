import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";

interface GsiId {
  initialize(o: { client_id: string; callback: (r: { credential: string }) => void }): void;
  renderButton(el: HTMLElement, o: Record<string, unknown>): void;
}
declare global { interface Window { google?: { accounts: { id: GsiId } } } }

let clientId: Promise<string | null> | null = null;
const loadClientId = () =>
  (clientId ??= api<{ google_client_id: string | null }>("/public/config").then((c) => c.google_client_id).catch(() => null));

let script: Promise<void> | null = null;
const loadScript = () =>
  (script ??= new Promise<void>((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Google sign-in could not load."));
    document.head.appendChild(s);
  }));

/** "Continue with Google". Renders nothing while Google sign-in is not set up on the server. */
export function GoogleButton({ onToken, text = "continue_with" }: { onToken(idToken: string): void; text?: "continue_with" | "signup_with" }) {
  const el = useRef<HTMLDivElement>(null);
  const [enabled, setEnabled] = useState(false);
  const cb = useRef(onToken);
  cb.current = onToken;

  useEffect(() => {
    let live = true;
    loadClientId().then(async (id) => {
      if (!id || !live) return;
      await loadScript();
      if (!live || !el.current || !window.google) return;
      window.google.accounts.id.initialize({ client_id: id, callback: (r) => cb.current(r.credential) });
      window.google.accounts.id.renderButton(el.current, { theme: "outline", size: "large", width: 320, text });
      setEnabled(true);
    }).catch(() => {});
    return () => { live = false; };
  }, [text]);

  return (
    <div className={enabled ? "space-y-4" : "hidden"}>
      <div ref={el} className="flex justify-center" />
      <div className="flex items-center gap-3 text-xs uppercase tracking-[0.14em] text-mute">
        <span className="h-px flex-1 bg-line" />or<span className="h-px flex-1 bg-line" />
      </div>
    </div>
  );
}
