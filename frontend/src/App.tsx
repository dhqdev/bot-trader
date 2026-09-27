import { createBrowserRouter, RouterProvider } from "react-router";
import { Layout } from "./components/Layout";
import { RouteError } from "./components/RouteError";
import { Loading } from "./components/ui";
import { useAuth } from "./lib/auth";
import { BotDetailPage } from "./pages/BotDetail";
import { DashboardPage } from "./pages/Dashboard";
import { LoginPage } from "./pages/Login";
import { NewRobotPage } from "./pages/NewRobot";
import { RobotsPage } from "./pages/Robots";
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
          { path: "/bots", element: <RobotsPage /> },
          { path: "/bots/new", element: <NewRobotPage /> },
          { path: "/bots/:id", element: <BotDetailPage /> },
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
