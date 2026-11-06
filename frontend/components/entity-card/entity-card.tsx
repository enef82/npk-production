"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export type EntityCardTab = {
  value: string;
  label: string;
  content: React.ReactNode;
};

export type EntityCardProps = {
  title: string;
  subtitle?: string;
  /** Значки статуса и т.п. рядом с заголовком — рендерятся вызывающей стороной. */
  badges?: React.ReactNode;
  tabs: EntityCardTab[];
  defaultTab?: string;
  /** Боковая панель — вложения, контакты, метаданные; не обязательна. */
  sidePanel?: React.ReactNode;
};

/**
 * Типовая карточка сущности: шапка + вкладки + опциональная боковая панель.
 * Содержимое вкладок и панели — целиком на вызывающей стороне (см.
 * `EntityCardEmptyBlock` для вкладок, у которых пока нет backend'а, например
 * «Документы»/«История»/«Согласования» — не выдумываем данные, честно показываем
 * пустое состояние).
 */
export function EntityCard({ title, subtitle, badges, tabs, defaultTab, sidePanel }: EntityCardProps) {
  return (
    <div className="flex h-full gap-6 overflow-auto p-6">
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <header>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-xl font-semibold">{title}</h1>
            {badges}
          </div>
          {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
        </header>

        <Tabs defaultValue={defaultTab ?? tabs[0]?.value} className="min-h-0 flex-1">
          <TabsList>
            {tabs.map((tab) => (
              <TabsTrigger key={tab.value} value={tab.value}>
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>
          {tabs.map((tab) => (
            <TabsContent key={tab.value} value={tab.value} className="mt-4">
              {tab.content}
            </TabsContent>
          ))}
        </Tabs>
      </div>

      {sidePanel && <aside className="w-72 shrink-0 border-l pl-6">{sidePanel}</aside>}
    </div>
  );
}
