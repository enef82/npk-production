"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { OptionSelect } from "@/components/option-select/option-select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  useGetOperationQc,
  useGetQualityReference,
  useRecordInspection,
  type OperationQcOut,
} from "@/lib/api/endpoints";
import { formatDate } from "@/lib/format/ru";

/**
 * Блок «Контроль качества» карточки операции (`opDialog` прототипа): точка контроля
 * участка, агрегат, записи и форма записи результата. `canRecord` — дополнительное
 * ограничение от карточки (например, только чтение); право записи всё равно решает
 * сервер (`abilities.can_record`). Без точки контроля у участка операцию запрос записей
 * не делается.
 */
export function OperationQcPanel({
  operationId,
  workCenterId,
  canRecord,
}: {
  operationId: string;
  workCenterId: string;
  canRecord?: boolean;
}) {
  const reference = useGetQualityReference();
  const hasPoint = reference.data ? reference.data.points.some((p) => p.work_center_id === workCenterId) : undefined;
  const query = useGetOperationQc(operationId, { query: { enabled: hasPoint === true } });

  if (hasPoint === false) {
    return (
      <section className="flex flex-col gap-2" data-testid="operation-qc">
        <h3 className="font-semibold">Контроль качества</h3>
        <p className="text-sm text-muted-foreground">Для этого участка точка контроля не предусмотрена.</p>
      </section>
    );
  }
  if (!query.data) {
    return (
      <section className="flex flex-col gap-2" data-testid="operation-qc">
        <h3 className="font-semibold">Контроль качества</h3>
        <p className="text-sm text-muted-foreground">{query.isError ? "Не удалось загрузить контроль." : "Загрузка…"}</p>
      </section>
    );
  }
  return <Panel data={query.data} allowed={(canRecord ?? true) && query.data.abilities.can_record} />;
}

function Panel({ data, allowed }: { data: OperationQcOut; allowed: boolean }) {
  const point = data.point;
  const agg = data.aggregate;
  return (
    <section className="flex flex-col gap-3" data-testid="operation-qc">
      <h3 className="font-semibold">Контроль качества</h3>
      {point && (
        <div className="flex flex-wrap items-center gap-2">
          <b>{point.name}</b>
          <Badge variant={point.is_final ? "secondary" : "outline"}>{point.is_final ? "финальный" : "промежуточный"}</Badge>
        </div>
      )}
      <p className="text-sm text-muted-foreground">
        Проверено {agg.checked} · брак {agg.defects} ({agg.pct}%) · доработка {agg.rework} · списание {agg.scrap}
      </p>
      {data.records.length ? (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Дата</TableHead>
                <TableHead>Контролёр</TableHead>
                <TableHead className="text-right">Пров.</TableHead>
                <TableHead className="text-right">Дораб.</TableHead>
                <TableHead className="text-right">Спис.</TableHead>
                <TableHead>Дефект / причина</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.records.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>{formatDate(r.date)}</TableCell>
                  <TableCell>{r.inspector_name}</TableCell>
                  <TableCell className="text-right">{r.checked}</TableCell>
                  <TableCell className={r.rework ? "text-right font-semibold text-amber-700" : "text-right"}>
                    {r.rework}
                  </TableCell>
                  <TableCell className={r.scrap ? "text-right font-semibold text-destructive" : "text-right"}>
                    {r.scrap}
                  </TableCell>
                  <TableCell className="whitespace-normal">
                    {r.rework + r.scrap ? (
                      <>
                        {r.defect_type_name}
                        <div className="text-xs text-muted-foreground">
                          {r.cause_name}
                          {r.comment && ` · ${r.comment}`}
                        </div>
                      </>
                    ) : (
                      <span className="text-xs text-muted-foreground">годно{r.comment && ` · ${r.comment}`}</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-200">
          Записей контроля нет. Без записи операцию нельзя завизировать.
        </p>
      )}
      {allowed ? (
        <RecordForm data={data} />
      ) : !data.recording_open ? (
        <p className="text-xs text-muted-foreground">Запись результатов доступна после запуска заказа в производство.</p>
      ) : null}
    </section>
  );
}

function RecordForm({ data }: { data: OperationQcOut }) {
  const queryClient = useQueryClient();
  const [checked, setChecked] = useState(String(data.default_checked));
  const [rework, setRework] = useState("0");
  const [scrap, setScrap] = useState("0");
  const [defectType, setDefectType] = useState("");
  const [cause, setCause] = useState("");
  const [comment, setComment] = useState("");
  const record = useRecordInspection({
    mutation: {
      onSuccess: (result) => {
        toast.success("Результат контроля записан");
        if (result.warning) toast.warning(result.warning);
        setRework("0");
        setScrap("0");
        setDefectType("");
        setCause("");
        setComment("");
        // Запись меняет и блок контроля, и карточку операции (виза требует записи), и журнал.
        void queryClient.invalidateQueries({
          predicate: (q) => {
            const key = q.queryKey[0];
            return typeof key === "string" && (key.startsWith("/api/v1/quality") || key.startsWith("/api/v1/production"));
          },
        });
      },
    },
  });

  const defects = (Number(rework) || 0) + (Number(scrap) || 0);
  return (
    <form
      className="grid grid-cols-2 gap-2 rounded-md border p-3 md:grid-cols-3"
      onSubmit={(e) => {
        e.preventDefault();
        const chk = Number(checked) || 0;
        if (chk < 1) return void toast.error("Укажите количество проверенных.");
        if (defects > chk) return void toast.error("Брака больше, чем проверено.");
        if (defects && (!defectType || !cause)) return void toast.error("Для брака укажите вид дефекта и причину.");
        record.mutate({
          operationId: data.operation_id,
          data: {
            checked: chk,
            rework: Number(rework) || 0,
            scrap: Number(scrap) || 0,
            defect_type_id: defects ? defectType : null,
            cause_id: defects ? cause : null,
            comment,
          },
        });
      }}
    >
      <div className="flex flex-col gap-1">
        <Label htmlFor="qc-checked">Проверено, шт.</Label>
        <Input id="qc-checked" type="number" min="1" step="1" value={checked} onChange={(e) => setChecked(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="qc-rework">Брак: доработка</Label>
        <Input id="qc-rework" type="number" min="0" step="1" value={rework} onChange={(e) => setRework(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="qc-scrap">Брак: списание</Label>
        <Input id="qc-scrap" type="number" min="0" step="1" value={scrap} onChange={(e) => setScrap(e.target.value)} />
      </div>
      <div className="flex flex-col gap-1">
        <Label>Вид дефекта</Label>
        <OptionSelect
          ariaLabel="Вид дефекта"
          className="w-full"
          value={defectType}
          onChange={setDefectType}
          emptyLabel="—"
          options={(data.point?.defect_types ?? []).map((t) => ({ value: t.id, label: t.name }))}
        />
      </div>
      <div className="flex flex-col gap-1">
        <Label>Причина</Label>
        <OptionSelect
          ariaLabel="Причина брака"
          className="w-full"
          value={cause}
          onChange={setCause}
          emptyLabel="—"
          options={data.causes.map((c) => ({ value: c.id, label: c.name }))}
        />
      </div>
      <div className="flex items-end">
        <Button type="submit" className="w-full" disabled={record.isPending}>
          Записать
        </Button>
      </div>
      <Input
        className="col-span-full"
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="Комментарий: что выявлено, что сделано"
        aria-label="Комментарий к записи контроля"
      />
    </form>
  );
}
