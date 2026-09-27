import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { Bot, Download, FlaskConical, LayoutDashboard, LogOut, Moon, Power, RefreshCw, Settings, Sparkles, Sun, WifiOff } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { duration } from "../lib/format";
import { APP_VERSION, setThemeColor, useInstallPrompt, useOnline } from "../lib/pwa";
import type { SystemInfo } from "../lib/types";
import { Confirm } from "./ui";

const NAV = [
  { to: "/", label: "Painel", short: "Painel", icon: LayoutDashboard, end: true },
  { to: "/bots", label: "Bots", short: "Bots", icon: Bot },
  { to: "/lab", label: "Laboratório", short: "Lab", icon: FlaskConical },
  { to: "/ai", label: "Análise IA", short: "IA", icon: Sparkles },
  { to: "/settings", label: "Configurações", short: "Ajustes", icon: Settings },
];

function useTheme(): [string, () => void] {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme ?? "dark");
  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    setThemeColor(next);
    try {
      localStorage.setItem("bt-theme", next);
    } catch {
      /* armazenamento bloqueado */
    }
    setTheme(next);
  };
  return [theme, toggle];
}

function useSystem() {
  return useQuery({ queryKey: ["system"], queryFn: () => api.get<SystemInfo>("/system"), refetchInterval: 15_000 });
}

function EngineSwitch() {
  const qc = useQueryClient();
  const [confirmOff, setConfirmOff] = useState(false);
  const { data } = useSystem();
  const mutation = useMutation({
    mutationFn: (enabled: boolean) => api.post<SystemInfo>("/system/engine", { enabled }),
    onSuccess: (info) => {
      qc.setQueryData(["system"], info);
      qc.invalidateQueries({ queryKey: ["bots"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      setConfirmOff(false);
    },
  });
  if (!data) return <span className="h-8" />;
  const on = data.engine_enabled;
  return (
    <>
      <button
        onClick={() => (on ? setConfirmOff(true) : mutation.mutate(true))}
        className={clsx(
          "flex min-h-9 items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
          on ? "border-good/40 text-good-text hover:bg-surface-2" : "border-bad/40 text-bad-text hover:bg-surface-2",
        )}
        title={on ? "Toque para desligar o sistema" : "Toque para ligar o sistema"}
      >
        <Power className="size-3.5" />
        <span className="sm:hidden">{on ? "Ligado" : "Desligado"}</span>
        <span className="hidden sm:inline">{on ? "Sistema ligado" : "Sistema desligado"}</span>
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

/** Avisos no topo: sem conexão e versão nova publicada no servidor. */
function Banners() {
  const online = useOnline();
  const { data } = useSystem();
  const outdated = Boolean(data?.version && data.version !== APP_VERSION);
  if (online && !outdated) return null;
  return (
    <div className="border-b border-line bg-surface-2 px-4 py-2 text-xs sm:px-6">
      {!online ? (
        <span className="flex items-center gap-2 text-warn-text">
          <WifiOff className="size-3.5" /> Sem conexão. Os dados mostrados podem estar desatualizados; os bots continuam rodando no servidor.
        </span>
      ) : (
        <button onClick={() => window.location.reload()} className="flex items-center gap-2 text-accent">
          <RefreshCw className="size-3.5" /> Nova versão disponível ({data?.version}). Toque para atualizar.
        </button>
      )}
    </div>
  );
}

function IconButton({ onClick, label, children }: { onClick: () => void; label: string; children: React.ReactNode }) {
  return (
    <button onClick={onClick} className="grid size-9 place-items-center rounded-lg text-ink-2 hover:bg-surface-2" aria-label={label} title={label}>
      {children}
    </button>
  );
}

export function Layout() {
  const { user, logout } = useAuth();
  const [theme, toggleTheme] = useTheme();
  const { canInstall, install } = useInstallPrompt();
  const { pathname } = useLocation();

  // corpo com chaves: no Chrome atual scrollTo devolve uma Promise, e um efeito
  // não pode devolver nada além de uma função de limpeza
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return (
    <div className="flex min-h-dvh flex-col md:flex-row">
      {/* menu lateral (computador) */}
      <aside className="hidden border-r border-line bg-surface md:sticky md:top-0 md:flex md:h-dvh md:w-56 md:shrink-0 md:flex-col">
        <div className="flex items-center gap-2 px-4 py-4">
          <img src="/favicon.svg" alt="" className="size-7" />
          <span className="font-semibold">Bot Trader</span>
        </div>
        <nav className="flex flex-col gap-1 px-2">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors",
                  isActive ? "bg-surface-2 font-medium text-ink" : "text-ink-2 hover:bg-surface-2 hover:text-ink",
                )
              }
            >
              <Icon className="size-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto px-4 py-3 text-[11px] text-muted">v{APP_VERSION}</div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-line bg-page/90 pt-[env(safe-area-inset-top)] backdrop-blur">
          <div className="flex items-center justify-between gap-2 px-4 py-2 sm:px-6">
            <div className="flex min-w-0 items-center gap-2">
              <img src="/favicon.svg" alt="" className="size-7 md:hidden" />
              <EngineSwitch />
            </div>
            <div className="flex items-center gap-0.5">
              {canInstall && (
                <button
                  onClick={install}
                  className="mr-1 flex min-h-9 items-center gap-1.5 rounded-lg border border-line px-2.5 text-xs font-medium text-ink hover:bg-surface-2"
                >
                  <Download className="size-3.5" /> Instalar app
                </button>
              )}
              <span className="mr-2 hidden text-xs text-muted lg:inline">{user?.email}</span>
              <IconButton onClick={toggleTheme} label="Alternar tema claro/escuro">
                {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
              </IconButton>
              <IconButton onClick={logout} label="Sair">
                <LogOut className="size-4" />
              </IconButton>
            </div>
          </div>
          <Banners />
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 px-4 pt-5 pb-[calc(5.5rem+env(safe-area-inset-bottom))] sm:px-6 md:py-6">
          <Outlet />
        </main>
      </div>

      {/* navegação inferior (celular) */}
      <nav
        className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
        aria-label="Navegação principal"
      >
        <div className="grid grid-cols-5">
          {NAV.map(({ to, short, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                clsx(
                  "flex min-h-14 flex-col items-center justify-center gap-1 text-[11px] font-medium transition-colors",
                  isActive ? "text-accent" : "text-ink-2 active:text-ink",
                )
              }
            >
              <Icon className="size-5" />
              {short}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
