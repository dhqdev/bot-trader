import clsx from "clsx";
import { Bot, MessageSquare, Newspaper } from "lucide-react";
import { NavLink } from "react-router";

const TABS = [
  { to: "/ai", label: "Conversa", short: "Conversa", icon: MessageSquare, end: true },
  { to: "/ai/piloto", label: "Piloto automático", short: "Piloto", icon: Bot, end: false },
  { to: "/ai/noticias", label: "Notícias e sentimento", short: "Notícias", icon: Newspaper, end: false },
];

/** Abas da área de IA (conversa, piloto automático, notícias). */
export function AITabs() {
  return (
    <nav aria-label="Seções da IA" className="-mt-2 mb-5 flex gap-1 overflow-x-auto border-b border-line">
      {TABS.map(({ to, label, short, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          aria-label={label}
          className={({ isActive }) =>
            clsx(
              "-mb-px flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors",
              isActive ? "border-accent text-ink" : "border-transparent text-ink-2 hover:text-ink",
            )
          }
        >
          <Icon className="size-4" />
          <span className="sm:hidden">{short}</span>
          <span className="hidden sm:inline">{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
