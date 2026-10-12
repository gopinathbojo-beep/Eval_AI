import { useEffect, useState } from "react";
import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../context/Auth";
import { Loading } from "../components/ui";

const NAV = [
  ["/dashboard", "Dashboard"], ["/classes", "Classes"], ["/students", "Students"], ["/subjects", "Subjects"], ["/exams", "Exams"],
  ["/evaluations", "Evaluations"], ["/results", "Results"], ["/settings", "Settings"],
];

export function AppLayout() {
  const { teacher, loading, logout } = useAuth();
  const loc = useLocation();
  const [dark, setDark] = useState(() => localStorage.getItem("adem_theme") === "dark");
  useEffect(() => { document.documentElement.classList.toggle("dark", dark); localStorage.setItem("adem_theme", dark ? "dark" : "light"); }, [dark]);
  if (loading) return <Loading />;
  if (!teacher) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  return (
    <div className="flex h-full">
      <aside className="flex w-56 shrink-0 flex-col border-r border-line bg-surface">
        <div className="px-5 py-5">
          <p className="text-lg font-semibold tracking-tight text-pen">ADEM</p>
          <p className="text-xs text-mute">Exam evaluation</p>
        </div>
        <nav className="flex-1 space-y-0.5 px-2" aria-label="Main">
          {NAV.map(([to, text]) => (
            <NavLink key={to} to={to}
              className={({ isActive }) => `block rounded-md px-3 py-2 text-sm ${isActive ? "bg-pen-soft font-medium text-pen" : "text-ink hover:bg-sunken"}`}>{text}</NavLink>
          ))}
        </nav>
        <div className="space-y-2 border-t border-line p-3 text-sm">
          <p className="truncate font-medium">{teacher.name}</p>
          <p className="truncate text-xs text-mute">{teacher.email}</p>
          <div className="flex gap-2">
            <button onClick={() => setDark(!dark)} className="rounded-md bg-sunken px-2.5 py-1 text-xs hover:bg-line">{dark ? "Light mode" : "Dark mode"}</button>
            <button onClick={logout} className="rounded-md bg-sunken px-2.5 py-1 text-xs hover:bg-line">Sign out</button>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto"><div className="mx-auto max-w-7xl p-6"><Outlet /></div></main>
    </div>
  );
}
