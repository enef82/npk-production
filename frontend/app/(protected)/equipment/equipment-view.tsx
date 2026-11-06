"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useListTimesheetWorkers, useListWorkCenters } from "@/lib/api/endpoints";

import { MachineSheet } from "./machine-sheet";
import { MachinesTab } from "./machines-tab";
import { RepairDialog, type RepairDraft } from "./repair-dialog";
import { RepairsPanel } from "./repairs-panel";

/** После любого действия — перечитать всё оборудование и журнал ремонтов (и табель:
 * закрытый ремонт переносит часы исполнителей в разноску). */
export function useInvalidateEquipment(): () => Promise<void> {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({
      predicate: (q) =>
        typeof q.queryKey[0] === "string" &&
        (q.queryKey[0].startsWith("/api/v1/equipment") || q.queryKey[0].startsWith("/api/v1/timesheet/departments")),
    });
  };
}

/** Подписи участков и сотрудников: модуль `equipment` хранит только их UUID (И2). */
export function useNames() {
  const centers = useListWorkCenters({ query: { staleTime: 5 * 60_000 } });
  const workers = useListTimesheetWorkers({ query: { staleTime: 5 * 60_000 } });
  return {
    workCenter: new Map(centers.data?.map((c) => [c.id, c]) ?? []),
    workers: workers.data ?? [],
  };
}

export function EquipmentView() {
  const [machineId, setMachineId] = useState<string | null>(null);
  const [repair, setRepair] = useState<RepairDraft | null>(null);

  return (
    <div className="flex flex-col gap-4 p-4">
      <h1 className="text-lg font-semibold">Оборудование</h1>
      <Tabs defaultValue="machines">
        <TabsList>
          <TabsTrigger value="machines">Оборудование и ТО</TabsTrigger>
          <TabsTrigger value="repairs">Аварии и ремонты</TabsTrigger>
        </TabsList>
        <TabsContent value="machines" className="pt-2">
          <MachinesTab onOpenMachine={setMachineId} />
        </TabsContent>
        <TabsContent value="repairs" className="pt-2">
          <RepairsPanel onOpenRepair={setRepair} />
        </TabsContent>
      </Tabs>

      <MachineSheet machineId={machineId} onClose={() => setMachineId(null)} onOpenRepair={setRepair} />
      {repair && <RepairDialog draft={repair} onClose={() => setRepair(null)} />}
    </div>
  );
}
