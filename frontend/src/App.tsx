import { createBrowserRouter, RouterProvider } from "react-router";
import { Layout } from "./components/Layout";
import { RouteError } from "./components/RouteError";
import { Loading } from "./components/ui";
import { useAuth } from "./lib/auth";
import { AIPage } from "./pages/AI";
import { AutopilotPage } from "./pages/Autopilot";
import { BotDetailPage } from "./pages/BotDetail";
import { BotFormPage } from "./pages/BotForm";
import { BotsPage } from "./pages/Bots";
import { DashboardPage } from "./pages/Dashboard";
import { LabPage } from "./pages/Lab";
import { LoginPage } from "./pages/Login";
import { NewsPage } from "./pages/News";
import { SettingsPage } from "./pages/Settings";

const router = createBrowserRouter([
  {
    element: <Layout />,
    errorElement: <RouteError standalone />,
    children: [
      {
        // erros de uma tela aparecem dentro do layout, com o menu funcionando
        errorElement: <RouteError />,
        children: [
          { path: "/", element: <DashboardPage /> },
          { path: "/bots", element: <BotsPage /> },
          { path: "/bots/new", element: <BotFormPage /> },
          { path: "/bots/:id", element: <BotDetailPage /> },
          { path: "/bots/:id/edit", element: <BotFormPage /> },
          { path: "/lab", element: <LabPage /> },
          { path: "/ai", element: <AIPage /> },
          { path: "/ai/piloto", element: <AutopilotPage /> },
          { path: "/ai/noticias", element: <NewsPage /> },
          { path: "/settings", element: <SettingsPage /> },
          { path: "*", element: <DashboardPage /> },
        ],
      },
    ],
  },
]);

export function App() {
  const { loading, user } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <LoginPage />;
  return <RouterProvider router={router} />;
}
