"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import type { OperationStatus } from "@/lib/api/endpoints";
import { addWorkingDays, fd, fromWorkIndex, MONTHS, parseIso, todayIso, weekday, workIndex } from "@/lib/production/dates";
import { cn } from "@/lib/utils";

import { Avatar, HealthDot, Pill } from "./bits";

/**
 * План-график по образцу `ganttHtml`/`bindGantt` прототипа. Шкала — рабочие дни
 * (выходных колонок нет): длительности и переносы на сервере считаются в рабочих
 * днях, и смещение мышью на N колонок — ровно N рабочих дней для `move`/`shift`.
 */

export type GanttOp = {
  id: string;
  seq: number;
  name: string;
  work_center_id: string;
  work_center_short_name: string;
  is_supply: boolean;
  status: OperationStatus;
  progress: number;
  responsible_name: string;
  planned_start: string | null;
  planned_finish: string | null;
  predecessor_ids: string[];
  is_critical: boolean;
  violates_dependency: boolean;
  slack?: number | null;
};

export type GanttRow = {
  id: string;
  number: string;
  customer_name: string;
  product_name: string;
  stage: string;
  due_date: string;
  planned_start: string | null;
  planned_finish: string | null;
  health: { color: string; text: string };
  can_plan: boolean;
  tentative?: boolean;
  operations: GanttOp[];
};

type Props = {
  rows: GanttRow[];
  mini?: boolean;
  colorBy?: "status" | "wc";
  onOpenOrder?: (orderId: string) => void;
  onOpenOperation?: (operationId: string, orderId: string) => void;
  onMoveOperation?: (op: GanttOp, start: string) => void;
  onShiftOrder?: (row: GanttRow, days: number) => void;
};

const DW = 26;
const RH = 30;
const HEAD = 44;

type Drag = { orderId: string; opId: string | null; dd: number };

function locked(row: GanttRow, op: GanttOp | null): boolean {
  if (!row.can_plan || row.stage === "done" || row.tentative) return true;
  return op !== null && op.status !== "wait";
}

function wcColor(id: string, palette: Map<string, number>): string {
  if (!palette.has(id)) palette.set(id, palette.size);
  const hue = (palette.get(id)! * 47) % 360;
  return `hsl(${hue} 60% 80%)`;
}

