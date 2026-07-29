import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { getToken } from "@/api/client";

const navItems = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/runs", label: "Run History", end: false },
];

export default function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-20 border-b border-surface-border bg-white/90 backdrop-blur">
        <div className="mx-auto max-w-7xl px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-2.5">
              <div className="h-8 w-8 rounded-lg bg-brand-500 text-white flex items-center justify-center font-bold text-sm">
                R
              </div>
              <div>
                <div className="text-sm font-bold leading-tight">Recon OS</div>
                <div className="text-[11px] text-ink-faint leading-tight">Eroute Technologies</div>
              </div>
            </div>
            <nav className="flex items-center gap-1">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                      isActive ? "bg-brand-50 text-brand-700" : "text-ink-muted hover:bg-surface-muted"
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right">
              <div className="text-sm font-medium leading-tight">{user?.name}</div>
              <div className="text-[11px] text-ink-faint leading-tight capitalize">{user?.role}</div>
            </div>
            {/* Only shown if a login token is actually in play (AUTH_REQUIRED=true
                server-side) - with auth optional (the default) there's nothing to sign out of. */}
            {getToken() && (
              <button onClick={logout} className="btn-ghost text-xs">
                Sign out
              </button>
            )}
          </div>
        </div>
      </header>
      <main className="flex-1 mx-auto w-full max-w-7xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
