"""Pydantic-схемы входа и выхода API модуля «ОТК и качество»."""

from __future__ import annotations

import datetime as dt
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from ninja import Field, Schema

# --- Справочники ---


class DefectTypeOut(Schema):
    id: UUID
    name: str


class InspectionPointOut(Schema):
    id: UUID
    work_center_id: UUID
    work_center_name: str
    name: str
    is_final: bool
    defect_types: list[DefectTypeOut]


class DefectCauseOut(Schema):
    id: UUID
    name: str
    is_operator_fault: bool


class QualityReferenceOut(Schema):
    points: list[InspectionPointOut]
    causes: list[DefectCauseOut]


# --- Записи ---


class QcAggOut(Schema):
    checked: int
    rework: int
    scrap: int
    defects: int
    pct: Decimal


class InspectionRecordOut(Schema):
    id: UUID
    operation_id: UUID
    order_id: UUID
    work_center_id: UUID
    date: date
    inspector_id: UUID
    inspector_name: str
    checked: int
    rework: int
    scrap: int
    defect_type_id: UUID | None
    defect_type_name: str
    cause_id: UUID | None
    cause_name: str
    comment: str
    created_at: datetime


class JournalRecordOut(InspectionRecordOut):
    """Строка журнала записей экрана «Качество» — с заказом, операцией и участком."""

    order_number: str
    customer_name: str
    operation_name: str
    work_center_name: str


class OperationQcAbilitiesOut(Schema):
    can_record: bool


class OperationQcOut(Schema):
    """Блок «Контроль качества» карточки операции (`opDialog` прототипа)."""

    operation_id: UUID
    order_id: UUID
    work_center_id: UUID
    point: InspectionPointOut | None
    # Запись разрешена этапом заказа (после запуска; входной контроль — с запуска).
    recording_open: bool
    default_checked: int
    aggregate: QcAggOut
    records: list[InspectionRecordOut]
    causes: list[DefectCauseOut]
    abilities: OperationQcAbilitiesOut


class InspectionIn(Schema):
    checked: int = Field(..., ge=1)
    rework: int = Field(0, ge=0)
    scrap: int = Field(0, ge=0)
    defect_type_id: UUID | None = None
    cause_id: UUID | None = None
    comment: str = ""
    # `dt.date`: поле `date` со значением по умолчанию затеняет имя типа в классе.
    date: dt.date | None = None


class InspectionCreatedOut(Schema):
    record: InspectionRecordOut
    # «Нужно повторное изготовление» — при списании (§3.3).
    warning: str


# --- Сводка ---


class QualityKpiOut(Schema):
    checked: int
    defects: int
    pct: Decimal
    rework: int
    scrap: int
    # Доля брака, выявленного до финального контроля, % — чем больше, тем дешевле.
    early_pct: Decimal
    # Доля брака по вине оператора, %.
    operator_pct: Decimal


class TopDefectOut(Schema):
    name: str
    defects: int


class WorkCenterQcOut(Schema):
    work_center_id: UUID
    work_center_name: str
    point_name: str
    is_final: bool
    checked: int
    defects: int
    pct: Decimal
    rework: int
    scrap: int
    top_defect: TopDefectOut | None
    # Изменение доли брака второй половины периода к первой, п.п.
    trend: Decimal


class WeekQcOut(Schema):
    week_start: date
    checked: int
    intermediate_defects: int
    final_defects: int
    pct: Decimal


class QualityParetoOut(Schema):
    name: str
    defects: int
    cumulative_pct: Decimal


class QualitySummaryOut(Schema):
    date_from: date
    date_to: date
    weeks: int
    kpi: QualityKpiOut
    by_work_center: list[WorkCenterQcOut]
    # Динамика за 12 недель — независимо от выбранного периода.
    dynamics: list[WeekQcOut]
    pareto_causes: list[QualityParetoOut]
    pareto_defect_types: list[QualityParetoOut]
