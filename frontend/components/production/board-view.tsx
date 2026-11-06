"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Plus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useGetProductionBoard,
  useGetSalesBoard,
  useListMyProductionVisas,
  useListMySalesVisas,
} from "@/lib/api/endpoints";
import { fd } from "@/lib/production/dates";
import { krub, num } from "@/lib/production/format";
import { BOARD_STAGES, checkMove, type BoardStage } from "@/lib/production/stages";
import { cn } from "@/lib/utils";

import { Avatar, HealthDot, NativeSelect, Pill, ProgressBar, TextInput, Visa } from "./bits";
import { useCards, type StageTarget } from "./card-host";
import { NewInquiryDialog } from "./new-inquiry-dialog";

type BoardItem = {
  key: string;
  target: StageTarget;
  stage: BoardStage;
  number: string;
  badge: string;
  title: string;
  customer: string;
  due: string;
  health: { color: string; text: string };
  total: number;
  progress: number | null;
  calcFlags: { calc: boolean; plan: boolean } | null;
  responsible: string;
  approved: boolean;
  managerId: string;
  managerName: string;
  needsMe: boolean;
  search: string;
};

type KpiFilter = "inq" | "act" | "red" | "yel" | "mine" | null;

const KPI_FILTERS: Record<Exclude<KpiFilter, null>, { title: string; test: (i: BoardItem) => boolean }> = {
  inq: { title: "Заявки в работе", test: (i) => i.target.kind === "inquiry" },
  act: { title: "Заказы в производстве", test: (i) => i.target.kind === "order" && i.stage !== "done" },
  red: { title: "Срыв срока", test: (i) => i.target.kind === "order" && i.stage !== "done" && i.health.color === "r" },
  yel: { title: "Под риском", test: (i) => i.target.kind === "order" && i.stage !== "done" && i.health.color === "y" },
  mine: { title: "Ждут моей визы", test: (i) => i.needsMe },
};

