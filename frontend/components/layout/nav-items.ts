import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BadgeCheck,
  Boxes,
  Building2,
  CalendarRange,
  ClipboardCheck,
  Factory,
  Gauge,
  KanbanSquare,
  LineChart,
  ShoppingCart,
  Timer,
  Users,
  Wrench,
  Zap,
} from "lucide-react";

export type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  /** Экран ещё не реализован — пункт виден, но некликабелен. */
  disabled?: boolean;
};

export const REFERENCE_NAV: NavItem[] = [
  { label: "Контрагенты", href: "/parties", icon: Building2 },
  { label: "Номенклатура", href: "/items", icon: Boxes },
];

/** Экраны приложения — `docs/spec/00-prilozhenie-proizvodstvo.md` §6. */
export const MODULE_NAV: NavItem[] = [
  { label: "Доска", href: "/board", icon: KanbanSquare },
  { label: "План-график", href: "/gantt", icon: CalendarRange },
  { label: "Мои визы", href: "/my-visas", icon: BadgeCheck },
  { label: "Загрузка участков", href: "/load", icon: Gauge },
  { label: "Отсечки", href: "/cutoffs", icon: Activity },
  { label: "Качество", href: "/quality", icon: ClipboardCheck },
  { label: "Портфель", href: "/portfolio", icon: LineChart },
  { label: "Закупки и склад", href: "/supply", icon: ShoppingCart },
  { label: "Табель", href: "/timesheet", icon: Timer },
  { label: "Оборудование", href: "/equipment", icon: Wrench },
  { label: "Энергоучёт", href: "/energy", icon: Zap },
  { label: "Сотрудники", href: "/employees", icon: Users },
  { label: "Участки", href: "/work-centers", icon: Factory },
];
