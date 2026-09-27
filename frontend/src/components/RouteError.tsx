import { AlertTriangle } from "lucide-react";
import { isRouteErrorResponse, Link, useRouteError } from "react-router";
import { Button } from "./ui";

/** Tela de erro amigável: os robôs continuam no servidor, só a tela falhou. */
export function RouteError({ standalone = false }: { standalone?: boolean }) {
  const error = useRouteError();
  const detail = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : String(error);
  return (
    <div className={standalone ? "flex min-h-dvh items-center justify-center p-6" : "py-10"}>
      <div className="mx-auto max-w-md space-y-3 rounded-xl border border-line bg-surface p-6 text-sm">
        <h1 className="flex items-center gap-2 text-base font-semibold">
          <AlertTriangle className="size-5 text-warn-text" /> Esta tela encontrou um erro
        </h1>
        <p className="text-ink-2">
          Os robôs continuam rodando normalmente no servidor; só a exibição desta tela falhou. Recarregue a página. Se o erro continuar, me envie a mensagem abaixo.
        </p>
        <pre className="overflow-x-auto rounded-lg bg-surface-2 p-2 text-xs whitespace-pre-wrap text-muted">{detail}</pre>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" onClick={() => window.location.reload()}>
            Recarregar
          </Button>
          <Link to="/" className="inline-flex h-9 items-center rounded-lg px-4 text-sm text-ink-2 hover:bg-surface-2">
            Ir para o painel
          </Link>
        </div>
      </div>
    </div>
  );
}
