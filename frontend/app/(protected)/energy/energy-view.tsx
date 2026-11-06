"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Kpi, KpiRow } from "@/components/charts/kpi";
import { LineChart } from "@/components/charts/line-chart";
import { StackChart } from "@/components/charts/stack-chart";
import { parseDecimalInput } from "@/components/editable-grid/decimal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import {
  setEnergyTariff,
  useGetEnergyConsumption,
  useGetEnergyDaily,
  useGetEnergyMeterTree,
  useGetEnergyProfile,
  useGetEnergySpecific,
  useListEnergyResources,
  useListScadaMessages,
  type MeterTreeRowOut,
  type ResourceOut,
} from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/mutator";
import { formatDate, formatDateTime } from "@/lib/format/ru";
import { cn } from "@/lib/utils";

import { addDays, daysBetween, isWeekend, isWorkSlot, lastWorkday, monthShort, monthStartBack, yesterday } from "./dates";
import { ReadingsDialog } from "./readings-dialog";

const PERIODS = [7, 14, 28];
const COLORS = ["#2f5bd3", "#7d96e0", "#e9a23b", "#c2410c", "#8fd1a8", "#b4bac4", "#6b7380"];

const KIND_LABELS: Record<string, string> = {
  input: "ввод",
  node: "узел",
  shop: "цех",
  equipment: "оборудование",
  compressor: "компрессор",
  office: "АБК",
  other: "прочее",
};

function n0(value: string | number): string {
  return Math.round(Number(value)).toLocaleString("ru-RU");
}

function rub(value: string | number): string {
  return `${Math.round(Number(value)).toLocaleString("ru-RU")} ₽`;
}

function Panel({ title, children, className, action }: { title: React.ReactNode; children: React.ReactNode; className?: string; action?: React.ReactNode }) {
  return (
    <section className={cn("rounded-xl border bg-card p-4", className)}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">{title}</h2>
        <span className="flex-1" />
        {action}
      </div>
      {children}
    </section>
  );
}

