"use client";

import { notFound } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EntityCard, type EntityCardTab } from "@/components/entity-card/entity-card";
import { EntityCardEmptyBlock } from "@/components/entity-card/empty-block";
import { useDynamicBreadcrumbLabel } from "@/components/layout/breadcrumb-labels";
import { useGetParty, useGetPartyProfiles } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/mutator";
import { formatDateTime } from "@/lib/format/ru";
import { PARTY_STATUS_LABELS, PARTY_TYPE_LABELS } from "../columns";

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm">{value || "—"}</dd>
    </div>
  );
}

export function PartyCardView({ partyId }: { partyId: string }) {
  const partyQuery = useGetParty(partyId, {
    query: { retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2 },
  });
  const profilesQuery = useGetPartyProfiles(partyId, { query: { enabled: !!partyQuery.data } });

  useDynamicBreadcrumbLabel(partyId, partyQuery.data?.short_name);

  if (partyQuery.isError && partyQuery.error instanceof ApiError && partyQuery.error.status === 404) {
    notFound();
  }

  if (partyQuery.isLoading || !partyQuery.data) {
    return (
      <div className="flex flex-col gap-4 p-6">
        <Skeleton className="h-7 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  const party = partyQuery.data;
  const profiles = profilesQuery.data ?? {};
  const profileEntries = Object.entries(profiles);

  const tabs: EntityCardTab[] = [
    {
      value: "overview",
      label: "Обзор",
      content: (
        <dl className="grid max-w-2xl grid-cols-2 gap-4">
          <Field label="Краткое наименование" value={party.short_name} />
          <Field label="Полное наименование" value={party.legal_name} />
          <Field label="ИНН" value={party.inn} />
          <Field label="КПП" value={party.kpp} />
          <Field label="Тип" value={PARTY_TYPE_LABELS[party.party_type] ?? party.party_type} />
          <Field label="Статус" value={PARTY_STATUS_LABELS[party.status] ?? party.status} />
          <Field label="Создан" value={formatDateTime(party.created_at)} />
          <Field label="Изменён" value={formatDateTime(party.updated_at)} />
        </dl>
      ),
    },
    {
      value: "profiles",
      label: `Профили${profileEntries.length ? ` (${profileEntries.length})` : ""}`,
      content: profilesQuery.isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : profileEntries.length === 0 ? (
        <EntityCardEmptyBlock
          title="Профилей пока нет"
          description="Появятся, когда контрагента впервые затронет модуль (закупки, продажи и т.д.)."
        />
      ) : (
        <div className="flex flex-col gap-4">
          {profileEntries.map(([module, profile]) => (
            <div key={module} className="rounded-md border p-4">
              <h3 className="mb-3 text-sm font-medium">{profile.title}</h3>
              {Object.keys(profile.attributes).length === 0 ? (
                <p className="text-sm text-muted-foreground">Атрибуты не заполнены.</p>
              ) : (
                <dl className="grid grid-cols-2 gap-3">
                  {Object.entries(profile.attributes).map(([key, value]) => (
                    <Field key={key} label={key} value={String(value)} />
                  ))}
                </dl>
              )}
            </div>
          ))}
        </div>
      ),
    },
    {
      value: "documents",
      label: "Документы",
      content: (
        <EntityCardEmptyBlock
          title="Документы появятся на следующих шагах"
          description="core.documents ещё не подключён к карточке контрагента."
        />
      ),
    },
    {
      value: "approvals",
      label: "Согласования",
      content: (
        <EntityCardEmptyBlock
          title="Согласования появятся на следующих шагах"
          description="core.approvals ещё не подключён к карточке контрагента."
        />
      ),
    },
  ];

  return (
    <EntityCard
      title={party.short_name}
      subtitle={party.legal_name}
      badges={<Badge>{PARTY_STATUS_LABELS[party.status] ?? party.status}</Badge>}
      tabs={tabs}
      sidePanel={
        <dl className="flex flex-col gap-4">
          <Field label="ИНН" value={party.inn} />
          <Field label="Тип" value={PARTY_TYPE_LABELS[party.party_type] ?? party.party_type} />
          <Field label="Создан" value={formatDateTime(party.created_at)} />
        </dl>
      }
    />
  );
}
