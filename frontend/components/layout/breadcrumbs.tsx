"use client";

import { Fragment } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { useBreadcrumbLabels } from "./breadcrumb-labels";

// Статическая карта заголовков по сегменту маршрута — интерфейс полностью русский,
// отдельного i18n-фреймворка нет (см. CLAUDE.md §5, "verbose_name на русском").
// Динамические сегменты (UUID сущности) регистрируют своё имя сами через
// `useDynamicBreadcrumbLabel` — см. `breadcrumb-labels.tsx`.
const SEGMENT_LABELS: Record<string, string> = {
  parties: "Контрагенты",
  items: "Номенклатура",
  board: "Доска",
  gantt: "План-график",
  "my-visas": "Мои визы",
  load: "Загрузка участков",
  cutoffs: "Отсечки",
  quality: "Качество",
  portfolio: "Портфель",
  supply: "Закупки и склад",
  timesheet: "Табель",
  equipment: "Оборудование",
  energy: "Энергоучёт",
  employees: "Сотрудники",
  "work-centers": "Участки",
  orders: "Заказы",
  inquiries: "Заявки",
  new: "Новый",
};

export function Breadcrumbs() {
  const pathname = usePathname();
  const dynamicLabels = useBreadcrumbLabels();
  const segments = pathname.split("/").filter(Boolean);

  if (segments.length === 0) return null;

  function labelFor(segment: string): string {
    return dynamicLabels[segment] ?? SEGMENT_LABELS[segment] ?? segment;
  }

  return (
    <Breadcrumb>
      <BreadcrumbList>
        {segments.map((segment, index) => {
          const href = "/" + segments.slice(0, index + 1).join("/");
          const isLast = index === segments.length - 1;
          return (
            <Fragment key={href}>
              <BreadcrumbItem>
                {isLast ? (
                  <BreadcrumbPage>{labelFor(segment)}</BreadcrumbPage>
                ) : (
                  <BreadcrumbLink render={<Link href={href}>{labelFor(segment)}</Link>} />
                )}
              </BreadcrumbItem>
              {!isLast && <BreadcrumbSeparator />}
            </Fragment>
          );
        })}
      </BreadcrumbList>
    </Breadcrumb>
  );
}