export function EnergyView() {
  const [resource, setResource] = useState("el");
  const [period, setPeriod] = useState(28);
  const [selected, setSelected] = useState<string | null>(null);
  const [day, setDay] = useState(() => lastWorkday(yesterday()));
  const [readingsOpen, setReadingsOpen] = useState(false);

  const dateTo = yesterday();
  const dateFrom = addDays(dateTo, -(period - 1));
  const range = { resource, date_from: dateFrom, date_to: dateTo };

  const resources = useListEnergyResources();
  const tree = useGetEnergyMeterTree(range);
  const daily = useGetEnergyDaily(range);
  const monthly = useGetEnergyConsumption({ resource, by_month: true, date_from: monthStartBack(5), date_to: dateTo });
  const specific = useGetEnergySpecific({ date_from: dateFrom, date_to: dateTo }, { query: { enabled: resource === "el" } });
  const scada = useListScadaMessages();

  const res = resources.data?.items.find((r) => r.code === resource);
  const rows = tree.data ?? [];
  const roots = rows.filter((r) => r.level === 0);
  const meterId = selected && rows.some((r) => r.meter_id === selected) ? selected : roots[0]?.meter_id ?? "";
  const meter = rows.find((r) => r.meter_id === meterId);
  const profile = useGetEnergyProfile({ meter_id: meterId, day }, { query: { enabled: Boolean(meterId) } });

  const total = roots.reduce((s, r) => s + Number(r.quantity), 0);
  const totalPrev = roots.reduce((s, r) => s + Number(r.previous_quantity), 0);
  const cost = roots.reduce((s, r) => s + Number(r.cost), 0);
  const unit = res?.unit ?? "";

  // Расход по дням: дочерние счётчики первого ввода стопкой и небаланс сверху.
  const days = daysBetween(dateFrom, dateTo);
  const byMeterDay = new Map<string, number>();
  for (const p of daily.data ?? []) byMeterDay.set(`${p.meter_id}|${p.day}`, Number(p.quantity));
  const root = roots[0];
  const children = root ? rows.filter((r) => r.parent_id === root.meter_id) : [];
  const value = (id: string, d: string) => byMeterDay.get(`${id}|${d}`) ?? 0;
  const series = root
    ? children.length
      ? [
          ...children.map((c, i) => ({ name: c.name, color: COLORS[i % COLORS.length], values: days.map((d) => value(c.meter_id, d)) })),
          {
            name: "Небаланс",
            color: "#c53030",
            values: days.map((d) => Math.max(0, value(root.meter_id, d) - children.reduce((s, c) => s + value(c.meter_id, d), 0))),
          },
        ]
      : [{ name: root.name, color: COLORS[0], values: days.map((d) => value(root.meter_id, d)) }]
    : [];
  const imbalanceDays = root && children.length
    ? days.filter((d) => {
        const v = value(root.meter_id, d);
        const k = children.reduce((s, c) => s + value(c.meter_id, d), 0);
        return v > 0 && (v - k) / v > 0.05;
      }).length
    : 0;

  // Профиль: электроэнергия — мощность кВт (кВт·ч за 30 мин × 2), прочее — расход за интервал.
  const power = resource === "el";
  const profileValues = (profile.data?.values ?? []).map((v) => Number(v) * (power ? 2 : 1));
  const offShift = profileValues.filter((_, s) => !isWorkSlot(s));
  const base = profileValues.length && offShift.length ? Math.min(...offShift) : undefined;
  const nightShare = profile.data && Number(profile.data.total) > 0
    ? (profile.data.values.filter((_, s) => !isWorkSlot(s)).reduce((a, v) => a + Number(v), 0) / Number(profile.data.total)) * 100
    : 0;

  const monthRows = monthly.data ?? [];
  const lastScada = scada.data?.[0];

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold">Энергоучёт</h1>
        <NativeSelect
          aria-label="Ресурс"
          className="w-52"
          value={resource}
          onChange={(e) => {
            setResource(e.target.value);
            setSelected(null);
          }}
        >
          {resources.data?.items.map((r) => (
            <option key={r.code} value={r.code}>
              {r.name}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect aria-label="Период" className="w-32" value={period} onChange={(e) => setPeriod(Number(e.target.value))}>
          {PERIODS.map((p) => (
            <option key={p} value={p}>
              {p} дней
            </option>
          ))}
        </NativeSelect>
        <span className="flex-1" />
        <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs text-blue-900">
          {lastScada
            ? `SCADA ${lastScada.source_id} · последний пакет ${formatDateTime(lastScada.created_at)} · принято ${lastScada.items_accepted}, отклонено ${lastScada.items_rejected}`
            : "Пакетов SCADA ещё не было"}
        </span>
        {resources.data?.abilities.can_manage_meters && (
          <Button size="sm" variant="outline" onClick={() => setReadingsOpen(true)}>
            Внести показания вручную
          </Button>
        )}
      </div>

      <KpiRow>
        <Kpi value={`${n0(total)} ${unit}`} label={`${res?.name.toLowerCase() ?? ""} за ${period} дн.`} />
        <Kpi
          value={totalPrev ? `${total > totalPrev ? "+" : ""}${Math.round((total / totalPrev - 1) * 100)}%` : "—"}
          label="к предыдущему периоду"
          tone={totalPrev && total > totalPrev * 1.05 ? "bad" : undefined}
        />
        <Kpi value={rub(cost)} label={`стоимость по тарифу ${res ? Number(res.tariff).toLocaleString("ru-RU") : "—"} ₽/${unit}`} />
        <Kpi value={imbalanceDays} label="суток с небалансом > 5%" tone={imbalanceDays ? "bad" : undefined} />
      </KpiRow>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Счётчики и балансы">
          <MeterTree rows={rows} unit={unit} selected={meterId} onSelect={setSelected} />
          <p className="mt-2 text-xs text-muted-foreground">
            Небаланс узла = его показание минус сумма дочерних счётчиков (потери). Клик по строке — профиль этой точки учёта.
          </p>
        </Panel>
        <Panel title="Расход по дням">
          <div data-testid="daily-chart">
            <StackChart
              categories={days.map((d) => (period > 14 ? String(Number(d.slice(8))) : formatDate(d).slice(0, 5)))}
              series={series}
              height={260}
              width={600}
              showTotals={period <= 14}
            />
          </div>
        </Panel>
      </div>

      <Panel
        title={`Получасовой профиль: ${meter?.name ?? "—"}`}
        action={
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Input
              type="date"
              aria-label="Сутки профиля"
              className="w-40"
              value={day}
              max={yesterday()}
              onChange={(e) => e.target.value && setDay(e.target.value)}
            />
            {profile.data && (
              <span>
                сутки {n0(profile.data.total)} {unit} · вне рабочего времени {Math.round(nightShare)}%
              </span>
            )}
          </div>
        }
      >
        <div data-testid="profile-chart">
          <LineChart
            values={profileValues}
            unit={power ? "кВт" : `${unit}/30 мин`}
            shade={profileValues.map((_, s) => isWorkSlot(s) && !isWeekend(day))}
            base={power ? base : undefined}
          />
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          Голубая зона — рабочая смена 8:00–17:00. Интервал 30 минут — как в АИИС КУЭ; данные приходят из SCADA пакетами JSON.
        </p>
      </Panel>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="Расход по месяцам">
          <StackChart
            categories={monthRows.map((r) => monthShort(r.period))}
            series={[{ name: `${res?.name ?? ""}, ${unit}`, color: "#2f5bd3", values: monthRows.map((r) => Number(r.quantity)) }]}
            height={200}
            width={600}
          />
          <table className="mt-2 w-full text-sm">
            <tbody>
              {monthRows.map((r) => (
                <tr key={r.period} className="border-t">
                  <td className="py-1">{monthShort(r.period)}</td>
                  <td className="text-right tabular-nums">
                    {n0(r.quantity)} {unit}
                  </td>
                  <td className="text-right tabular-nums">{rub(r.cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <TariffsPanel resources={resources.data?.items ?? []} canManage={Boolean(resources.data?.abilities.can_manage_meters)} />
      </div>

      {resource === "el" && (
        <Panel title="Удельный расход оборудования">
          <table className="w-full text-sm" data-testid="specific-table">
            <thead className="text-xs text-muted-foreground">
              <tr className="text-left">
                <th className="py-1 font-medium">Оборудование</th>
                <th className="font-medium">Счётчик</th>
                <th className="text-right font-medium">кВт·ч</th>
                <th className="text-right font-medium">Машино-часы</th>
                <th className="text-right font-medium">кВт·ч / маш-ч</th>
                <th className="text-right font-medium">Стоимость</th>
              </tr>
            </thead>
            <tbody>
              {specific.data?.map((r) => (
                <tr key={r.meter_id} className="border-t">
                  <td className="py-1">
                    {r.equipment_name}
                    <div className="text-xs text-muted-foreground">{r.inventory_no}</div>
                  </td>
                  <td className="text-xs text-muted-foreground">{r.meter_code}</td>
                  <td className="text-right tabular-nums">{n0(r.energy)}</td>
                  <td className="text-right tabular-nums">{Number(r.machine_hours).toLocaleString("ru-RU")}</td>
                  <td className="text-right font-semibold tabular-nums">
                    {r.specific ? Number(r.specific).toLocaleString("ru-RU") : "—"}
                  </td>
                  <td className="text-right tabular-nums">{rub(r.cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-muted-foreground">
            Машино-часы — работа и наладка из журнала смен оборудования за тот же период.
          </p>
        </Panel>
      )}

      <Panel title="Журнал пакетов SCADA">
        {!scada.data || scada.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Пакетов ещё не было. SCADA передаёт получасовые интервалы на POST /api/v1/energy/intervals.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr className="text-left">
                <th className="py-1 font-medium">Принят</th>
                <th className="font-medium">Источник</th>
                <th className="font-medium">Сообщение</th>
                <th className="font-medium">Версия</th>
                <th className="text-right font-medium">Строк</th>
                <th className="text-right font-medium">Принято</th>
                <th className="text-right font-medium">Отклонено</th>
              </tr>
            </thead>
            <tbody>
              {scada.data.map((m) => (
                <tr key={m.message_id} className="border-t">
                  <td className="py-1">{formatDateTime(m.created_at)}</td>
                  <td>{m.source_id}</td>
                  <td className="text-xs text-muted-foreground">{m.message_id}</td>
                  <td>{m.schema_version}</td>
                  <td className="text-right tabular-nums">{m.items_total}</td>
                  <td className="text-right tabular-nums">{m.items_accepted}</td>
                  <td className={cn("text-right tabular-nums", m.items_rejected > 0 && "text-red-600")}>{m.items_rejected}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      {readingsOpen && <ReadingsDialog onClose={() => setReadingsOpen(false)} />}
    </div>
  );
}

function MeterTree({
  rows,
  unit,
  selected,
  onSelect,
}: {
  rows: MeterTreeRowOut[];
  unit: string;
  selected: string;
  onSelect: (id: string) => void;
}) {
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">Счётчиков этого ресурса нет.</p>;
  return (
    <div className="overflow-auto">
      <table className="w-full text-sm" data-testid="meter-tree">
        <thead className="text-xs text-muted-foreground">
          <tr className="text-left">
            <th className="py-1 font-medium">Точка учёта</th>
            <th className="font-medium">Источник</th>
            <th className="text-right font-medium">{unit}</th>
            <th className="text-right font-medium">Доля</th>
            <th className="text-right font-medium">К пред.</th>
            <th className="text-right font-medium">Стоимость</th>
            <th className="text-right font-medium">Потери</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const q = Number(r.quantity);
            const p = Number(r.previous_quantity);
            const change = p ? (q / p - 1) * 100 : null;
            const loss = r.balance?.loss_pct !== null && r.balance?.loss_pct !== undefined ? Number(r.balance.loss_pct) : null;
            return (
              <tr
                key={r.meter_id}
                className={cn("cursor-pointer border-t hover:bg-muted/40", r.meter_id === selected && "bg-blue-50")}
                onClick={() => onSelect(r.meter_id)}
              >
                <td className="py-1" style={{ paddingLeft: 4 + r.level * 18 }}>
                  {r.balance ? "▾ " : ""}
                  {r.name}
                  <div className="text-xs text-muted-foreground">
                    {r.code} · {KIND_LABELS[r.kind] ?? r.kind}
                  </div>
                </td>
                <td>
                  <span
                    className={cn(
                      "rounded px-1.5 py-0.5 text-xs",
                      r.source === "scada" ? "bg-blue-100 text-blue-900" : "bg-muted",
                    )}
                  >
                    {r.source === "scada" ? "SCADA" : "вручную"}
                  </span>
                </td>
                <td className="text-right font-semibold tabular-nums">{n0(r.quantity)}</td>
                <td className="text-right tabular-nums">{r.share_pct !== null ? `${Math.round(Number(r.share_pct))}%` : "—"}</td>
                <td
                  className={cn(
                    "text-right tabular-nums",
                    change !== null && change > 5 && "text-red-600",
                    change !== null && change < -5 && "text-emerald-600",
                  )}
                >
                  {change === null ? "—" : `${change > 0 ? "+" : ""}${Math.round(change)}%`}
                </td>
                <td className="text-right tabular-nums">{rub(r.cost)}</td>
                <td
                  className={cn("text-right tabular-nums", loss !== null && Math.abs(loss) > 5 ? "text-red-600" : "text-muted-foreground")}
                  title={r.balance ? `Ввод ${n0(r.balance.input)} − дочерние ${n0(r.balance.children)} = ${n0(r.balance.loss)} ${unit}` : undefined}
                >
                  {r.balance ? `${n0(r.balance.loss)} · ${loss !== null ? `${loss.toLocaleString("ru-RU")}%` : "—"}` : ""}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function TariffsPanel({ resources, canManage }: { resources: ResourceOut[]; canManage: boolean }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ resource_id: "", valid_from: yesterday(), tariff: "" });
  const [saving, setSaving] = useState(false);
  const resourceId = form.resource_id || resources[0]?.id || "";

  async function submit() {
    const tariff = parseDecimalInput(form.tariff);
    if (tariff === null) {
      toast.error("Введите тариф числом.");
      return;
    }
    setSaving(true);
    try {
      await setEnergyTariff(resourceId, { valid_from: form.valid_from, tariff });
      toast.success("Тариф сохранён");
      setForm((f) => ({ ...f, tariff: "" }));
      await queryClient.invalidateQueries({
        predicate: (q) => typeof q.queryKey[0] === "string" && q.queryKey[0].startsWith("/api/v1/energy"),
      });
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Не удалось сохранить тариф.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Panel title="Ресурсы и тарифы">
      <table className="w-full text-sm">
        <thead className="text-xs text-muted-foreground">
          <tr className="text-left">
            <th className="py-1 font-medium">Ресурс</th>
            <th className="font-medium">Ед.</th>
            <th className="text-right font-medium">Тариф, ₽</th>
            <th className="pl-3 font-medium">История</th>
          </tr>
        </thead>
        <tbody>
          {resources.map((r) => (
            <tr key={r.id} className="border-t align-top">
              <td className="py-1">{r.name}</td>
              <td>{r.unit}</td>
              <td className="text-right tabular-nums">{Number(r.tariff).toLocaleString("ru-RU")}</td>
              <td className="pl-3 text-xs text-muted-foreground">
                {r.tariff_periods.length
                  ? r.tariff_periods.map((p) => `с ${formatDate(p.valid_from)}: ${Number(p.tariff).toLocaleString("ru-RU")}`).join(" · ")
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {canManage && (
        <div className="mt-3 grid grid-cols-[1fr_auto_auto_auto] items-end gap-2">
          <NativeSelect
            aria-label="Ресурс тарифа"
            value={resourceId}
            onChange={(e) => setForm((f) => ({ ...f, resource_id: e.target.value }))}
          >
            {resources.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </NativeSelect>
          <Input
            type="date"
            aria-label="Действует с"
            className="w-40"
            value={form.valid_from}
            onChange={(e) => setForm((f) => ({ ...f, valid_from: e.target.value }))}
          />
          <Input
            aria-label="Новый тариф"
            placeholder="₽ за единицу"
            inputMode="decimal"
            className="w-32"
            value={form.tariff}
            onChange={(e) => setForm((f) => ({ ...f, tariff: e.target.value }))}
          />
          <Button size="sm" disabled={saving || !form.tariff} onClick={submit}>
            Установить
          </Button>
        </div>
      )}
    </Panel>
  );
}
