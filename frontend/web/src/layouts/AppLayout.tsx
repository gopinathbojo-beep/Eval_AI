import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { Link, NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../context/Auth";
import { CrumbProvider, useCrumbNames } from "../context/Crumbs";
import { useApi } from "../hooks/useApi";
import type { Dashboard } from "../types";
import { BrandLabel } from "../components/Brand";
import { ThemeToggle } from "../components/ThemeToggle";
import { CommandPalette } from "../components/CommandPalette";
import {
  IconDashboard,
  IconExam,
  IconEvaluation,
  IconResults,
  IconClasses,
  IconStudents,
  IconSubjects,
  IconSettings,
  IconLogOut,
  IconMenu,
  IconX,
  IconChevronRight,
  IconPlus,
  IconUpload,
} from "../components/Icons";

type IconType = React.ComponentType<{ size?: number; className?: string }>;
type BadgeKey = "pending";

interface NavItem {
  to: string;
  label: string;
  icon: IconType;
  badge?: BadgeKey;
}

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Main",
    items: [
      { to: "/dashboard", label: "Dashboard", icon: IconDashboard },
      { to: "/exams", label: "Exams", icon: IconExam },
      {
        to: "/evaluations",
        label: "Evaluations",
        icon: IconEvaluation,
        badge: "pending",
      },
      { to: "/results", label: "Results", icon: IconResults },
    ],
  },
  {
    label: "Academic Management",
    items: [
      { to: "/classes", label: "Classes", icon: IconClasses },
      { to: "/students", label: "Students", icon: IconStudents },
      { to: "/subjects", label: "Subjects", icon: IconSubjects },
    ],
  },
];

const ALL_PAGES = [
  ...NAV_GROUPS.flatMap((g) => g.items),
  { to: "/settings", label: "Settings", icon: IconSettings },
];

/** Phone tab bar; everything else lives behind "More" (the drawer). */
const TAB_BAR: NavItem[] = [
  { to: "/dashboard", label: "Home", icon: IconDashboard },
  { to: "/exams", label: "Exams", icon: IconExam },
  {
    to: "/evaluations",
    label: "Evaluate",
    icon: IconEvaluation,
    badge: "pending",
  },
  { to: "/results", label: "Results", icon: IconResults },
];

const BREADCRUMBS: Record<string, string> = {
  dashboard: "Dashboard",
  classes: "Classes",
  students: "Students",
  subjects: "Subjects",
  exams: "Exams",
  new: "Create Exam",
  evaluations: "Evaluations",
  results: "Results",
  settings: "Settings",
  admin: "Administration",
  management: "School management",
  family: "Family profile",
  content: "Setup",
  overview: "Overview",
  submissions: "Answer Sheets",
  "question-paper": "Question Paper",
  questions: "Questions",
  "answer-key": "Answer Key",
  "answer-sheets": "Answer Sheets",
  evaluation: "Assessment",
};

const POLL_MS = 60_000;

interface AiStatus {
  available: boolean;
  model: string;
  url: string;
  message: string;
  detail?: string;
}

/** Irregular wax rim: a circle with soft, uneven lobes (viewBox 0 0 48 48, centred at 24,24). */
const WAX_EDGE = (() => {
  const lobes = 18;
  const pts = Array.from({ length: lobes * 2 }, (_, i) => {
    const a = (i / (lobes * 2)) * Math.PI * 2;
    const r = i % 2 ? 21.2 : 23 - ((i * 7) % 5) * 0.25; // outer lobes vary slightly, like poured wax
    return [24 + r * Math.cos(a), 24 + r * Math.sin(a)] as const;
  });
  // Smooth through midpoints so lobes read as rounded drips, not star points
  const mid = (p: readonly [number, number], q: readonly [number, number]) => [
    (p[0] + q[0]) / 2,
    (p[1] + q[1]) / 2,
  ];
  const start = mid(pts[pts.length - 1]!, pts[0]!);
  let d = `M${start[0]!.toFixed(2)} ${start[1]!.toFixed(2)}`;
  pts.forEach((p, i) => {
    const m = mid(p, pts[(i + 1) % pts.length]!);
    d += ` Q${p[0].toFixed(2)} ${p[1].toFixed(2)} ${m[0]!.toFixed(2)} ${m[1]!.toFixed(2)}`;
  });
  return `${d} Z`;
})();

