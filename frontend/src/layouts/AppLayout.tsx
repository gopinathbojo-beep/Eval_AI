import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../context/Auth";
import { useApi } from "../hooks/useApi";
import { Loading } from "../components/ui";
import { BrandLabel } from "../components/Brand";
import {
  IconDashboard,
  IconExam,
  IconEvaluation,
  IconResults,
  IconClasses,
  IconStudents,
  IconSubjects,
  IconSettings,
  IconSun,
  IconMoon,
  IconLogOut,
  IconMenu,
  IconX,
  IconChevronRight,
  IconAlertTriangle,
} from "../components/Icons";

interface NavGroup {
  label: string;
  items: { to: string; label: string; icon: React.ComponentType<{ size?: number; className?: string }> }[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Main",
    items: [
      { to: "/dashboard", label: "Dashboard", icon: IconDashboard },
      { to: "/exams", label: "Exams", icon: IconExam },
      { to: "/evaluations", label: "Evaluations", icon: IconEvaluation },
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
  {
    label: "Preferences",
    items: [
      { to: "/settings", label: "Settings", icon: IconSettings },
    ],
  },
];

/** Profile as a ribbon bookmark hanging from the top-right of the header; opens an account card. */
function ProfileBookmark({
  name,
  email,
  dark,
  onToggleDark,
  onLogout,
}: {
  name: string;
  email: string;
  dark: boolean;
  onToggleDark: () => void;
  onLogout: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("") || "T";

  return (
    <div ref={ref} className="relative h-14 w-12 shrink-0 self-start">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account: ${name}`}
        title={name}
        className={`absolute left-0 top-0 flex h-[74px] w-12 flex-col items-center justify-start bg-mark pt-3 text-[#fff7e6] drop-shadow-[0_3px_3px_rgb(var(--ink)/0.25)] transition-transform duration-200 ease-out [clip-path:polygon(0_0,100%_0,100%_100%,50%_80%,0_100%)] hover:translate-y-1.5 ${
          open ? "translate-y-1.5" : ""
        }`}
      >
        {/* stitched edge */}
        <span aria-hidden className="pointer-events-none absolute inset-x-1 top-0 bottom-3 border-x border-dashed border-[#fff7e6]/45" />
        <span className="font-display text-base font-semibold leading-none">{initials}</span>
        <span aria-hidden className="mt-2 h-px w-5 bg-[#fff7e6]/50" />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-[84px] z-50 w-64 animate-rise overflow-hidden rounded-lg border border-line border-t-4 border-t-mark bg-surface shadow-pop"
        >
          <div className="border-b border-dashed border-line px-4 py-3">
            <p className="truncate font-display text-base font-semibold text-ink">{name}</p>
            <p className="truncate text-xs text-mute">{email}</p>
          </div>
          <div className="p-1.5">
            <button
              role="menuitem"
              onClick={onToggleDark}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm text-ink transition-ui hover:bg-hover hover:text-brown"
            >
              {dark ? <IconSun size={16} className="text-warn" /> : <IconMoon size={16} className="text-mute" />}
              {dark ? "Light mode" : "Dark mode"}
            </button>
            <Link
              role="menuitem"
              to="/settings"
              onClick={() => setOpen(false)}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-ink transition-ui hover:bg-hover hover:text-brown"
            >
              <IconSettings size={16} className="text-mute" />
              Settings
            </Link>
            <button
              role="menuitem"
              onClick={onLogout}
              className="flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm text-mark transition-ui hover:bg-mark-soft"
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

export function AppLayout() {
  const { teacher, loading, logout } = useAuth();
  const loc = useLocation();
  const [dark, setDark] = useState(() => localStorage.getItem("adem_theme") === "dark");
  const [sidebarOpen, setSidebarOpen] = useState(false); // Mobile drawer state
  const { data: aiStatus } = useApi<{
    available: boolean;
    model: string;
    url: string;
    message: string;
    detail?: string;
  }>("/system/ai-status");
  const [aiBannerDismissed, setAiBannerDismissed] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("adem_theme", dark ? "dark" : "light");
  }, [dark]);

  // Close mobile sidebar on route change
  useEffect(() => {
    setSidebarOpen(false);
  }, [loc.pathname]);

  if (loading) return <Loading text="Authenticating..." />;
  if (!teacher) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;

  // Generate breadcrumbs from route path
  const pathSegments = loc.pathname.split("/").filter(Boolean);
  const breadcrumbMap: Record<string, string> = {
    dashboard: "Dashboard",
    classes: "Classes",
    students: "Students",
    subjects: "Subjects",
    exams: "Exams",
    new: "Create Exam",
    evaluations: "Evaluations",
    results: "Results",
    settings: "Settings",
    "question-paper": "Question Paper",
    questions: "Questions",
    "answer-key": "Answer Key",
    "answer-sheets": "Answer Sheets",
    evaluation: "Assessment",
  };

  const navContent = (
    <div className="flex h-full flex-col justify-between">
      {/* Brand & Navigation */}
      <div className="flex-1 overflow-y-auto px-4 py-5">
        <Link to="/dashboard" className="mb-7 block px-1" aria-label="Eval AI dashboard">
          <BrandLabel />
          <p className="mt-2.5 pl-1 font-doc text-xs italic text-cover-ink/60">the examiner&rsquo;s desk</p>
        </Link>

        <div className="space-y-6">
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              <p className="flex items-center gap-2 px-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-cover-ink/45">
                {group.label}
                <span aria-hidden className="h-px flex-1 bg-cover-line/10" />
              </p>
              <nav className="mt-2 space-y-1" aria-label={group.label}>
                {group.items.map(({ to, label: itemLabel, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    className={({ isActive }) =>
                      `relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-ui ${isActive
                        ? "bg-cover-line/[0.09] text-cover-brown before:absolute before:-left-1 before:top-1.5 before:bottom-1.5 before:w-[3px] before:rounded-full before:bg-mark"
                        : "text-cover-ink/70 hover:bg-cover-line/[0.05] hover:text-cover-brown"
                      }`
                    }
                  >
                    <Icon size={18} className="shrink-0 opacity-80" />
                    <span>{itemLabel}</span>
                  </NavLink>
                ))}
              </nav>
            </div>
          ))}
        </div>
      </div>

    </div>
  );

  return (
    <div className="flex h-full overflow-hidden bg-paper">
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

      {/* Mobile drawer panel */}
      <div
        className={`fixed inset-y-0 left-0 z-50 w-72 transform bg-cover text-cover-ink shadow-pop transition-transform duration-300 ease-in-out lg:hidden ${sidebarOpen ? "translate-x-0" : "-translate-x-full"
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
        <header className="relative z-40 flex h-14 shrink-0 items-center justify-between border-b border-line bg-surface/80 px-4 backdrop-blur sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              aria-label="Open navigation menu"
              className="rounded-md p-1.5 text-mute hover:bg-hover hover:text-brown lg:hidden"
            >
              <IconMenu size={20} />
            </button>

            {/* Breadcrumb path */}
            <div className="hidden sm:flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.12em] text-mute">
              <span className="font-display text-sm normal-case tracking-normal text-ink/70">Eval AI</span>
              {pathSegments.map((seg, i) => {
                const labelText = breadcrumbMap[seg] || (seg.length > 15 ? seg.slice(0, 8) + "..." : seg);
                return (
                  <span key={i} className="flex items-center gap-2">
                    <IconChevronRight size={12} className="text-mark/60" />
                    <span className={i === pathSegments.length - 1 ? "font-semibold text-ink" : ""}>
                      {labelText}
                    </span>
                  </span>
                );
              })}
            </div>
          </div>
          <div className="flex items-center gap-4">
            <p className="hidden font-doc text-sm italic text-mute md:block" title="Today">
              {new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}
            </p>
            <ProfileBookmark
              name={teacher.name || "Teacher"}
              email={teacher.email}
              dark={dark}
              onToggleDark={() => setDark(!dark)}
              onLogout={logout}
            />
          </div>
        </header>

        {/* Offline AI Diagnostics Banner */}
        {aiStatus && !aiStatus.available && !aiBannerDismissed && (
          <div className="flex animate-fadeIn items-center justify-between gap-3 border-b border-warn/30 bg-warn-soft/70 px-4 py-2.5 text-xs text-ink sm:px-6 lg:px-8">
            <div className="flex items-center gap-2">
              <IconAlertTriangle size={16} className="shrink-0 text-warn" />
              <span>
                <strong>Offline AI Mode:</strong> {aiStatus.message || "Local AI model is currently offline."} Manual teacher grading, transcription review, and marksheet export remain active.
              </span>
              <Link to="/settings" className="ml-1 font-semibold text-warn underline underline-offset-2 hover:text-brown">
                AI Diagnostics
              </Link>
            </div>
            <button
              onClick={() => setAiBannerDismissed(true)}
              className="rounded p-1 text-warn transition-ui hover:bg-warn/15"
              title="Dismiss banner"
              aria-label="Dismiss banner"
            >
              <IconX size={14} />
            </button>
          </div>
        )}

        {/* Scrollable Page Body */}
        <main className="desk min-w-0 flex-1 overflow-y-auto">
          <div key={loc.pathname} className="mx-auto max-w-7xl animate-rise p-4 sm:p-6 lg:p-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
