import { useEffect, useState } from "react";
import { Link, NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../context/Auth";
import { useApi } from "../hooks/useApi";
import { Loading } from "../components/ui";
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
  IconSparkles,
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
        <Link to="/dashboard" className="mb-6 flex items-center gap-3 px-2 group">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-pen text-white shadow-md transition-ui group-hover:scale-105">
            <IconSparkles size={20} />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-lg font-bold tracking-tight text-ink">Eval AI</span>
              <span className="rounded bg-pen/10 px-1.5 py-0.2 text-[10px] font-semibold text-pen uppercase tracking-wide">
                Pro
              </span>
            </div>
            <p className="text-xs font-medium text-mute">Academic Assessment</p>
          </div>
        </Link>

        <div className="space-y-6">
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              <p className="px-3 text-[11px] font-bold uppercase tracking-wider text-mute/80">
                {group.label}
              </p>
              <nav className="mt-2 space-y-1" aria-label={group.label}>
                {group.items.map(({ to, label: itemLabel, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    className={({ isActive }) =>
                      `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-ui ${isActive
                        ? "bg-pen-soft text-pen shadow-sm"
                        : "text-ink/80 hover:bg-sunken hover:text-ink"
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

      {/* User profile & actions */}
      <div className="border-t border-line bg-sunken/40 p-4">
        <div className="mb-3 flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-pen/15 font-semibold text-pen text-sm">
            {teacher.name ? teacher.name.charAt(0).toUpperCase() : "T"}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-semibold text-ink">{teacher.name}</p>
            <p className="truncate text-[11px] text-mute">{teacher.email}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setDark(!dark)}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs font-medium text-ink transition-ui hover:bg-sunken"
            title={dark ? "Switch to light mode" : "Switch to dark mode"}
          >
            {dark ? <IconSun size={14} className="text-amber-500" /> : <IconMoon size={14} />}
            <span>{dark ? "Light" : "Dark"}</span>
          </button>
          <button
            onClick={logout}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs font-medium text-ink transition-ui hover:bg-mark-soft hover:text-mark hover:border-mark/30"
            title="Sign out of your account"
          >
            <IconLogOut size={14} />
            <span>Sign out</span>
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex h-full overflow-hidden bg-paper">
      {/* Desktop sidebar */}
      <aside className="hidden w-64 shrink-0 border-r border-line bg-surface lg:flex lg:flex-col shadow-sm">
        {navContent}
      </aside>

      {/* Mobile drawer backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-slate-900/50 backdrop-blur-sm lg:hidden transition-opacity"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Mobile drawer panel */}
      <div
        className={`fixed inset-y-0 left-0 z-50 w-72 transform bg-surface shadow-2xl transition-transform duration-300 ease-in-out lg:hidden ${sidebarOpen ? "translate-x-0" : "-translate-x-full"
          }`}
      >
        <div className="absolute right-3 top-3">
          <button
            onClick={() => setSidebarOpen(false)}
            aria-label="Close navigation"
            className="rounded-lg p-2 text-mute hover:bg-sunken hover:text-ink"
          >
            <IconX size={20} />
          </button>
        </div>
        {navContent}
      </div>

      {/* Main content area */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Top Header Bar */}
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-surface px-4 sm:px-6 shadow-sm">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(true)}
              aria-label="Open navigation menu"
              className="rounded-lg p-1.5 text-mute hover:bg-sunken hover:text-ink lg:hidden"
            >
              <IconMenu size={20} />
            </button>

            {/* Breadcrumb path */}
            <div className="hidden sm:flex items-center gap-2 text-xs font-medium text-mute">
              <span>Eval AI</span>
              {pathSegments.map((seg, i) => {
                const labelText = breadcrumbMap[seg] || (seg.length > 15 ? seg.slice(0, 8) + "..." : seg);
                return (
                  <span key={i} className="flex items-center gap-2">
                    <IconChevronRight size={12} className="opacity-40" />
                    <span className={i === pathSegments.length - 1 ? "font-semibold text-ink" : ""}>
                      {labelText}
                    </span>
                  </span>
                );
              })}
            </div>
          </div>
        </header>

        {/* Offline AI Diagnostics Banner */}
        {aiStatus && !aiStatus.available && !aiBannerDismissed && (
          <div className="bg-amber-500/10 border-b border-amber-500/30 px-4 py-2.5 text-xs text-amber-800 dark:text-amber-200 flex items-center justify-between gap-3 animate-fadeIn">
            <div className="flex items-center gap-2">
              <IconAlertTriangle size={16} className="text-amber-600 dark:text-amber-400 shrink-0" />
              <span>
                <strong>Offline AI Mode:</strong> {aiStatus.message || "Local AI model is currently offline."} Manual teacher grading, OCR review, and marksheet export remain active.
              </span>
              <Link to="/settings" className="underline font-semibold ml-1 hover:text-amber-900 dark:hover:text-amber-100">
                AI Diagnostics
              </Link>
            </div>
            <button
              onClick={() => setAiBannerDismissed(true)}
              className="rounded p-1 hover:bg-amber-500/20 text-amber-700 dark:text-amber-300 transition-ui"
              title="Dismiss banner"
              aria-label="Dismiss banner"
            >
              <IconX size={14} />
            </button>
          </div>
        )}

        {/* Scrollable Page Body */}
        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-7xl p-4 sm:p-6 lg:p-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
