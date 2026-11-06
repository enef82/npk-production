"use client";

import { StackChart } from "@/components/charts/stack-chart";
import { useCards } from "@/components/production/card-host";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useGetAnalyticsPortfolio, type AnalyticsMonthLoadOut, type AnalyticsPortfolioOut } from "@/lib/api/endpoints";
import { heatColor, monthLabel } from "@/lib/analytics/format";
import { krub, num, qty } from "@/lib/production/format";
import { cn } from "@/lib/utils";

const FACT = "#6b7a99";
const FIRM = "#2f5bd3";
const PIPE = "#9fb4ea";

const shortMoney = (v: number) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)}м` : `${Math.round(v / 1e3)}т`);
const nh = (v: number) => (v >= 1 ? Math.round(v).toLocaleString("ru-RU") : "—");

/** Экран «Портфель» (`renderPortfolio` прототипа): выручка и загрузка по месяцам. */
export function PortfolioView() {
  const query = useGetAnalyticsPortfolio();
  const data = query.data;
  if (!data) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        {query.isError ? "Не удалось загрузить портфель." : "Загрузка…"}
      </div>
    );
  }
  const hl = data.months.indexOf(data.current_month);
  const labels = data.months.map(monthLabel);
  const { hot, free } = notes(data, hl);

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto p-4 [&>*]:shrink-0">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-lg font-semibold">Портфель заказов и план загрузки по месяцам</h1>
        <div className="flex flex-wrap gap-2 text-xs" data-testid="portfolio-probabilities">
          {data.probabilities.map((p) => (
            <Badge key={p.stage} variant="outline">
              {p.label}: {Math.round(num(p.probability))}%
            </Badge>
          ))}
        </div>
      </div>
      <p className="-mt-2 text-xs text-muted-foreground">
        Твёрдые заказы — по текущему плану; заявки — с весом вероятности по этапу (вероятности — в настройках заявок);
        заявка без плана — по требуемому сроку, в загрузку не входит. Прошлые месяцы — факт освоения (закрытые недели —
        по отсечкам) и отгрузок.
      </p>
      {hot.length > 0 && (
        <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">
          <b>Перегрузка:</b> {hot.slice(0, 8).join(" · ")}
        </div>
      )}
      {free.length > 0 && (
        <div className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">
          <b>Есть свободная мощность — можно брать заказы:</b> {free.join(" · ")}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border p-3" data-testid="portfolio-revenue">
          <h2 className="mb-2 font-semibold">Портфель по месяцам отгрузки, ₽ с НДС</h2>
          <StackChart
            categories={labels}
            highlight={hl}
            format={shortMoney}
            series={[
              { name: "Отгружено (факт)", color: FACT, values: data.revenue.map((m) => num(m.fact)) },
              { name: "Заказы в работе", color: FIRM, values: data.revenue.map((m) => num(m.firm)) },
              { name: "Воронка (взвешенно)", color: PIPE, values: data.revenue.map((m) => num(m.pipe)) },
            ]}
          />
        </section>
        <section className="rounded-lg border p-3" data-testid="portfolio-load">
          <h2 className="mb-2 font-semibold">Загрузка производства, н-ч</h2>
          <StackChart
            categories={labels}
            highlight={hl}
            series={[
              { name: "Факт (освоено)", color: FACT, values: data.load.map((m) => num(m.fact)) },
              { name: "Заказы в работе", color: FIRM, values: data.load.map((m) => num(m.firm)) },
              { name: "Воронка (взвешенно)", color: PIPE, values: data.load.map((m) => num(m.pipe)) },
            ]}
            line={{ name: "Мощность", values: data.load.map((m) => num(m.capacity)) }}
          />
        </section>
      </div>

      <section className="overflow-x-auto rounded-lg border p-3">
        <h2 className="mb-2 font-semibold">Сводка</h2>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead />
              {labels.map((l, i) => (
                <TableHead key={l} className={cn("text-right", i === hl && "text-primary")}>
                  {l}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            <SumRow name="Отгружено (факт)" hl={hl} values={data.revenue.map((m) => krubOrDash(m.fact))} />
            <SumRow name="Заказы в работе" hl={hl} values={data.revenue.map((m) => krubOrDash(m.firm))} />
            <SumRow name="Воронка (взвешенно)" hl={hl} values={data.revenue.map((m) => krubOrDash(m.pipe))} />
            <SumRow name="Итого ожидается" bold hl={hl} values={data.revenue.map((m) => krubOrDash(m.total))} />
            <SumRow name="Загрузка, н-ч" hl={hl} values={data.load.map((m) => nh(num(m.total)))} />
            <SumRow name="Мощность, н-ч" hl={hl} values={data.load.map((m) => nh(num(m.capacity)))} />
            <TableRow className="font-semibold">
              <TableCell>Загрузка, %</TableCell>
              {data.load.map((m, i) => {
                const r = num(m.pct) / 100;
                return (
                  <TableCell
                    key={data.months[i]}
                    className={cn(
                      "text-right",
                      i === hl && "bg-primary/5",
                      r > 1 ? "text-destructive" : r > 0.85 ? "text-amber-700" : "",
                    )}
                  >
                    {m.pct === null ? "—" : `${Math.round(num(m.pct))}%`}
                  </TableCell>
                );
              })}
            </TableRow>
            <SumRow
              name="Свободно, н-ч"
              hl={hl}
              values={data.load.map((m) => nh(Math.max(0, num(m.capacity) - num(m.total))))}
            />
          </TableBody>
        </Table>
      </section>

      <section className="overflow-x-auto rounded-lg border p-3">
        <h2 className="mb-2 font-semibold">Загрузка участков по месяцам</h2>
        <Table data-testid="portfolio-centers">
          <TableHeader>
            <TableRow>
              <TableHead>Участок · загрузка от мощности</TableHead>
              {labels.map((l, i) => (
                <TableHead key={l} className={cn("text-center", i === hl && "text-primary")}>
                  {l}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.centers.map((c) => (
              <TableRow key={c.work_center_id}>
                <TableCell className="whitespace-nowrap">{c.name}</TableCell>
                {c.months.map((m, i) => (
                  <HeatCell key={data.months[i]} m={m} />
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>

      <Items data={data} />
    </div>
  );
}

function krubOrDash(v: string): string {
  return num(v) ? krub(v) : "—";
}

function SumRow({ name, values, hl, bold }: { name: string; values: string[]; hl: number; bold?: boolean }) {
  return (
    <TableRow className={cn(bold && "font-semibold")}>
      <TableCell>{name}</TableCell>
      {values.map((v, i) => (
        <TableCell key={i} className={cn("text-right tabular-nums", i === hl && "bg-primary/5")}>
          {v}
        </TableCell>
      ))}
    </TableRow>
  );
}

function HeatCell({ m }: { m: AnalyticsMonthLoadOut }) {
  const total = num(m.total);
  const ratio = num(m.capacity) ? total / num(m.capacity) : 0;
  return (
    <TableCell
      className="min-w-16 text-center tabular-nums"
      style={{ background: heatColor(ratio) }}
      title={`Факт ${Math.round(num(m.fact))} · заказы ${Math.round(num(m.firm))} · воронка ${Math.round(num(m.pipe))} · мощность ${Math.round(num(m.capacity))} н-ч`}
    >
      {total >= 1 ? `${Math.round(num(m.pct))}%` : ""}
      {num(m.pipe) >= 1 && (
        <div className="text-[10px] text-muted-foreground">в т.ч. воронка {Math.round(num(m.pipe_pct))}%</div>
      )}
    </TableCell>
  );
}

/** Узкие места и свободная мощность будущих месяцев (подсказки прототипа). */
function notes(data: AnalyticsPortfolioOut, hl: number): { hot: string[]; free: string[] } {
  const hot: string[] = [];
  const free: string[] = [];
  data.months.forEach((month, i) => {
    if (i < hl) return;
    data.centers.forEach((c) => {
      const m = c.months[i];
      if (num(m.capacity) && num(m.total) / num(m.capacity) > 1) {
        hot.push(`${c.name} — ${monthLabel(month)} ${Math.round(num(m.pct))}%`);
      }
    });
    const t = data.load[i];
    const ratio = num(t.capacity) ? num(t.total) / num(t.capacity) : 0;
    if (i > hl && ratio < 0.5) {
      free.push(
        `${monthLabel(month)}: свободно ~${Math.round(num(t.capacity) - num(t.total)).toLocaleString("ru-RU")} н-ч (${Math.round(100 - ratio * 100)}%)`,
      );
    }
  });
  return { hot, free };
}

function Items({ data }: { data: AnalyticsPortfolioOut }) {
  const cards = useCards();
  return (
    <section className="overflow-x-auto rounded-lg border p-3">
      <h2 className="mb-2 font-semibold">Заказы и заявки по месяцу отгрузки</h2>
      <Table data-testid="portfolio-items">
        <TableHeader>
          <TableRow>
            <TableHead>Месяц</TableHead>
            <TableHead>Номер</TableHead>
            <TableHead>Заказчик</TableHead>
            <TableHead>Изделие</TableHead>
            <TableHead>Этап</TableHead>
            <TableHead className="text-right">Сумма</TableHead>
            <TableHead className="text-right">Вероятн.</TableHead>
            <TableHead className="text-right">В портфель</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.items.map((item) => (
            <TableRow
              key={item.id}
              className="cursor-pointer"
              onClick={() => (item.is_order ? cards.openOrder(item.id) : cards.openInquiry(item.id))}
            >
              <TableCell>{monthLabel(item.month)}</TableCell>
              <TableCell className="font-medium">{item.number}</TableCell>
              <TableCell>{item.customer_name}</TableCell>
              <TableCell>
                {item.product_name} × {qty(item.quantity)}
              </TableCell>
              <TableCell>
                <Badge variant={item.is_order ? "secondary" : "outline"}>{item.stage_label}</Badge>
                {item.estimated && <span className="ml-1 text-xs text-muted-foreground">оценка</span>}
              </TableCell>
              <TableCell className="text-right tabular-nums">{krub(item.total)}</TableCell>
              <TableCell className="text-right tabular-nums">{Math.round(num(item.probability_pct))}%</TableCell>
              <TableCell className="text-right tabular-nums">{krub(item.weighted)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  );
}
