import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { Link, NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../context/Auth";
import { CrumbProvider, useCrumbNames } from "../context/Crumbs";
import { useApi } from "../hooks/useApi";
import type { Dashboard } from "../types";
import { SidebarBrand } from "../components/Brand";
import { ThemeToggle } from "../components/ThemeToggle";
import { CommandPalette } from "../components/CommandPalette";
import catImg from "../assets/sidebar-cat.png";
import {
  IconDashboard,
  IconExam,
  IconResults,
  IconClasses,
  IconStudents,
  IconSubjects,
  IconSettings,
  IconFileText,
  IconLogOut,
  IconMenu,
  IconX,
  IconChevronRight,
  IconUpload,
  IconBell,
  IconAlertTriangle,
  IconCheckCircle,
} from "../components/Icons";

type IconType = React.ComponentType<{ size?: number; className?: string }>;
type BadgeKey = "pending";

interface NavItem {
  to: string;
  label: string;
  icon: IconType;
  badge?: BadgeKey;
}

/** School Management: 5 main items matching modern layout */
const SCHOOL_NAV: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: IconDashboard },
  { to: "/exams", label: "Exams", icon: IconExam, badge: "pending" },
  { to: "/qp-generation", label: "QP & Answer Key", icon: IconSubjects },
];

const PARENT_NAV: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: IconDashboard },
  { to: "/exams", label: "Exams", icon: IconExam, badge: "pending" },
  { to: "/results", label: "Results", icon: IconResults },
  { to: "/family", label: "My child & profile", icon: IconClasses },
];

const navFor = (role: string | undefined) => (role === "PARENT" ? PARENT_NAV : SCHOOL_NAV);

const pagesFor = (role: string | undefined) => [
  ...navFor(role),
  ...(role === "PARENT" ? [] : [{ to: "/settings", label: "Branding & reports", icon: IconSettings }]),
];