/** Elements Tab can land on inside a container. */
const focusables = (root: HTMLElement) =>
  Array.from(
    root.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  );

/** Close a popover on an outside click. */
function useOutsideClick(
  ref: React.RefObject<HTMLElement>,
  open: boolean,
  close: () => void,
) {
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) =>
      !ref.current?.contains(e.target as Node) && close();
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open, ref, close]);
}

/** Profile as a red wax seal pressed onto the right of the header; opens an account card. */
function ProfileBookmark({
  name,
  email,
  onLogout,
}: {
  name: string;
  email: string;
  onLogout: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const gradientId = `wax-fill-${useId().replace(/:/g, "")}`;
  useOutsideClick(ref, open, () => setOpen(false));

  // Opening moves focus to the first item, as a menu button should
  useEffect(() => {
    if (open && menuRef.current) focusables(menuRef.current)[0]?.focus();
  }, [open]);

  const onMenuKeyDown = (e: ReactKeyboardEvent) => {
    const items = menuRef.current ? focusables(menuRef.current) : [];
    const i = items.indexOf(document.activeElement as HTMLElement);
    const move: Record<string, number> = {
      ArrowDown: i + 1,
      ArrowUp: i - 1,
      Home: 0,
      End: items.length - 1,
    };
    if (e.key in move) {
      e.preventDefault();
      items[(move[e.key]! + items.length) % items.length]?.focus();
    } else if (e.key === "Escape") {
      // Don't let the same key press also close a dialog or drawer behind the menu
      e.stopPropagation();
      setOpen(false);
      buttonRef.current?.focus();
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  };

  const initials =
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0]!.toUpperCase())
      .join("") || "T";

  return (
    <div
      ref={ref}
      className="relative flex h-14 w-14 shrink-0 items-center justify-center self-start"
    >
      <button
        ref={buttonRef}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" && !open) {
            e.preventDefault();
            setOpen(true);
          }
        }}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account: ${name}`}
        title={name}
        className={`group relative flex h-12 w-12 items-center justify-center rounded-full drop-shadow-[0_2px_2px_rgb(0_0_0/0.3)] transition-transform duration-200 ease-out hover:-translate-y-0.5 hover:scale-110 ${
          open ? "-translate-y-0.5 scale-110" : ""
        }`}
      >
        <svg
          viewBox="0 0 48 48"
          className="absolute inset-0 h-full w-full"
          aria-hidden
        >
          <defs>
            <radialGradient id={gradientId} cx="38%" cy="32%" r="70%">
              <stop offset="0%" stopColor="#de5a44" />
              <stop offset="55%" stopColor="#c43a28" />
              <stop offset="100%" stopColor="#962a1c" />
            </radialGradient>
          </defs>
          <path d={WAX_EDGE} fill={`url(#${gradientId})`} />
          {/* Pressed stamp: dark groove with a light lip, like an embossed ring */}
          <circle
            cx="24"
            cy="24"
            r="15.5"
            fill="none"
            stroke="#7d2116"
            strokeOpacity="0.55"
            strokeWidth="1.6"
          />
          <circle
            cx="24"
            cy="24.6"
            r="15.5"
            fill="none"
            stroke="#fff7e6"
            strokeOpacity="0.28"
            strokeWidth="0.8"
          />
          <circle cx="24" cy="24" r="12.5" fill="#b33424" fillOpacity="0.45" />
        </svg>
        <span className="relative font-display text-[15px] font-semibold leading-none tracking-wide text-[#fff7e6] [text-shadow:0_1px_0_rgb(125_33_22/0.8)]">
          {initials}
        </span>
      </button>

      {open && (
        <div
          ref={menuRef}
          role="menu"
          aria-label="Account"
          onKeyDown={onMenuKeyDown}
          className="absolute right-0 top-[60px] z-50 w-64 animate-rise overflow-hidden rounded-lg border border-line border-t-4 border-t-mark bg-surface shadow-pop"
        >
          <div className="border-b border-dashed border-line px-4 py-3">
            <p className="truncate font-display text-base font-semibold text-ink">
              {name}
            </p>
            <p className="truncate text-xs text-mute">{email}</p>
          </div>
          <div className="p-1.5">
            <ThemeToggle menuItem />
            <Link
              role="menuitem"
              to="/account"
              onClick={() => setOpen(false)}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-ink transition-ui hover:bg-hover hover:text-brown focus-visible:bg-hover"
            >
              <IconSettings size={16} className="text-mute" />
              Account settings
            </Link>
            <button
              role="menuitem"
              onClick={onLogout}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm text-mark transition-ui hover:bg-mark-soft focus-visible:bg-mark-soft"
            >
              <IconLogOut size={16} />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Compact "AI offline" pill for the header; the detail sits in a popover instead of a page-wide banner. */
function AiStatusPill({ status }: { status: AiStatus }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useOutsideClick(ref, open, () => setOpen(false));

  return (
    <div
      ref={ref}
      className="relative"
      onKeyDown={(e) => {
        if (e.key !== "Escape" || !open) return;
        e.stopPropagation();
        setOpen(false);
      }}
    >
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex items-center gap-1.5 rounded-full border border-warn/40 bg-warn-soft px-2.5 py-1 text-xs font-semibold text-warn transition-ui hover:bg-warn/15"
      >
        <span
          aria-hidden
          className="h-2 w-2 animate-pulse rounded-full bg-warn"
        />
        <span className="hidden sm:inline">AI offline</span>
        <span className="sm:hidden">AI</span>
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="AI status"
          className="absolute right-0 top-10 z-50 w-72 animate-rise rounded-lg border border-line bg-surface p-4 text-xs text-ink shadow-pop"
        >
          <p className="font-display text-sm font-semibold">Offline AI mode</p>
          <p className="mt-1.5 text-mute">
            {status.message || "The local AI model is currently offline."}
          </p>
          <p className="mt-1.5 text-mute">
            Manual grading, transcription review and marksheet export still
            work.
          </p>
          {status.detail && (
            <p className="mt-2 rounded bg-sunken px-2 py-1.5 font-mono text-[11px] text-mute">
              {status.detail}
            </p>
          )}
          <Link
            to="/settings"
            onClick={() => setOpen(false)}
            className="mt-3 inline-block font-semibold text-warn underline underline-offset-2 hover:text-brown"
          >
            Open AI diagnostics
          </Link>
        </div>
      )}
    </div>
  );
}

function CountBadge({
  count,
  className = "",
}: {
  count: number;
  className?: string;
}) {
  if (!count) return null;
  return (
    <span
      className={`min-w-[1.25rem] rounded-full bg-mark px-1.5 text-center text-[10px] font-semibold leading-5 text-white ${className}`}
      aria-label={`${count} pending`}
    >
      {count > 99 ? "99+" : count}
    </span>
  );
}

/** Layout-shaped placeholder shown while the session is checked, so the app appears at once. */
function ShellSkeleton() {
  return (
    <div
      className="flex h-full overflow-hidden bg-paper"
      aria-busy="true"
      aria-label="Loading"
    >
      <aside className="hidden w-64 shrink-0 bg-cover p-5 lg:block">
        <div className="mb-8 h-10 w-36 animate-pulse rounded-md bg-cover-line/10" />
        {Array.from({ length: 7 }, (_, i) => (
          <div
            key={i}
            className="mb-3 h-8 animate-pulse rounded-md bg-cover-line/[0.06]"
          />
        ))}
      </aside>
      <div className="flex flex-1 flex-col">
        <div className="h-14 border-b border-line bg-surface/80" />
        <div className="mx-auto w-full max-w-7xl space-y-4 p-4 sm:p-6 lg:p-8">
          <div className="h-28 animate-pulse rounded-lg bg-sunken" />
          <div className="grid gap-4 sm:grid-cols-3">
            {Array.from({ length: 3 }, (_, i) => (
              <div
                key={i}
                className="h-24 animate-pulse rounded-lg bg-sunken"
              />
            ))}
          </div>
          <div className="h-64 animate-pulse rounded-lg bg-sunken" />
        </div>
      </div>
    </div>
  );
}

export function AppLayout() {
  return (
    <CrumbProvider>
      <AppShell />
    </CrumbProvider>
  );
}

function AppShell() {
  const { user, teacher, loading, logout } = useAuth();
  const loc = useLocation();
  const crumbNames = useCrumbNames();
  const [sidebarOpen, setSidebarOpen] = useState(false); // Mobile drawer state
  const [paletteOpen, setPaletteOpen] = useState(false);
  const drawerRef = useRef<HTMLDivElement>(null);
  // Re-checked every minute so the offline pill clears on its own once the model is back
  const workspaceReady =
    teacher?.profile_complete &&
    !teacher.must_change_password &&
    !teacher.is_admin;
  const { data: aiStatus } = useApi<AiStatus>(
    workspaceReady ? "/system/ai-status" : null,
    () => POLL_MS,
  );
  const { data: dash } = useApi<Dashboard>(
    workspaceReady ? "/dashboard" : null,
    () => POLL_MS,
  );
  const badges: Record<BadgeKey, number> = {
    pending: dash?.pending_evaluations ?? 0,
  };

  // Close mobile sidebar on route change
  useEffect(() => {
    setSidebarOpen(false);
  }, [loc.pathname]);

  // Mobile drawer: focus moves in on open, Tab stays inside, Escape closes, focus returns to the opener
  useEffect(() => {
    const panel = drawerRef.current;
    if (!sidebarOpen || !panel) return;
    const opener = document.activeElement as HTMLElement | null;
    focusables(panel)[0]?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") return setSidebarOpen(false);
      if (e.key !== "Tab") return;
      const items = focusables(panel);
      const first = items[0],
        last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last?.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (panel.contains(document.activeElement)) opener?.focus();
    };
  }, [sidebarOpen]);

  // Ctrl/⌘ K opens search from anywhere
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "k" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Generate breadcrumbs from route path
  const pathSegments = loc.pathname.split("/").filter(Boolean);
  const crumbLabel = (seg: string) =>
    crumbNames[seg] || BREADCRUMBS[seg] || (seg.length > 15 ? "Details" : seg);

  // Browser tab title follows the page, so several open tabs can be told apart
  const pageName = pathSegments.length
    ? crumbLabel(pathSegments[pathSegments.length - 1]!)
    : "Dashboard";
  useEffect(() => {
    document.title = `${pageName} · Eval AI`;
  }, [pageName]);

  // Exam pages on a phone get a shortcut to upload answer sheets, the main thing done from a phone
  const examId =
    pathSegments[0] === "exams" && pathSegments[1] && pathSegments[1] !== "new"
      ? pathSegments[1]
      : null;
  const onUploadPage = ["submissions", "answer-sheets"].includes(
    pathSegments[2] ?? "",
  );

  if (loading) return <ShellSkeleton />;
<<<<<<< 7c662e7:frontend/web/src/layouts/AppLayout.tsx
  if (!teacher) return user ? <Navigate to="/school" replace /> : <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  if (teacher.must_change_password) return <Navigate to="/change-password" replace />;
=======
  if (!teacher)
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  if (teacher.must_change_password) return <Navigate to="/account" replace />;
  if (!teacher.is_admin && !teacher.profile_complete)
    return <Navigate to="/onboarding" replace />;
  if (teacher.is_admin && loc.pathname !== "/admin")
    return <Navigate to="/admin" replace />;
>>>>>>> kishore/Version2.0:frontend/src/layouts/AppLayout.tsx

  const navContent = (
    <div className="flex h-full flex-col">
      {/* Brand & Navigation */}
      <div className="flex-1 overflow-y-auto px-4 py-5">
        <Link
          to={teacher.is_admin ? "/admin" : "/dashboard"}
          className="mb-7 block px-1"
          aria-label="Eval AI dashboard"
        >
          <BrandLabel />
          <p className="mt-2.5 pl-1 font-doc text-xs italic text-cover-ink/60">
            the examiner&rsquo;s desk
          </p>
        </Link>

        <div className="space-y-6">
          {[
            ...(teacher.is_admin
              ? []
              : NAV_GROUPS.map((g) => ({
                  ...g,
                  items: g.items.filter(
                    (i) =>
                      !(
                        teacher.role === "PARENT" &&
                        ["/classes", "/students", "/settings"].includes(i.to)
                      ) &&
                      !(teacher.role === "TEACHER" && i.to === "/settings"),
                  ),
                }))),
            {
              label: "Account",
              items: [
                {
                  to: "/account",
                  label: "Account settings",
                  icon: IconSettings,
                } as NavItem,
              ],
            },
            ...(teacher.role === "MANAGEMENT"
              ? [
                  {
                    label: "School",
                    items: [
                      {
                        to: "/management",
                        label: "School management",
                        icon: IconSettings,
                      } as NavItem,
                      {
                        to: "/settings",
                        label: "Branding & reports",
                        icon: IconSettings,
                      } as NavItem,
                    ],
                  },
                ]
              : []),
            ...(teacher.role === "PARENT"
              ? [
                  {
                    label: "Family",
                    items: [
                      {
                        to: "/family",
                        label: "My child & profile",
                        icon: IconSettings,
                      } as NavItem,
                    ],
                  },
                ]
              : []),
            ...(teacher.is_admin
              ? [
                  {
                    label: "Platform",
                    items: [
                      {
                        to: "/admin",
                        label: "Administration",
                        icon: IconSettings,
                      } as NavItem,
                    ],
                  },
                ]
              : []),
          ].map((group) => (
            <div key={group.label}>
              <p className="flex items-center gap-2 px-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-cover-ink/45">
                {group.label}
                <span aria-hidden className="h-px flex-1 bg-cover-line/10" />
              </p>
              <nav className="mt-2 space-y-1" aria-label={group.label}>
                {group.items.map(
                  ({ to, label: itemLabel, icon: Icon, badge }) => (
                    <NavLink
                      key={to}
                      to={to}
                      className={({ isActive }) =>
                        `relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-ui ${
                          isActive
                            ? "bg-cover-line/[0.09] text-cover-brown before:absolute before:-left-1 before:top-1.5 before:bottom-1.5 before:w-[3px] before:rounded-full before:bg-mark"
                            : "text-cover-ink/70 hover:bg-cover-line/[0.05] hover:text-cover-brown"
                        }`
                      }
                    >
                      <Icon size={18} className="shrink-0 opacity-80" />
                      <span>{itemLabel}</span>
                      {badge && (
                        <CountBadge count={badges[badge]} className="ml-auto" />
                      )}
                    </NavLink>
                  ),
                )}
              </nav>
            </div>
          ))}
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex h-full overflow-hidden bg-paper">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-[70] focus:rounded-md focus:bg-pen focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-on-pen focus:shadow-pop"
      >
        Skip to content
      </a>
      {/* Desktop sidebar: the notebook cover, with binding holes on its spine */}
      <aside className="relative hidden w-64 shrink-0 bg-cover text-cover-ink lg:flex lg:flex-col">
        <span
          aria-hidden
          className="pointer-events-none absolute inset-y-0 right-0 w-3 bg-[radial-gradient(circle,rgb(var(--paper))_2.5px,transparent_3px)] bg-[length:12px_26px] bg-center bg-repeat-y opacity-90"
        />
        {navContent}
      </aside>

      {/* Mobile drawer backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 animate-fadeIn bg-cover/55 backdrop-blur-[3px] lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Mobile drawer panel (hidden from Tab and screen readers while closed) */}
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label="Navigation"
        aria-hidden={!sidebarOpen}
        {...(!sidebarOpen && { inert: "" })}
        className={`fixed inset-y-0 left-0 z-50 w-72 transform bg-cover text-cover-ink shadow-pop transition-[transform,visibility] duration-300 ease-in-out lg:hidden ${
          sidebarOpen ? "visible translate-x-0" : "invisible -translate-x-full"
        }`}
      >
        <div className="absolute right-3 top-3">
          <button
            onClick={() => setSidebarOpen(false)}
            aria-label="Close navigation"
            className="rounded-md p-2 text-cover-ink/70 hover:bg-cover-line/10 hover:text-cover-brown"
          >
            <IconX size={20} />
          </button>
        </div>
        {navContent}
      </div>

      {/* Main content area */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Top Header Bar */}
        <header className="relative z-40 flex h-14 shrink-0 items-center justify-between gap-3 border-b border-line bg-surface/80 px-4 backdrop-blur sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              aria-label="Open navigation menu"
              className="rounded-md p-1.5 text-mute hover:bg-hover hover:text-brown lg:hidden"
            >
              <IconMenu size={20} />
            </button>

            {/* Phones: just the current page */}
            <p className="truncate font-display text-base font-semibold text-ink sm:hidden">
              {pageName}
            </p>

            {/* Breadcrumb path: every level but the current page links back up */}
            <nav
              aria-label="Breadcrumbs"
              className="hidden min-w-0 sm:flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.12em] text-mute"
            >
              <Link
                to={teacher.is_admin ? "/admin" : "/dashboard"}
                className="shrink-0 font-display text-sm normal-case tracking-normal text-ink/70 transition-ui hover:text-brown"
              >
                Eval AI
              </Link>
              {pathSegments.map((seg, i) => {
                const last = i === pathSegments.length - 1;
                const to = "/" + pathSegments.slice(0, i + 1).join("/");
                // Names stay in their own case; route words keep the small-caps label style
                const named = !!crumbNames[seg];
                const cls = `truncate ${named ? "max-w-[16rem] normal-case tracking-normal text-xs" : ""}`;
                return (
                  <span key={to} className="flex min-w-0 items-center gap-2">
                    <IconChevronRight
                      size={12}
                      className="shrink-0 text-mark/60"
                    />
                    {last ? (
                      <span
                        aria-current="page"
                        className={`${cls} font-semibold text-ink`}
                      >
                        {crumbLabel(seg)}
                      </span>
                    ) : (
                      <Link
                        to={to}
                        className={`${cls} transition-ui hover:text-brown`}
                      >
                        {crumbLabel(seg)}
                      </Link>
                    )}
                  </span>
                );
              })}
            </nav>
          </div>
          <div className="flex shrink-0 items-center gap-2 sm:gap-3">
            {!teacher.is_admin && (
              <Link
                to="/exams/new"
                className="hidden items-center gap-1.5 rounded-md bg-pen px-3 py-1.5 text-sm font-medium text-on-pen transition-ui hover:opacity-90 lg:flex"
              >
                <IconPlus size={16} />
                New Exam
              </Link>
            )}
            {aiStatus && !aiStatus.available && (
              <AiStatusPill status={aiStatus} />
            )}
            <ProfileBookmark
              name={teacher.name || "Teacher"}
              email={teacher.email}
              onLogout={logout}
            />
          </div>
        </header>

        {/* Scrollable Page Body */}
        <main
          id="main"
          tabIndex={-1}
          className="desk min-w-0 flex-1 overflow-y-auto pb-20 outline-none lg:pb-0"
        >
          {/* Keyed on the section (e.g. one exam), not the full path, so switching tabs inside it keeps the page */}
          <div
            key={pathSegments.slice(0, 2).join("/")}
            className="mx-auto max-w-7xl animate-rise p-4 sm:p-6 lg:p-8"
          >
            <Outlet />
          </div>
        </main>
      </div>

      {/* Phone: upload answer sheets from any exam page */}
      {examId && !onUploadPage && (
        <Link
          to={`/exams/${examId}/submissions`}
          className="fixed bottom-20 right-4 z-30 flex items-center gap-2 rounded-full bg-pen px-4 py-3 text-sm font-semibold text-on-pen shadow-pop transition-ui hover:opacity-90 lg:hidden"
        >
          <IconUpload size={18} />
          Upload sheets
        </Link>
      )}

      {/* Phone tab bar */}
      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
      >
        {(teacher.is_admin
          ? [
              {
                to: "/admin",
                label: "Administration",
                icon: IconSettings,
              } as NavItem,
              {
                to: "/account",
                label: "Account",
                icon: IconSettings,
              } as NavItem,
            ]
          : TAB_BAR
        ).map(({ to, label, icon: Icon, badge }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `relative flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-medium transition-ui ${
                isActive ? "text-pen" : "text-mute hover:text-brown"
              }`
            }
          >
            <Icon size={20} />
            {label}
            {badge && (
              <CountBadge
                count={badges[badge]}
                className="absolute left-1/2 top-1 ml-1.5"
              />
            )}
          </NavLink>
        ))}
        <button
          onClick={() => setSidebarOpen(true)}
          className="flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-medium text-mute transition-ui hover:text-brown"
        >
          <IconMenu size={20} />
          More
        </button>
      </nav>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        pages={
          teacher.is_admin
            ? [
                { to: "/admin", label: "Administration", icon: IconSettings },
                {
                  to: "/account",
                  label: "Account settings",
                  icon: IconSettings,
                },
              ]
            : [
                ...ALL_PAGES.filter(
                  (p) =>
                    (teacher.role !== "PARENT" ||
                      !["/classes", "/students", "/settings"].includes(p.to)) &&
                    (teacher.role !== "TEACHER" || p.to !== "/settings"),
                ),
                {
                  to:
                    teacher.role === "MANAGEMENT"
                      ? "/management"
                      : teacher.role === "PARENT"
                        ? "/family"
                        : "/account",
                  label:
                    teacher.role === "MANAGEMENT"
                      ? "School management"
                      : teacher.role === "PARENT"
                        ? "Family profile"
                        : "Account settings",
                  icon: IconSettings,
                },
              ]
        }
      />
    </div>
  );
}
