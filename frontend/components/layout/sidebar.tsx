"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { MODULE_NAV, REFERENCE_NAV, type NavItem } from "./nav-items";

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;

  if (item.disabled) {
    return (
      <span
        className="flex cursor-not-allowed items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground/50"
        aria-disabled="true"
        title="Появится на следующих шагах"
      >
        <Icon className="size-4 shrink-0" aria-hidden />
        {item.label}
      </span>
    );
  }

  return (
    <Link
      href={item.href}
      className={cn(
        "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors hover:bg-accent hover:text-accent-foreground",
        active && "bg-accent font-medium text-accent-foreground",
      )}
      aria-current={active ? "page" : undefined}
    >
      <Icon className="size-4 shrink-0" aria-hidden />
      {item.label}
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();

  return (
    <nav
      className="flex h-full w-60 shrink-0 flex-col gap-6 overflow-y-auto border-r bg-sidebar px-3 py-4"
      aria-label="Разделы системы"
    >
      <Link href="/board" className="px-3 text-lg font-semibold tracking-tight">
        НПК Производство
      </Link>

      <div className="flex flex-col gap-1">
        <p className="px-3 text-xs font-medium tracking-wide text-muted-foreground uppercase">
          Справочники
        </p>
        {REFERENCE_NAV.map((item) => (
          <NavLink key={item.href} item={item} active={pathname.startsWith(item.href)} />
        ))}
      </div>

      <div className="flex flex-col gap-1">
        <p className="px-3 text-xs font-medium tracking-wide text-muted-foreground uppercase">
          Модули
        </p>
        {MODULE_NAV.map((item) => (
          <NavLink key={item.href} item={item} active={pathname.startsWith(item.href)} />
        ))}
      </div>
    </nav>
  );
}
