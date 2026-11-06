import { redirect } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { getSession } from "@/lib/auth/session";

// Настоящая проверка сессии (middleware.ts делает только дешёвую проверку наличия
// cookie на входе, см. её докстроку) — идёт в Django за актуальным пользователем
// с cookies текущего запроса. 401/сессия невалидна → редирект на /login.
export default async function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const user = await getSession();
  if (!user) {
    redirect("/login");
  }

  return <AppShell user={user}>{children}</AppShell>;
}
