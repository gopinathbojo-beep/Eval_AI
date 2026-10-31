import { useState, type ReactNode } from "react";
import { Navigate, NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../context/Auth";
import { BrandLabel } from "../components/Brand";
import { ThemeToggle } from "../components/ThemeToggle";
import { IconLogOut, IconMenu, IconX } from "../components/Icons";
import { Loading } from "../components/ui";

export interface NavItem { to: string; label: string; icon: ReactNode }

/** Signed-in frame: sidebar on wide screens, slide-in menu on phones. Sends signed-out users to /login and users
 * with a password someone else chose to /change-password. */
export function Layout({ nav, roleLabel }: { nav: NavItem[]; roleLabel: string }) {
  const { user, loading, logout } = useAuth();
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  if (loading) return <Loading text="Signing you in..." />;
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  if (user.must_change_password) return <Navigate to="/change-password" replace />;

  const sidebar = (
    <nav className="flex h-full flex-col bg-cover px-4 py-6 text-cover-ink">
      <div className="px-2"><BrandLabel /></div>
      <ul className="mt-8 flex-1 space-y-1 overflow-y-auto">
        {nav.map((n) => (
          <li key={n.to}>
            <NavLink to={n.to} end={n.to === "/"} onClick={() => setOpen(false)}
              className={({ isActive }) => `flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-ui ${
                isActive ? "bg-white/10 font-semibold text-white" : "text-cover-ink/80 hover:bg-white/5 hover:text-cover-brown"}`}>
              <span className="shrink-0">{n.icon}</span>{n.label}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="mt-4 border-t border-cover-line/15 px-2 pt-4 text-sm">
        <p className="truncate font-semibold text-white">{user.name}</p>
        <p className="truncate text-xs text-cover-ink/60">{roleLabel}</p>
        <div className="mt-3 flex items-center justify-between">
          <ThemeToggle />
          <button onClick={logout} className="flex items-center gap-1.5 text-xs text-cover-ink/80 hover:text-cover-brown">
            <IconLogOut size={15} />Sign out
          </button>
        </div>
      </div>
    </nav>
  );

  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 lg:block">{sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-ink/40" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 animate-rise">{sidebar}</aside>
        </div>
      )}
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-paper/95 px-4 py-3 backdrop-blur lg:hidden">
          <button aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen(!open)} className="text-ink">
            {open ? <IconX size={22} /> : <IconMenu size={22} />}
          </button>
          <BrandLabel onDark={false} />
        </header>
        <main className="desk mx-auto max-w-6xl px-4 py-6 sm:px-8 sm:py-8"><Outlet /></main>
      </div>
    </div>
  );
}