/** Доска (§6, `renderKpis`/`cardHtml`/`renderBoard` прототипа). */
export function BoardView() {
  const cards = useCards();
  const orders = useGetProductionBoard();
  const inquiries = useGetSalesBoard();
  const orderVisas = useListMyProductionVisas();
  const inquiryVisas = useListMySalesVisas();
  const [search, setSearch] = useState("");
  const [manager, setManager] = useState("");
  const [kpi, setKpi] = useState<KpiFilter>(null);
  const [dragKey, setDragKey] = useState<string | null>(null);
  const [overStage, setOverStage] = useState<BoardStage | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const items = useMemo<BoardItem[]>(() => {
    const mineOrders = new Set((orderVisas.data ?? []).map((v) => v.order_id));
    const mineInquiries = new Set((inquiryVisas.data ?? []).map((v) => v.inquiry_id));
    const list: BoardItem[] = [];
    for (const c of inquiries.data ?? []) {
      if (c.stage !== "new" && c.stage !== "calc" && c.stage !== "approval") continue;
      list.push({
        key: `i${c.id}`,
        target: { kind: "inquiry", card: c },
        stage: c.stage,
        number: c.number,
        badge: "",
        title: `${c.product_name || "изделие не указано"} × ${Number(c.quantity)}`,
        customer: `${c.customer_name} · ${c.object_name}`,
        due: c.due_date,
        health: c.health,
        total: num(c.total),
        progress: null,
        calcFlags: c.stage === "calc" ? { calc: c.has_calc, plan: c.has_plan } : null,
        responsible: c.stage_responsible_name,
        approved: c.stage_approved,
        managerId: c.manager_id,
        managerName: c.manager_name,
        needsMe: mineInquiries.has(c.id),
        search: [c.number, c.customer_name, c.object_name, c.product_name].join(" ").toLowerCase(),
      });
    }
    for (const c of orders.data ?? []) {
      list.push({
        key: `o${c.id}`,
        target: { kind: "order", card: c },
        stage: c.stage,
        number: c.inquiry_number || c.number,
        badge: c.number,
        title: `${c.product_name} × ${Number(c.quantity)}`,
        customer: `${c.customer_name} · ${c.object_name}`,
        due: c.due_date,
        health: c.health,
        total: num(c.contract_total),
        progress: c.stage === "launch" || c.stage === "done" ? null : num(c.progress),
        calcFlags: null,
        responsible: c.stage_responsible_name,
        approved: c.stage_approved,
        managerId: c.manager_id,
        managerName: c.manager_name,
        needsMe: mineOrders.has(c.id),
        search: [c.number, c.inquiry_number, c.customer_name, c.object_name, c.product_name].join(" ").toLowerCase(),
      });
    }
    return list;
  }, [orders.data, inquiries.data, orderVisas.data, inquiryVisas.data]);

  const managers = useMemo(() => {
    const m = new Map<string, string>();
    for (const i of items) m.set(i.managerId, i.managerName);
    return [...m.entries()].sort((a, b) => a[1].localeCompare(b[1], "ru"));
  }, [items]);

  const q = search.trim().toLowerCase();
  const visible = items.filter(
    (i) => (!q || i.search.includes(q)) && (!manager || i.managerId === manager) && (!kpi || KPI_FILTERS[kpi].test(i)),
  );

  const inq = items.filter((i) => i.target.kind === "inquiry");
  const act = items.filter(KPI_FILTERS.act.test);
  const pipe = inq.filter((i) => i.stage !== "new").reduce((s, i) => s + i.total, 0);
  const portfolio = act.reduce((s, i) => s + i.total, 0);
  const red = act.filter((i) => i.health.color === "r").length;
  const yel = act.filter((i) => i.health.color === "y").length;
  const visas = (orderVisas.data?.length ?? 0) + (inquiryVisas.data?.length ?? 0);
  const dragItem = dragKey ? items.find((i) => i.key === dragKey) : undefined;
  const loading = orders.isLoading || inquiries.isLoading;

  const Kpi = ({ id, value, label, tone, onClick }: { id?: KpiFilter; value: React.ReactNode; label: string; tone?: string; onClick?: () => void }) => (
    <button
      type="button"
      onClick={onClick ?? (() => setKpi((k) => (k === id ? null : id!)))}
      className={cn(
        "min-w-[140px] rounded-xl border bg-background px-3.5 py-2 text-left hover:border-slate-300",
        id && kpi === id && "border-blue-600 ring-2 ring-blue-600/20",
        tone === "me" && "border-blue-600 bg-blue-50",
      )}
      data-testid={id ? `kpi-${id}` : undefined}
    >
      <b
        className={cn(
          "block text-lg tabular-nums",
          tone === "r" && "text-red-600",
          tone === "y" && "text-amber-600",
        )}
      >
        {value}
      </b>
      <span className="text-xs text-muted-foreground">{label}</span>
    </button>
  );

  return (
    <div className="flex h-full flex-col bg-slate-50">
      <div className="flex flex-wrap items-center gap-2.5 px-4 pt-3">
        <h1 className="text-lg font-semibold">Доска</h1>
        <TextInput className="w-56" placeholder="Поиск: номер, заказчик, объект" value={search} onChange={(e) => setSearch(e.target.value)} name="board-search" />
        <NativeSelect className="w-52" value={manager} onChange={(e) => setManager(e.target.value)} aria-label="Менеджер">
          <option value="">Все менеджеры</option>
          {managers.map(([id, name]) => (
            <option key={id} value={id}>
              {name}
            </option>
          ))}
        </NativeSelect>
        <span className="flex-1" />
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="size-4" aria-hidden />
          Новая заявка
        </Button>
      </div>
      <div className="flex flex-wrap gap-2.5 px-4 pt-3" data-testid="kpis">
        <Kpi id="inq" value={inq.length} label="заявок в работе" />
        <Kpi id="inq" value={krub(pipe)} label="сумма КП в работе" />
        <Kpi id="act" value={act.length} label="заказов в производстве" />
        <Kpi id="act" value={krub(portfolio)} label="портфель с НДС" />
        <Kpi id="red" value={red} label="срыв срока" tone={red ? "r" : undefined} />
        <Kpi id="yel" value={yel} label="под риском" tone={yel ? "y" : undefined} />
        <Kpi id="mine" value={visas} label="ждут моей визы" tone={visas ? "me" : undefined} />
        {kpi ? (
          <div className="flex items-center gap-1 self-center text-sm">
            Фильтр: <b>{KPI_FILTERS[kpi].title}</b> · {visible.length}
            <Button size="icon-xs" variant="ghost" aria-label="Сбросить фильтр" onClick={() => setKpi(null)}>
              <X />
            </Button>
          </div>
        ) : null}
        {visas ? (
          <Link href="/my-visas" className="self-center text-sm text-blue-700 hover:underline">
            Список моих виз ›
          </Link>
        ) : null}
      </div>
      <div className="flex-1 overflow-auto px-4 pt-3 pb-4">
        {loading ? (
          <div className="flex gap-2.5">
            {BOARD_STAGES.map((s) => (
              <Skeleton key={s.id} className="h-64 w-60 shrink-0" />
            ))}
          </div>
        ) : (
          <div className="flex min-h-full items-stretch gap-2.5" data-testid="board">
            {BOARD_STAGES.map((s) => {
              const list = visible.filter((i) => i.stage === s.id).sort((a, b) => (a.due < b.due ? -1 : 1));
              const sum = list.reduce((a, i) => a + i.total, 0);
              const deny = dragItem && dragItem.stage !== s.id ? checkMove(dragItem.stage, s.id) : null;
              const over = overStage === s.id && dragItem && dragItem.stage !== s.id;
              return (
                <div key={s.id} className="contents">
                  {s.id === "launch" ? <div className="w-0.5 shrink-0 bg-border" title="Заявка → производственный заказ" /> : null}
                  <section
                    data-stage={s.id}
                    data-testid={`col-${s.id}`}
                    className={cn(
                      "flex w-60 min-w-0 shrink-0 flex-col rounded-xl border-2 border-dashed border-transparent bg-slate-200/50 transition-colors",
                      over && !deny && "border-blue-600 bg-blue-50",
                      over && deny && "border-red-600 bg-red-50",
                    )}
                    onDragOver={(e) => {
                      if (!dragItem) return;
                      e.preventDefault();
                      if (overStage !== s.id) setOverStage(s.id);
                    }}
                    onDragLeave={(e) => {
                      if (!e.currentTarget.contains(e.relatedTarget as Node)) setOverStage(null);
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      setOverStage(null);
                      const item = items.find((i) => i.key === (dragKey ?? e.dataTransfer.getData("text/plain")));
                      setDragKey(null);
                      if (item && item.stage !== s.id) cards.moveTo(item.target, s.id);
                    }}
                  >
                    <div className="flex items-baseline gap-1.5 px-3 pt-2.5">
                      <b className="text-[13px]">{s.title}</b>
                      <span className="text-xs text-muted-foreground">{list.length}</span>
                      <span className="ml-auto text-xs text-muted-foreground tabular-nums">{sum ? krub(sum) : ""}</span>
                    </div>
                    <div className="px-3 pb-1.5 text-[11px] tracking-wide text-muted-foreground uppercase">{s.hint}</div>
                    <div className="flex min-h-20 flex-1 flex-col gap-2 px-2 pt-1 pb-2.5">
                      {list.map((item) => (
                        <BoardCard
                          key={item.key}
                          item={item}
                          dragging={dragKey === item.key}
                          onDragStart={(e) => {
                            setDragKey(item.key);
                            e.dataTransfer.effectAllowed = "move";
                            e.dataTransfer.setData("text/plain", item.key);
                          }}
                          onDragEnd={() => {
                            setDragKey(null);
                            setOverStage(null);
                          }}
                          onOpen={() =>
                            item.target.kind === "order" ? cards.openOrder(item.target.card.id) : cards.openInquiry(item.target.card.id)
                          }
                        />
                      ))}
                    </div>
                  </section>
                </div>
              );
            })}
          </div>
        )}
      </div>
      <NewInquiryDialog open={createOpen} onOpenChange={setCreateOpen} onCreated={(id) => cards.openInquiry(id)} />
    </div>
  );
}

