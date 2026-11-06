"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { DataTable } from "@/components/data-table/data-table";
import { exportRowsToExcel } from "@/components/data-table/export-excel";
import { useKnownTotal } from "@/components/data-table/use-known-total";
import { useTableUrlState } from "@/components/data-table/use-table-url-state";
import { EntityForm } from "@/components/entity-form/entity-form";
import { listParties, useCreateParty, useListParties, type ListPartiesParams } from "@/lib/api/endpoints";
import { CreatePartyBody } from "@/lib/api/schemas";
import { ApiError } from "@/lib/api/mutator";
import { toast } from "sonner";

import { PARTY_STATUS_LABELS, PARTY_TYPE_LABELS, partyColumns } from "./columns";
import { PartiesToolbar } from "./parties-toolbar";

const EXPORT_PAGE_SIZE = 100;
const EXPORT_ROW_LIMIT = 5000;

export function PartiesView() {
  const urlState = useTableUrlState("", 20);
  const queryClient = useQueryClient();
  const router = useRouter();
  const [isExporting, setIsExporting] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  const params: ListPartiesParams = {
    search: urlState.search || undefined,
    status: (urlState.filters.status as ListPartiesParams["status"]) || undefined,
    party_type: (urlState.filters.party_type as ListPartiesParams["party_type"]) || undefined,
    cursor: urlState.cursor || undefined,
    page_size: urlState.pageSize,
    ordering: urlState.ordering || undefined,
    // Точный total считается по явному запросу, не на каждой странице — только на
    // первой странице текущего фильтра/сортировки (cursor ещё не назначен).
    with_total: !urlState.cursor,
  };

  const query = useListParties(params, { query: { placeholderData: (prev) => prev } });
  const { total, totalCap } = useKnownTotal(query.data);

  const createParty = useCreateParty({
    mutation: {
      meta: { skipGlobalErrorToast: true },
      onSuccess: () => {
        toast.success("Контрагент создан.");
        setCreateOpen(false);
        queryClient.invalidateQueries({ queryKey: ["/api/v1/identity/parties"] });
      },
    },
  });

  async function handleExport() {
    setIsExporting(true);
    try {
      const rows: Record<string, string>[] = [];
      let cursor: string | null | undefined;
      do {
        const page = await listParties({ ...params, cursor: cursor ?? undefined, page_size: EXPORT_PAGE_SIZE });
        for (const party of page.items) {
          rows.push({
            short_name: party.short_name,
            inn: party.inn,
            party_type: PARTY_TYPE_LABELS[party.party_type] ?? party.party_type,
            status: PARTY_STATUS_LABELS[party.status] ?? party.status,
            created_at: party.created_at,
          });
        }
        cursor = page.next_cursor;
      } while (cursor && rows.length < EXPORT_ROW_LIMIT);

      await exportRowsToExcel(
        "kontragenty",
        [
          { key: "short_name", label: "Наименование", width: 32 },
          { key: "inn", label: "ИНН", width: 16 },
          { key: "party_type", label: "Тип", width: 16 },
          { key: "status", label: "Статус", width: 16 },
          { key: "created_at", label: "Создан", width: 20 },
        ],
        rows,
      );
    } catch {
      toast.error("Не удалось выполнить экспорт.");
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Контрагенты</h1>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="size-4" aria-hidden />
          Создать
        </Button>
      </div>

      <DataTable
        columns={partyColumns}
        data={query.data?.items ?? []}
        rowId={(party) => party.id}
        isLoading={query.isLoading}
        isFetching={query.isFetching}
        nextCursor={query.data?.next_cursor}
        total={total}
        totalCap={totalCap}
        urlState={urlState}
        toolbar={<PartiesToolbar urlState={urlState} />}
        onRowActivate={(party) => router.push(`/parties/${party.id}`)}
        onExport={handleExport}
        isExporting={isExporting}
        emptyMessage="Контрагенты не найдены."
      />

      <Sheet open={createOpen} onOpenChange={setCreateOpen}>
        <SheetContent className="w-full sm:max-w-md">
          <SheetHeader>
            <SheetTitle>Новый контрагент</SheetTitle>
          </SheetHeader>
          <div className="px-4">
            <EntityForm
              schema={CreatePartyBody}
              draftKey="parties:new"
              defaultValues={{
                short_name: "",
                legal_name: "",
                inn: "",
                kpp: "",
                party_type: "legal" as const,
                force: false,
              }}
              fields={[
                { type: "text", name: "short_name", label: "Краткое наименование", autoFocus: true },
                { type: "text", name: "legal_name", label: "Полное наименование" },
                { type: "text", name: "inn", label: "ИНН" },
                { type: "text", name: "kpp", label: "КПП" },
                {
                  type: "select",
                  name: "party_type",
                  label: "Тип контрагента",
                  options: Object.entries(PARTY_TYPE_LABELS).map(([value, label]) => ({ value, label })),
                },
              ]}
              onSubmit={async (values) => {
                await createParty.mutateAsync({ data: values });
              }}
              onDomainError={(error: ApiError) => {
                if (error.code === "duplicates_found") {
                  toast.warning("Найдены похожие контрагенты", {
                    description: "Проверьте список перед повторной попыткой.",
                  });
                } else {
                  toast.error(error.message);
                }
              }}
              submitLabel="Создать"
            />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
