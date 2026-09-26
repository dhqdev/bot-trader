import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Bot, FlaskConical, LayoutDashboard, LogOut, Moon, Power, Settings, Sparkles, Sun } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { duration } from "../lib/format";
import type { SystemInfo } from "../lib/types";
import { Confirm } from "./ui";

const NAV = [
  { to: "/", label: "Painel", icon: LayoutDashboard, end: true },
  { to: "/bots", label: "Bots", icon: Bot },
  { to: "/lab", label: "Laboratório", icon: FlaskConical },
  { to: "/ai", label: "Análise IA", icon: Sparkles },
  { to: "/settings", label: "Configurações", icon: Settings },
];

function useTheme(): [string, () => void] {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme ?? "dark");
  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("bt-theme", next);
    } catch {
      /* armazenamento bloqueado */
    }
    setTheme(next);
  };
  return [theme, toggle];
}

function EngineSwitch() {
  const qc = useQueryClient();
  const [confirmOff, setConfirmOff] = useState(false);
  const { data } = useQuery({
    queryKey: ["system"],
    queryFn: () => api.get<SystemInfo>("/system"),
    refetchInterval: 15_000,
  });
  const mutation = useMutation({
    mutationFn: (enabled: boolean) => api.post<SystemInfo>("/system/engine", { enabled }),
    onSuccess: (info) => {
      qc.setQueryData(["system"], info);
      qc.invalidateQueries({ queryKey: ["bots"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      setConfirmOff(false);
    },
  });
  if (!data) return null;
  const on = data.engine_enabled;
  return (
    <>
      <button
        onClick={() => (on ? setConfirmOff(true) : mutation.mutate(true))}
        className={clsx(
          "flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
          on ? "border-good/40 text-good-text hover:bg-surface-2" : "border-bad/40 text-bad-text hover:bg-surface-2",
        )}
        title={on ? "Clique para desligar o sistema" : "Clique para ligar o sistema"}
      >
        <Power className="size-3.5" />
        {on ? "Sistema ligado" : "Sistema desligado"}
        {on && (
          <span className="hidden text-muted sm:inline">
            · {data.running_bots}/{data.total_bots} bots · {duration(data.uptime_seconds)}
          </span>
        )}
      </button>
      <Confirm
        open={confirmOff}
        title="Desligar o sistema?"
        message={
          <>
            Todos os bots param de operar, inclusive o monitoramento de stop das posições abertas. As posições{" "}
            <strong>não</strong> são vendidas. Ao religar, os bots que estavam ativos voltam a rodar.
          </>
        }
        confirmLabel="Desligar"
        danger
        loading={mutation.isPending}
        onConfirm={() => mutation.mutate(false)}
        onClose={() => setConfirmOff(false)}
      />
    </>
  );
}

export function Layout() {
  const { user, logout } = useAuth();
  const [theme, toggleTheme] = useTheme();

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="border-b border-line bg-surface md:sticky md:top-0 md:h-screen md:w-56 md:shrink-0 md:border-r md:border-b-0">
        <div className="flex items-center gap-2 px-4 py-4">
          <img src="/favicon.svg" alt="" className="size-7" />
          <span className="font-semibold">Bot Trader</span>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:pb-0">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                clsx(
                  "flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors",
                  isActive ? "bg-surface-2 font-medium text-ink" : "text-ink-2 hover:bg-surface-2 hover:text-ink",
                )
              }
            >
              <Icon className="size-4" />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-line bg-page/90 px-4 py-2.5 backdrop-blur sm:px-6">
          <EngineSwitch />
          <div className="flex items-center gap-1">
            <span className="mr-2 hidden text-xs text-muted sm:inline">{user?.email}</span>
            <button onClick={toggleTheme} className="rounded-lg p-2 text-ink-2 hover:bg-surface-2" aria-label="Alternar tema">
              {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </button>
            <button onClick={logout} className="rounded-lg p-2 text-ink-2 hover:bg-surface-2" aria-label="Sair">
              <LogOut className="size-4" />
            </button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
