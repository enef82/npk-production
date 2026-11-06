"use client";

import { createContext, useContext } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";

import { useLogout } from "@/lib/api/endpoints";
import type { MeOut } from "@/lib/api/endpoints";

type AuthContextValue = {
  user: MeOut;
  logout: () => void;
  isLoggingOut: boolean;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ user, children }: { user: MeOut; children: React.ReactNode }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const logoutMutation = useLogout({
    mutation: {
      meta: { skipGlobalErrorToast: true },
      onSettled: () => {
        queryClient.clear();
        router.push("/login");
      },
    },
  });

  return (
    <AuthContext.Provider
      value={{
        user,
        logout: () => logoutMutation.mutate(),
        isLoggingOut: logoutMutation.isPending,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth должен вызываться внутри AuthProvider.");
  return ctx;
}