const BREADCRUMBS: Record<string, string> = {
  dashboard: "Dashboard",
  classes: "Classes",
  subjects: "Subjects",
  exams: "Exams",
  new: "Create Exam",
  evaluations: "Evaluations",
  results: "Results",
  settings: "Branding & reports",
  "qp-generation": "QP & Answer Key",
  codes: "Uploader Codes",
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

/** Modern user profile pill button matching the mockup */
function ProfileBookmark({
  name,
  email,
  role = "Teacher",
  onLogout,
}: {
  name: string;
  email: string;
  role?: string;
  onLogout: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useOutsideClick(ref, open, () => setOpen(false));

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
      e.stopPropagation();
      setOpen(false);
      buttonRef.current?.focus();
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  };


  return (
    <div ref={ref} className="relative">
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
        className="group flex items-center gap-3 rounded-full py-1 pl-1 pr-2 transition-all hover:bg-white/60 cursor-pointer"
      >
        <div className="sky-avatar flex h-11 w-11 items-center justify-center rounded-full transition-transform group-hover:scale-105" aria-hidden>
          {/* Sun in light mode, crescent moon in dark mode (CSS shows one) */}
          <svg className="sky-sun" width="26" height="26" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="4.6" fill="#fbbf24" />
            <g stroke="#f59e0b" strokeWidth="1.8" strokeLinecap="round">
              <path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6" />
            </g>
          </svg>
          <svg className="sky-moon" width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M15.5 3.5a8.5 8.5 0 1 0 5 15.3A7 7 0 0 1 15.5 3.5Z" fill="#fde68a" />
            <path d="M19 5.5l.5 1 1 .5-1 .5-.5 1-.5-1-1-.5 1-.5z M21.5 10l.3.6.6.3-.6.3-.3.6-.3-.6-.6-.3.6-.3z" fill="#e0f2fe" />
          </svg>
        </div>
        <div className="hidden sm:flex flex-col text-left leading-tight">
          <span className="text-sm font-bold text-blue-950">{name}</span>
          <span className="text-xs font-semibold text-blue-900/70 capitalize">{role.toLowerCase()}</span>
        </div>
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`ml-0.5 text-blue-900 transition-transform ${open ? "rotate-180" : ""}`}
        >
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </button>

      {open && (
        <div
          ref={menuRef}
          role="menu"
          aria-label="Account"
          onKeyDown={onMenuKeyDown}
          className="popover-panel absolute right-0 top-14 z-50 w-64 animate-rise overflow-hidden rounded-2xl border border-slate-200 bg-white p-2 shadow-xl shadow-slate-900/10"
        >
          <div className="border-b border-slate-100 px-4 py-3">
            <p className="truncate text-sm font-bold text-slate-900">{name}</p>
            <p className="truncate text-xs font-medium text-slate-400 mt-0.5">{email}</p>
            <span className="inline-block mt-1.5 rounded-full bg-blue-50 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-blue-700">
              {role}
            </span>
          </div>
          <div className="pt-1.5 space-y-0.5">
            <ThemeToggle menuItem />
            
            <button
              role="menuitem"
              onClick={onLogout}
              className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-sm font-medium text-red-600 transition-colors hover:bg-red-50 cursor-pointer"
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

interface Notice {
  kind: string;
  exam: string;
  title: string;
  detail: string;
  link: string;
  at: string | null;
}

/** Icon and tint per notification kind (see backend routes/notifications.py). */
const NOTICE_KIND: Record<string, { icon: IconType; cls: string }> = {
  sheet_held: { icon: IconStudents, cls: "bg-amber-50 text-amber-600" },
  sheet_unread: { icon: IconAlertTriangle, cls: "bg-rose-50 text-rose-600" },
  document_unread: { icon: IconFileText, cls: "bg-rose-50 text-rose-600" },
  evaluation_review: { icon: IconCheckCircle, cls: "bg-blue-50 text-blue-600" },
  default: { icon: IconBell, cls: "bg-slate-100 text-slate-600" },
};

/** "5m ago", "3h ago", "2d ago"; older than a week shows the date. */
function ago(iso: string) {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60_000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 1440) return `${Math.round(mins / 60)}h ago`;
  if (mins < 10080) return `${Math.round(mins / 1440)}d ago`;
  return new Date(iso).toLocaleDateString([], { day: "numeric", month: "short" });
}

/** Notifications bell with unread count pill badge */
function NotificationsBell() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useOutsideClick(ref, open, () => setOpen(false));
  const { data } = useApi<{ count: number; items: Notice[] }>("/notifications", () => POLL_MS);
  const count = data?.count ?? 0;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={count ? `${count} notifications` : "Notifications"}
        className="relative hover-star flex h-11 w-11 items-center justify-center rounded-full border border-white bg-white/90 text-blue-800 shadow-[0_8px_20px_-10px_rgba(30,64,175,0.45)] hover:-translate-y-0.5 hover:bg-white transition-all cursor-pointer"
      >
        {/* Star instead of a bell: it twinkles while something is waiting */}
        <svg aria-hidden width="22" height="22" viewBox="0 0 24 24" className={`star-icon ${count > 0 ? "has-news" : ""}`}>
          <path
            d="M12 2.8l2.6 5.6 6.1.7-4.5 4.2 1.2 6-5.4-3.1-5.4 3.1 1.2-6-4.5-4.2 6.1-.7z"
            fill="url(#starFill)"
            stroke="#0e7490"
            strokeWidth="1.2"
            strokeLinejoin="round"
          />
          <defs>
            <linearGradient id="starFill" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#fde68a" />
              <stop offset="1" stopColor="#5eead4" />
            </linearGradient>
          </defs>
        </svg>
        {count > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex h-[1.15rem] min-w-[1.15rem] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white ring-2 ring-white shadow-xs animate-[fadeIn_.3s_ease-out]">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </button>

      {open && (
        <div className="popover-panel absolute right-0 top-14 z-50 w-80 max-w-[calc(100vw-2rem)] animate-rise overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl shadow-slate-900/10">
          <p className="border-b border-slate-100 px-4 py-3 text-sm font-bold text-slate-900">
            Notifications{count > 0 && <span className="ml-1.5 font-semibold text-slate-400">{count}</span>}
          </p>
          {!data?.items.length ? (
            <p className="px-4 py-8 text-center text-sm text-slate-500">You're all caught up.</p>
          ) : (
            <ul className="max-h-[60vh] overflow-y-auto py-1">
              {data.items.map((n, i) => {
                const k = NOTICE_KIND[n.kind] ?? NOTICE_KIND.default!;
                return (
                  <li key={`${n.link}-${i}`}>
                    <Link
                      to={n.link}
                      title={n.detail}
                      onClick={() => setOpen(false)}
                      className="flex items-start gap-3 px-4 py-2.5 transition-colors hover:bg-slate-50"
                    >
                      <span className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${k.cls}`}>
                        <k.icon size={14} />
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium text-slate-800">{n.title}</span>
                        <span className="block truncate text-xs text-slate-500">
                          {n.exam}
                          {n.at ? ` · ${ago(n.at)}` : ""}
                        </span>
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

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
        className="flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700 hover:bg-amber-100 transition-colors"
      >
        <span aria-hidden className="h-2 w-2 animate-pulse rounded-full bg-amber-500" />
        <span className="hidden sm:inline">AI offline</span>
        <span className="sm:hidden">AI</span>
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="AI status"
          className="popover-panel absolute right-0 top-11 z-50 w-72 animate-rise rounded-2xl border border-slate-200 bg-white p-4 text-xs text-slate-700 shadow-xl"
        >
          <p className="text-sm font-bold text-slate-900">Offline AI mode</p>
          <p className="mt-1.5 text-slate-500">
            {status.message || "The local AI model is currently offline."}
          </p>
          <p className="mt-1.5 text-slate-500">
            Manual grading, transcription review and marksheet export still work.
          </p>
          {status.detail && (
            <p className="mt-2 rounded-lg bg-slate-100 px-2 py-1.5 font-mono text-[11px] text-slate-600">
              {status.detail}
            </p>
          )}
          <Link
            to="/settings"
            onClick={() => setOpen(false)}
            className="mt-3 inline-block font-semibold text-amber-600 underline underline-offset-2 hover:text-amber-700"
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
      className={`min-w-[1.25rem] rounded-full bg-red-500 px-1.5 text-center text-[10px] font-bold leading-5 text-white shadow-xs ${className}`}
      aria-label={`${count} pending`}
    >
      {count > 99 ? "99+" : count}
    </span>
  );
}

function ShellSkeleton() {
  return (
    <div className="app-shell app-bg flex h-full overflow-hidden" aria-busy="true" aria-label="Loading">
      <aside className="sidebar-surface relative hidden w-64 shrink-0 p-5 lg:block">
        <div className="mb-8 h-10 w-36 animate-pulse rounded-md bg-white/10" />
        {Array.from({ length: 7 }, (_, i) => (
          <div key={i} className="mb-3 h-8 animate-pulse rounded-md bg-white/5" />
        ))}
      </aside>
      <div className="flex flex-1 flex-col">
        <div className="h-[4.5rem]" />
        <div className="mx-auto w-full max-w-7xl space-y-4 p-4 sm:p-6 lg:p-8">
          <div className="h-28 animate-pulse rounded-3xl bg-white" />
          <div className="grid gap-4 sm:grid-cols-4">
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className="h-28 animate-pulse rounded-3xl bg-white" />
            ))}
          </div>
          <div className="h-64 animate-pulse rounded-3xl bg-white" />
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
  const { teacher, loading, logout } = useAuth();
  const loc = useLocation();
  const crumbNames = useCrumbNames();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const drawerRef = useRef<HTMLDivElement>(null);

  const workspaceReady =
    teacher?.profile_complete &&
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

  useEffect(() => {
    setSidebarOpen(false);
  }, [loc.pathname]);

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

  // Ctrl/⌘ K opens search
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

  const pathSegments = loc.pathname.split("/").filter(Boolean);
  const crumbLabel = (seg: string) =>
    crumbNames[seg] || BREADCRUMBS[seg] || (seg.length > 15 ? "Details" : seg);

  const pageName = pathSegments.length
    ? crumbLabel(pathSegments[pathSegments.length - 1]!)
    : "Dashboard";

  useEffect(() => {
    document.title = `${pageName} · Eval AI`;
  }, [pageName]);

  const examId =
    pathSegments[0] === "exams" && pathSegments[1] && pathSegments[1] !== "new"
      ? pathSegments[1]
      : null;

  const onUploadPage = pathSegments[2] === "upload";

  if (loading) return <ShellSkeleton />;
  if (!teacher)
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
    if (!teacher.is_admin && !teacher.profile_complete)
    return <Navigate to="/onboarding" replace />;
  if (teacher.is_admin && loc.pathname !== "/admin")
    return <Navigate to="/admin" replace />;

  /** Sleeping cat with floating zzz. `popOut` lets it extend past the sidebar's right edge. */
  const catArt = (popOut: boolean) => (
    <div className={popOut ? "cat-pop cat-pop-out" : "cat-pop"} aria-hidden>
      <div className="pointer-events-none absolute right-[34%] top-[24%] z-10 font-bold text-sky-200">
        <span className="absolute text-[12px] animate-zzz-1">z</span>
        <span className="absolute left-2 -top-2 text-[14px] animate-zzz-2">z</span>
        <span className="absolute left-4 -top-4 text-[17px] animate-zzz-3">Z</span>
      </div>
      {!popOut && <div className="cat-pop-frame" />}
      <div className="cat-pop-glow" />
      <img src={catImg} alt="" className="cat-pop-img" />
    </div>
  );

  const navContent = (inDrawer: boolean) => (
    <div className="flex h-full flex-col justify-between overflow-y-auto">
      {/* Brand & Navigation */}
      <div className="px-4 py-6">
        <Link
          to={teacher.is_admin ? "/admin" : "/dashboard"}
          className="mb-6 block"
          aria-label="Eval AI dashboard"
        >
          <SidebarBrand />
        </Link>

        <div className="space-y-6">
          {[
            ...(teacher.is_admin
              ? []
              : [{ label: "", items: navFor(teacher.role) }]),
            ...(teacher.is_admin || teacher.role === "PARENT"
              ? []
              : [
                  {
                    label: "Settings",
                    collapsible: true,
                    items: [
                      { to: "/settings", label: "Branding & reports", icon: IconFileText } as NavItem,
                    ],
                  },
                ]),
            ...(teacher.is_admin
              ? [
                  {
                    label: "Platform",
                    collapsible: false,
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
          ].map((group, idx) => (
            <div
              key={idx}
              className={`space-y-1.5 ${group.label ? "border-t border-white/15 pt-4" : ""}`}
            >
              <nav className="space-y-1 stagger" aria-label={group.label || "Navigation"}>
                {group.items.map(({ to, label: itemLabel, icon: Icon, badge }) => (
                  <NavLink
                    key={to}
                    to={to}
                    className={({ isActive }) =>
                      `nav-link relative flex items-center gap-3.5 rounded-2xl px-3.5 py-2.5 text-sm font-semibold transition-all duration-200 ${
                        isActive
                          ? "nav-active shine text-white"
                          : "text-blue-50 hover:bg-white/10 hover:text-white"
                      }`
                    }
                  >
                    {({ isActive }) => (
                      <>
                        {isActive ? (
                          <span className="flex h-[1.9rem] w-[1.9rem] shrink-0 items-center justify-center">
                            <Icon size={20} className="text-white drop-shadow" />
                          </span>
                        ) : (
                          <span className="nav-tile">
                            <Icon size={17} />
                          </span>
                        )}
                        <span className="relative z-10">{itemLabel}</span>
                        {badge && (
                          <CountBadge count={badges[badge]} className="ml-auto" />
                        )}
                        {isActive && (
                          <IconChevronRight size={16} className="relative z-10 ml-auto text-white/90" />
                        )}
                      </>
                    )}
                  </NavLink>
                ))}
              </nav>
            </div>
          ))}
        </div>
      </div>

      {/* Sidebar Footer Illustration */}
      <div className="px-4 pb-4 pt-2 select-none" aria-hidden>
        <div className="relative ml-4 inline-block -rotate-6">
          <p className="script-text text-lg leading-tight text-white drop-shadow">
            Dream Big,
            <br />
            <span className="pl-1">Learn More...</span>
          </p>
          <svg className="-mt-0.5 h-3 w-full text-amber-400" viewBox="0 0 100 10" preserveAspectRatio="none">
            <path
              d="M2 8 Q 50 1, 98 5"
              stroke="currentColor"
              strokeWidth="2.5"
              fill="none"
              strokeLinecap="round"
              strokeDasharray="120"
              className="animate-[draw_2.4s_ease-out_both]"
            />
          </svg>
        </div>
        {/* Room for the cat; on desktop it is drawn over the sidebar edge (see catArt) */}
        {inDrawer ? <div className="relative -mx-4 -mb-4 mt-1">{catArt(false)}</div> : <div className="h-[12.5rem]" />}
      </div>
    </div>
  );

  return (
    <div className="app-shell app-bg flex h-full overflow-hidden font-sans">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-[70] focus:rounded-md focus:bg-blue-600 focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-white"
      >
        Skip to content
      </a>

      {/* Desktop Sidebar */}
      <aside className="sidebar-surface relative z-30 hidden w-64 shrink-0 text-white lg:flex lg:flex-col">
        {navContent(false)}
        {catArt(true)}
      </aside>

      {/* Mobile drawer backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-[#0B1528]/60 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Mobile drawer panel */}
      <div
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label="Navigation"
        aria-hidden={!sidebarOpen}
        {...(!sidebarOpen && { inert: "" })}
        className={`sidebar-surface fixed inset-y-0 left-0 z-50 w-72 transform text-white shadow-2xl transition-[transform,visibility] duration-300 ease-in-out lg:hidden ${
          sidebarOpen ? "visible translate-x-0" : "invisible -translate-x-full"
        }`}
      >
        <div className="absolute right-3 top-3">
          <button
            onClick={() => setSidebarOpen(false)}
            aria-label="Close navigation"
            className="rounded-lg p-2 text-blue-200 hover:bg-white/10 hover:text-white"
          >
            <IconX size={20} />
          </button>
        </div>
        {navContent(true)}
      </div>

      {/* Main Content Area */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Top Header Bar */}
        <header className="relative z-40 mx-auto flex h-16 w-full max-w-[1680px] shrink-0 items-center justify-between gap-3 px-4 sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              aria-label="Open navigation menu"
              className="rounded-lg p-1.5 text-slate-600 hover:bg-slate-100 lg:hidden"
            >
              <IconMenu size={20} />
            </button>

          </div>

          <div className="flex shrink-0 items-center gap-2 sm:gap-3">
            {aiStatus && !aiStatus.available && (
              <AiStatusPill status={aiStatus} />
            )}
            {!teacher.is_admin && (
              <span className="mr-0.5 whitespace-nowrap rounded-full border border-line bg-surface/90 px-3 py-1.5 text-xs font-medium text-slate-600 shadow-sm backdrop-blur sm:text-sm">
                Credits: <span className="font-semibold text-emerald-600">{dash?.credits ?? "Unlimited"}</span>
              </span>
            )}
            {!teacher.is_admin && <NotificationsBell />}
            <ProfileBookmark
              name={teacher.name || "Teacher"}
              email={teacher.email}
              role={teacher.role || "Teacher"}
              onLogout={logout}
            />
          </div>
        </header>

        {/* Scrollable Page Body with sky-blue gradient background */}
        <main
          id="main"
          tabIndex={-1}
          className="min-w-0 flex-1 overflow-y-auto pb-20 outline-none lg:pb-0"
        >
          <div
            key={pathSegments.slice(0, 2).join("/")}
            className="mx-auto w-full max-w-[1680px] animate-rise px-4 pb-6 pt-1 sm:px-6 lg:px-8"
          >
            <Outlet />
          </div>
        </main>
      </div>

      {/* Phone: upload answer sheets from any exam page */}
      {examId && !onUploadPage && (
        <Link
          to={`/exams/${examId}/upload`}
          className="fixed bottom-20 right-4 z-30 flex items-center gap-2 rounded-full bg-blue-600 px-4 py-3 text-sm font-semibold text-white shadow-xl hover:bg-blue-700 transition-all lg:hidden"
        >
          <IconUpload size={18} />
          Upload sheets
        </Link>
      )}

      {/* Phone bottom tab bar */}
      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-30 flex border-t border-slate-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md lg:hidden"
      >
        {(teacher.is_admin
          ? [
              {
                to: "/admin",
                label: "Administration",
                icon: IconSettings,
              } as NavItem,
              ]
          : navFor(teacher.role)
        ).map(({ to, label, icon: Icon, badge }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `relative flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-medium transition-colors ${
                isActive ? "text-blue-600 font-semibold" : "text-slate-500 hover:text-slate-800"
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
          className="flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-medium text-slate-500 hover:text-slate-800 transition-colors"
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
                ]
            : pagesFor(teacher.role)
        }
      />
    </div>
  );
}