export function GanttChart({ rows, mini, colorBy = "status", onOpenOrder, onOpenOperation, onMoveOperation, onShiftOrder }: Props) {
  const LW = mini ? 250 : 320;
  const today = todayIso();
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [drag, setDrag] = useState<Drag | null>(null);
  const [tip, setTip] = useState<{ text: string; x: number; y: number } | null>(null);
  const dragRef = useRef<{ x0: number; moved: boolean } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrolledRef = useRef(false);

  const range = useMemo(() => {
    let a = workIndex(today);
    let b = a + 20;
    for (const r of rows) {
      for (const d of [r.planned_start, ...r.operations.map((o) => o.planned_start)]) if (d) a = Math.min(a, workIndex(d));
      for (const d of [r.planned_finish, r.due_date, ...r.operations.map((o) => o.planned_finish)]) if (d) b = Math.max(b, workIndex(d));
    }
    a -= 2;
    b += 5;
    // Начало шкалы — с понедельника, чтобы недели читались ровными блоками по пять.
    while (weekday(fromWorkIndex(a)) !== 0) a -= 1;
    return { from: a, n: b - a + 1 };
  }, [rows, today]);

  const W = range.n * DW;
  const X = (day: string) => (workIndex(day) - range.from) * DW;
  const palette = useMemo(() => new Map<string, number>(), []);

  // Строки: заказ, затем (если раскрыт) его операции с плановой датой.
  const lines: ({ type: "order"; row: GanttRow } | { type: "op"; row: GanttRow; op: GanttOp; index: number })[] = [];
  for (const row of rows) {
    if (!mini) lines.push({ type: "order", row });
    if (mini || !collapsed.has(row.id)) {
      row.operations.forEach((op, index) => {
        if (op.planned_start) lines.push({ type: "op", row, op, index });
      });
    }
  }
  const yOf = new Map<string, number>();
  lines.forEach((l, i) => {
    if (l.type === "op") yOf.set(l.op.id, i * RH + RH / 2);
  });

  function shiftFor(row: GanttRow, op: GanttOp | null): number {
    if (!drag || drag.orderId !== row.id) return 0;
    if (drag.opId === null) return op && locked(row, op) ? 0 : drag.dd;
    return op && op.id === drag.opId ? drag.dd : 0;
  }

  function onPointerDown(e: React.PointerEvent, row: GanttRow, op: GanttOp | null) {
    if (e.button !== 0) return;
    const open = () => {
      setTip(null);
      if (op) onOpenOperation?.(op.id, row.id);
      else onOpenOrder?.(row.id);
    };
    if (locked(row, op)) {
      open();
      return;
    }
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    dragRef.current = { x0: e.clientX, moved: false };
    setDrag({ orderId: row.id, opId: op?.id ?? null, dd: 0 });
  }

  function onPointerMove(e: React.PointerEvent, text: string) {
    if (dragRef.current && drag) {
      const dd = Math.round((e.clientX - dragRef.current.x0) / DW);
      if (dd !== drag.dd) setDrag({ ...drag, dd });
      if (Math.abs(e.clientX - dragRef.current.x0) > 3) dragRef.current.moved = true;
      setTip({ text: `${dd > 0 ? "+" : ""}${dd} раб. дн.`, x: e.clientX, y: e.clientY });
      return;
    }
    setTip({ text, x: e.clientX, y: e.clientY });
  }

  function onPointerUp(row: GanttRow, op: GanttOp | null) {
    const state = drag;
    const moved = dragRef.current?.moved;
    dragRef.current = null;
    setDrag(null);
    setTip(null);
    if (!state) return;
    if (!moved || state.dd === 0) {
      if (op) onOpenOperation?.(op.id, row.id);
      else onOpenOrder?.(row.id);
      return;
    }
    if (op && op.planned_start) onMoveOperation?.(op, addWorkingDays(op.planned_start, state.dd));
    else if (!op) onShiftOrder?.(row, state.dd);
  }

  // Шкала: месяцы, числа, границы недель.
  const head: React.ReactNode[] = [];
  const grid: React.ReactNode[] = [];
  let prevMonth = -1;
  for (let i = 0; i < range.n; i++) {
    const day = fromWorkIndex(range.from + i);
    const dt = new Date(parseIso(day));
    const month = dt.getUTCMonth();
    if (month !== prevMonth) {
      head.push(
        <div key={`m${i}`} className="absolute top-1 pl-1 text-[10.5px] font-semibold whitespace-nowrap" style={{ left: i * DW }}>
          {MONTHS[month]} {dt.getUTCFullYear()}
        </div>,
      );
      prevMonth = month;
    }
    head.push(
      <div
        key={`d${i}`}
        className={cn("absolute top-6 text-center text-[10.5px] text-muted-foreground", day === today && "font-bold text-blue-700")}
        style={{ left: i * DW, width: DW }}
      >
        {dt.getUTCDate()}
      </div>,
    );
    if (weekday(day) === 0) {
      grid.push(<div key={`w${i}`} className="absolute top-0 bottom-0 border-l border-slate-200" style={{ left: LW + i * DW }} />);
    }
  }
  const todayX = X(today) + (weekday(today) < 5 ? DW / 2 : 0);

  // При первом показе — «сегодня» в первой трети видимой шкалы, как удобно диспетчеру:
  // прошлое видно, но основное место — под ближайшие недели.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || scrolledRef.current || !rows.length) return;
    scrolledRef.current = true;
    el.scrollLeft = Math.max(0, todayX - (el.clientWidth - LW) / 3);
  }, [rows.length, todayX, LW]);

  // Стрелки связей: от конца предшественника к началу последователя.
  const arrows: React.ReactNode[] = [];
  for (const row of rows) {
    const byId = new Map(row.operations.map((o) => [o.id, o]));
    for (const op of row.operations) {
      const yb = yOf.get(op.id);
      if (yb === undefined || !op.planned_start) continue;
      for (const pid of op.predecessor_ids) {
        const p = byId.get(pid);
        const ya = yOf.get(pid);
        if (!p || ya === undefined || !p.planned_finish) continue;
        const x1 = X(p.planned_finish) + DW + shiftFor(row, p) * DW;
        const x2 = X(op.planned_start) + shiftFor(row, op) * DW;
        const crit = p.is_critical && op.is_critical;
        const mid = x1 + 5;
        arrows.push(
          <path
            key={`${pid}-${op.id}`}
            d={`M${x1} ${ya} H${mid} V${yb} H${x2 - 1}`}
            fill="none"
            stroke={op.violates_dependency ? "#c53030" : crit ? "#c2410c" : "#8b94a5"}
            strokeWidth={crit ? 1.6 : 1}
            markerEnd={`url(#${crit ? "g-ac" : "g-an"})`}
            opacity={0.85}
          />,
        );
      }
    }
  }

  return (
    <div
      ref={scrollRef}
      className="relative overflow-auto rounded-xl border bg-background"
      style={{ maxHeight: mini ? 420 : "calc(100vh - 230px)" }}
      data-testid={mini ? "mini-gantt" : "gantt"}
    >
      <div className="relative" style={{ width: LW + W }}>
        {/* шапка */}
        <div className="sticky top-0 z-20 flex border-b bg-background" style={{ height: HEAD }}>
          <div
            className="sticky left-0 z-30 flex items-end border-r bg-background px-2.5 pb-1.5 text-xs text-muted-foreground"
            style={{ width: LW, minWidth: LW }}
          >
            {mini ? "Операция" : "Заказ / операция"}
          </div>
          <div className="relative" style={{ width: W }}>
            {head}
          </div>
        </div>

        {grid}
        <div className="pointer-events-none absolute bottom-0 z-[5] w-0.5 bg-blue-600/50" style={{ left: LW + todayX, top: HEAD }} title="Сегодня" />

        {lines.map((line) => {
          if (line.type === "order") {
            const { row } = line;
            const open = !collapsed.has(row.id);
            const dd = shiftFor(row, null);
            return (
              <div key={`o${row.id}`} className="flex border-b border-muted bg-slate-50" style={{ height: RH }}>
                <div
                  className="sticky left-0 z-10 flex cursor-pointer items-center gap-1.5 overflow-hidden border-r bg-slate-50 px-2 text-[12.5px] font-semibold whitespace-nowrap"
                  style={{ width: LW, minWidth: LW }}
                  onClick={() => onOpenOrder?.(row.id)}
                  data-testid="gantt-order-label"
                >
                  <button
                    type="button"
                    className="text-muted-foreground"
                    aria-label={open ? "Свернуть" : "Развернуть"}
                    onClick={(e) => {
                      e.stopPropagation();
                      setCollapsed((s) => {
                        const n = new Set(s);
                        if (n.has(row.id)) n.delete(row.id);
                        else n.add(row.id);
                        return n;
                      });
                    }}
                  >
                    {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
                  </button>
                  <HealthDot color={row.health.color} title={row.health.text} />
                  <span className="truncate">
                    {row.number} <span className="font-normal text-muted-foreground">{row.customer_name}</span>
                  </span>
                  {row.tentative ? <Pill className="ml-auto">предв.</Pill> : null}
                </div>
                <div className="relative" style={{ width: W }}>
                  {row.planned_start && row.planned_finish ? (
                    <div
                      data-testid="gantt-order-bar"
                      data-order={row.id}
                      className={cn(
                        "absolute top-[11px] z-[3] h-2 touch-none rounded-sm bg-slate-700 select-none",
                        locked(row, null) ? "cursor-pointer" : "cursor-grab",
                      )}
                      style={{
                        left: X(row.planned_start) + dd * DW,
                        width: X(row.planned_finish) - X(row.planned_start) + DW,
                      }}
                      onPointerDown={(e) => onPointerDown(e, row, null)}
                      onPointerMove={(e) =>
                        onPointerMove(
                          e,
                          `${row.number}: ${fd(row.planned_start)}–${fd(row.planned_finish)} · срок ${fd(row.due_date)}${
                            locked(row, null) ? "" : " · тяните, чтобы сдвинуть заказ"
                          }`,
                        )
                      }
                      onPointerUp={() => onPointerUp(row, null)}
                      onPointerLeave={() => !drag && setTip(null)}
                    />
                  ) : null}
                  <div
                    className="pointer-events-none absolute top-[3px] h-6 border-l-2 border-dashed border-red-600"
                    style={{ left: X(row.due_date) + DW }}
                    title={`Срок ${fd(row.due_date)}`}
                  />
                </div>
              </div>
            );
          }
          const { row, op, index } = line;
          const start = op.planned_start!;
          const finish = op.planned_finish ?? start;
          const dd = shiftFor(row, op);
          const left = X(start) + dd * DW;
          const width = X(finish) - X(start) + DW;
          const done = op.status === "done";
          const late = !done && !row.tentative && finish < today;
          const pr = done ? 100 : op.progress;
          const lock = locked(row, op);
          const bg =
            colorBy === "wc"
              ? wcColor(op.work_center_id, palette)
              : done
                ? "#a8d8b9"
                : op.is_critical
                  ? "#f4b89a"
                  : op.is_supply
                    ? "#e9d8a6"
                    : "#9fb4ea";
          // Цвет «выполненной части» — тон полосы, как `.gb .pf` прототипа.
          const fill =
            colorBy === "wc"
              ? "rgba(15,23,42,.18)"
              : done
                ? "rgba(31,138,76,.5)"
                : op.is_critical
                  ? "rgba(194,65,12,.45)"
                  : op.is_supply
                    ? "rgba(183,121,31,.5)"
                    : "rgba(47,91,211,.5)";
          const tipText =
            `${index + 1}. ${op.name} · ${op.work_center_short_name} · ${fd(start)}–${fd(finish)}` +
            (op.slack != null ? ` · резерв ${Math.max(0, op.slack)} дн.` : "") +
            (op.is_critical ? " · КРИТИЧЕСКИЙ ПУТЬ" : "") +
            (op.violates_dependency ? " · НАРУШЕНИЕ СВЯЗИ" : "") +
            (late ? " · отставание" : "") +
            (op.responsible_name ? ` · ${op.responsible_name}` : "") +
            ` · ${pr}%`;
          return (
            <div key={op.id} className="flex border-b border-muted" style={{ height: RH }}>
              <div
                className="sticky left-0 z-10 flex cursor-pointer items-center gap-1.5 overflow-hidden border-r bg-background pr-2 text-[12.5px] whitespace-nowrap"
                style={{ width: LW, minWidth: LW, paddingLeft: mini ? 10 : 28 }}
                onClick={() => onOpenOperation?.(op.id, row.id)}
                title="Открыть операцию"
              >
                <span className="w-4 text-muted-foreground">{index + 1}</span>
                <span className="truncate">{op.name}</span>
                <Pill tone={op.is_supply ? "y" : "n"} className="ml-auto">
                  {op.work_center_short_name}
                </Pill>
                {!mini ? <Avatar name={op.responsible_name} /> : null}
              </div>
              <div className="relative" style={{ width: W }}>
                {!done && op.slack && op.slack > 0 ? (
                  <div
                    className="pointer-events-none absolute top-3.5 h-0.5"
                    style={{
                      left: left + width,
                      width: op.slack * DW,
                      background: "repeating-linear-gradient(90deg,#9aa3b3 0 4px,transparent 4px 7px)",
                    }}
                  />
                ) : null}
                <div
                  data-testid="gantt-op-bar"
                  data-op={op.id}
                  data-locked={lock ? "1" : "0"}
                  className={cn(
                    "absolute top-1.5 z-[3] flex h-[18px] touch-none items-center overflow-hidden rounded-[5px] px-1.5 text-[11px] whitespace-nowrap text-slate-900 select-none",
                    lock ? "cursor-pointer" : "cursor-grab",
                    op.is_critical && !done && colorBy === "status" && "shadow-[inset_0_0_0_1.5px_#c2410c]",
                    late && "outline-2 outline-offset-1 outline-red-600",
                    op.violates_dependency && "outline-2 outline-offset-1 outline-dashed outline-red-600",
                    row.tentative && "border border-dashed border-slate-500 opacity-60",
                  )}
                  style={{ left, width, background: bg }}
                  onPointerDown={(e) => onPointerDown(e, row, op)}
                  onPointerMove={(e) => onPointerMove(e, tipText)}
                  onPointerUp={() => onPointerUp(row, op)}
                  onPointerLeave={() => !drag && setTip(null)}
                >
                  <div className="pointer-events-none absolute inset-y-0 left-0" style={{ width: `${pr}%`, background: fill }} />
                  <span className="relative">{Math.max(1, workIndex(finish) - workIndex(start) + 1)} д</span>
                </div>
              </div>
            </div>
          );
        })}

        <svg
          className="pointer-events-none absolute z-[4] overflow-visible"
          style={{ left: LW, top: HEAD }}
          width={W}
          height={lines.length * RH}
        >
          <defs>
            <marker id="g-an" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M0 0L6 3L0 6z" fill="#8b94a5" />
            </marker>
            <marker id="g-ac" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M0 0L6 3L0 6z" fill="#c2410c" />
            </marker>
          </defs>
          {arrows}
        </svg>
      </div>
      {tip ? (
        <div
          className="pointer-events-none fixed z-[70] rounded-md bg-slate-900 px-2 py-1 text-xs whitespace-nowrap text-white"
          style={{ left: tip.x + 12, top: tip.y + 14 }}
          data-testid="gantt-tip"
        >
          {tip.text}
        </div>
      ) : null}
    </div>
  );
}

export function GanttLegend() {
  const item = (style: React.CSSProperties, text: string) => (
    <span className="inline-flex items-center gap-1">
      <i className="inline-block h-2.5 w-[18px] rounded-sm" style={style} />
      {text}
    </span>
  );
  return (
    <span className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      {item({ background: "#f4b89a", boxShadow: "inset 0 0 0 1.5px #c2410c" }, "критический путь")}
      {item({ background: "#9fb4ea" }, "работа")}
      {item({ background: "#e9d8a6" }, "закупка")}
      {item({ background: "#a8d8b9" }, "выполнено")}
      {item({ background: "#9fb4ea", outline: "2px solid #dc2626" }, "отставание")}
      {item({ background: "#9fb4ea", outline: "2px dashed #dc2626" }, "нарушение связи")}
      {item({ background: "repeating-linear-gradient(90deg,#9aa3b3 0 4px,transparent 4px 7px)", height: 2 }, "резерв")}
      {item({ borderLeft: "2px dashed #c53030", width: 2, height: 12, borderRadius: 0 }, "срок")}
      {item({ background: "rgba(37,99,235,.5)", width: 2, height: 12 }, "сегодня")}
    </span>
  );
}