function BoardCard({
  item,
  dragging,
  onDragStart,
  onDragEnd,
  onOpen,
}: {
  item: BoardItem;
  dragging: boolean;
  onDragStart: (e: React.DragEvent) => void;
  onDragEnd: () => void;
  onOpen: () => void;
}) {
  const showVisa = item.stage !== "new" && item.stage !== "done";
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onClick={onOpen}
      data-testid="board-card"
      data-number={item.target.card.number}
      className={cn(
        "relative min-w-0 cursor-grab rounded-lg border bg-background px-2.5 py-2 hover:border-slate-300",
        dragging && "opacity-40",
        item.needsMe && "shadow-[inset_3px_0_0_#2563eb]",
      )}
    >
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <HealthDot color={item.health.color} title={item.health.text} />
        <span className="font-semibold text-foreground">{item.number}</span>
        {item.badge ? <Pill tone="b">{item.badge}</Pill> : null}
        <span className="flex-1" />
        <Avatar name={item.responsible} mine={item.needsMe} />
      </div>
      <div className="mt-1 mb-0.5 font-medium">{item.title}</div>
      <div className="truncate text-xs text-muted-foreground" title={item.customer}>
        {item.customer}
      </div>
      <div className="mt-1.5 flex items-center justify-between gap-1.5 text-xs">
        <span className="font-semibold tabular-nums">{item.total ? krub(item.total) : <span className="font-normal text-muted-foreground">не посчитано</span>}</span>
        <span className="text-muted-foreground">до {fd(item.due)}</span>
      </div>
      {item.health.color !== "n" ? (
        <div className="mt-1 text-[11.5px]">
          <Pill tone={item.health.color}>{item.health.text}</Pill>
        </div>
      ) : null}
      {item.progress !== null ? (
        <>
          <ProgressBar value={item.progress} className="mt-1.5" />
          <div className="mt-0.5 text-right text-[11px] text-muted-foreground">{Math.round(item.progress)}%</div>
        </>
      ) : null}
      {item.calcFlags ? (
        <div className="mt-1.5 flex gap-1">
          <Pill tone={item.calcFlags.calc ? "g" : "n"}>калькуляция {item.calcFlags.calc ? "✓" : "—"}</Pill>
          <Pill tone={item.calcFlags.plan ? "g" : "n"}>план {item.calcFlags.plan ? "✓" : "—"}</Pill>
        </div>
      ) : null}
      {showVisa ? (
        <div className="mt-1 text-xs">
          {item.approved ? (
            <Visa>виза</Visa>
          ) : (
            <span className={cn("text-muted-foreground", item.needsMe && "font-medium text-blue-700")}>
              {item.needsMe ? "нужна моя виза" : `ждёт визы ${item.responsible || ""}`}
            </span>
          )}
        </div>
      ) : null}
    </div>
  );
}
