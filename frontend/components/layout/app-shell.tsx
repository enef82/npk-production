import type { MeOut } from "@/lib/api/endpoints";
import { AuthProvider } from "@/lib/auth/auth-context";
import { BreadcrumbLabelsProvider } from "./breadcrumb-labels";
import { Breadcrumbs } from "./breadcrumbs";
import { CommandSearch } from "./command-search";
import { NotificationsMenu } from "./notifications-menu";
import { Sidebar } from "./sidebar";
import { UserMenu } from "./user-menu";

export function AppShell({ user, children }: { user: MeOut; children: React.ReactNode }) {
  return (
    <AuthProvider user={user}>
      <BreadcrumbLabelsProvider>
        <div className="flex h-svh">
          <Sidebar />
          <div className="flex min-w-0 flex-1 flex-col">
            <header className="flex h-14 shrink-0 items-center gap-4 border-b px-4">
              <Breadcrumbs />
              <div className="ml-auto flex items-center gap-2">
                <CommandSearch />
                <NotificationsMenu />
                <UserMenu />
              </div>
            </header>
            <main className="min-w-0 flex-1 overflow-auto">{children}</main>
          </div>
        </div>
      </BreadcrumbLabelsProvider>
    </AuthProvider>
  );
}
