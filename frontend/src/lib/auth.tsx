import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, type ReactNode } from "react";
import { api } from "./api";
import type { AuthStatus, User } from "./types";

interface AuthValue {
  status: AuthStatus | undefined;
  user: User | null;
  loading: boolean;
  refresh: () => Promise<unknown>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["auth"], queryFn: () => api.get<AuthStatus>("/auth/status"), staleTime: 60_000 });

  useEffect(() => {
    const onUnauthorized = () => qc.invalidateQueries({ queryKey: ["auth"] });
    window.addEventListener("bt:unauthorized", onUnauthorized);
    return () => window.removeEventListener("bt:unauthorized", onUnauthorized);
  }, [qc]);

  const value: AuthValue = {
    status: query.data,
    user: query.data?.user ?? null,
    loading: query.isLoading,
    refresh: () => query.refetch(),
    logout: async () => {
      await api.post("/auth/logout");
      qc.clear();
      await query.refetch();
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth fora do AuthProvider");
  return ctx;
}
