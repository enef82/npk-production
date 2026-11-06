"""Эндпоинты django-ninja модуля «Производство» (`docs/spec/00-prilozhenie-proizvodstvo.md`
§4, §6).

Права проверяются здесь, сервисы их не проверяют (как в ИС). Каждая карточка отдаёт
серверные `abilities`, посчитанные теми же функциями, что и проверки эндпоинтов, —
кнопка на фронте и запрет в API не могут разойтись.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any
from uuid import UUID

from django.http import Http404, HttpRequest
from ninja import File, Form, Router
from ninja.files import UploadedFile

from src.core.accounts.models import User
from src.core.common.exceptions import PermissionDenied
from src.production import facade, rules, selectors
from src.production.exceptions import ActorNotEmployee
from src.production.models import JournalKind, OperationStatus, OrderStage
from src.production.selectors import WORK_STAGES, OperationRow, OrderCard
from src.production.services import documents as document_services
from src.production.services import journal as journal_services
from src.production.services import operation as operation_services
from src.production.services import order as order_services
from src.quality import facade as quality

from .schemas import (
    BoardAbilitiesOut,
    CommentIn,
    CreatedOut,
    DocumentKindOut,
    DocumentOut,
    GanttOrderOut,
    JournalEntryOut,
    OperationAbilitiesOut,
    OperationApproveIn,
    OperationCardOut,
    OperationMoveIn,
    OperationProgressIn,
    OperationStatusIn,
    OperationUpdateIn,
    OrderAbilitiesOut,
    OrderCardOut,
    OrderOut,
    OrderUpdateIn,
    PredecessorsIn,
    ProductionSettingsOut,
    ReplanIn,
    ScheduleOut,
    ShiftIn,
    StageApproveIn,
    StageMoveIn,
    StageResponsibleIn,
    TemplateListItem,
    TemplateOut,
    VisaItemOut,
    WorkCenterOut,
)

router = Router(tags=["production"])


class AuthenticatedHttpRequest(HttpRequest):
    auth: User


def _employee(request: AuthenticatedHttpRequest) -> UUID | None:
    return rules.employee_id_of(request.auth)


def _require_employee(request: AuthenticatedHttpRequest) -> UUID:
    employee_id = _employee(request)
    if employee_id is None:
        raise ActorNotEmployee
    return employee_id


# --- Способности -------------------------------------------------------------------


def _board_abilities(user: User, card: OrderCard) -> BoardAbilitiesOut:
    me = rules.employee_id_of(user)
    is_responsible = me is not None and me == card.stage_responsible_id
    return BoardAbilitiesOut(
        can_move=bool(
            rules.can_manage_orders(user)
            or (me is not None and me == card.manager_id)
            or is_responsible
        ),
        can_approve_stage=(
            card.stage != OrderStage.DONE
            and not card.stage_approved
            and bool(is_responsible or rules.can_approve_any(user))
        ),
    )


def _order_abilities(user: User, card: OrderCard) -> OrderAbilitiesOut:
    board = _board_abilities(user, card)
    open_order = card.stage != OrderStage.DONE
    return OrderAbilitiesOut(
        can_move=board.can_move,
        can_approve_stage=board.can_approve_stage,
        can_edit=open_order and bool(rules.can_manage_orders(user)),
        can_plan=open_order and bool(rules.can_plan_operations(user)),
        can_manage_documents=bool(rules.can_manage_documents(user)),
        can_comment=rules.employee_id_of(user) is not None,
    )


def _operation_abilities(user: User, row: OperationRow, order_stage: str) -> OperationAbilitiesOut:
    me = rules.employee_id_of(user)
    is_responsible = me is not None and me == row.responsible_id
    in_work = order_stage in WORK_STAGES
    can_work = (
        in_work
        and row.status != OperationStatus.DONE
        and bool(is_responsible or rules.can_plan_operations(user))
    )
    can_plan = order_stage != OrderStage.DONE and bool(rules.can_plan_operations(user))
    return OperationAbilitiesOut(
        can_change_status=can_work,
        can_set_progress=can_work and row.status == OperationStatus.WORK and not row.is_supply,
        can_approve=(
            in_work
            and row.status in (OperationStatus.WORK, OperationStatus.CHECK)
            and bool(is_responsible or rules.can_approve_any(user))
        ),
        can_edit_plan=can_plan and row.status == OperationStatus.WAIT,
        can_set_responsible=can_plan and row.status != OperationStatus.DONE,
    )


def _card_out(user: User, card: OrderCard) -> dict[str, Any]:
    return {**asdict(card), "abilities": _board_abilities(user, card)}


def _row_out(user: User, row: OperationRow, order_stage: str) -> dict[str, Any]:
    return {**asdict(row), "abilities": _operation_abilities(user, row, order_stage)}


def _order_out(user: User, order_id: UUID) -> dict[str, Any]:
    detail = selectors.get_order_detail(order_id)
    if detail is None:
        raise Http404
    return {
        **asdict(detail),
        "abilities": _board_abilities(user, detail),
        "order_abilities": _order_abilities(user, detail),
    }


def _card_or_404(order_id: UUID) -> OrderCard:
    detail = selectors.get_order_detail(order_id)
    if detail is None:
        raise Http404
    return detail


# --- Справочники -------------------------------------------------------------------


@router.get("/work-centers", response=list[WorkCenterOut], operation_id="listWorkCenters")
def list_work_centers(request: AuthenticatedHttpRequest) -> list[dict[str, Any]]:
    return [
        {
            "id": c.id,
            "code": c.code,
            "short_name": c.short_name,
            "name": c.name,
            "hourly_rate": c.hourly_rate,
            "capacity": c.capacity,
            "phase": c.phase,
            "is_supply": c.is_supply,
            "responsible_id": c.responsible_id,
            "responsible_name": c.responsible.full_name if c.responsible else "",
            "is_active": c.is_active,
            "requires_inspection": quality.requires_inspection(c.id),
        }
        for c in selectors.list_work_centers()
    ]


@router.get("/templates", response=list[TemplateListItem], operation_id="listProductTemplates")
def list_templates(request: AuthenticatedHttpRequest) -> list[Any]:
    return selectors.list_templates(active_only=True)


@router.get("/templates/{code_or_id}", response=TemplateOut, operation_id="getProductTemplate")
def get_template(request: AuthenticatedHttpRequest, code_or_id: str) -> Any:
    template = facade.get_template(code_or_id)
    if template is None:
        raise Http404
    return template


@router.get("/settings", response=ProductionSettingsOut, operation_id="getProductionSettings")
def get_settings(request: AuthenticatedHttpRequest) -> dict[str, Any]:
    settings = selectors.get_settings()
    pairs = [
        (OrderStage.LAUNCH, settings.launch_responsible if settings else None),
        (OrderStage.PREP, settings.prep_responsible if settings else None),
        (OrderStage.PROD, settings.prod_responsible if settings else None),
        (OrderStage.QC, settings.qc_responsible if settings else None),
    ]
    return {
        "stages": [
            {
                "stage": stage,
                "stage_label": str(stage.label),
                "responsible_id": employee.id if employee else None,
                "responsible_name": employee.full_name if employee else "",
            }
            for stage, employee in pairs
        ]
    }


@router.get("/document-kinds", response=list[DocumentKindOut], operation_id="listDocumentKinds")
def list_document_kinds(request: AuthenticatedHttpRequest) -> list[dict[str, str]]:
    return [{"code": code, "name": name} for code, name in selectors.DOCUMENT_TYPE_CODES.items()]


# --- Доска, Гант, «Мои визы» -------------------------------------------------------


@router.get("/board", response=list[OrderCardOut], operation_id="getProductionBoard")
def get_board(
    request: AuthenticatedHttpRequest,
    stage: OrderStage | None = None,
    search: str = "",
    active_only: bool = False,
) -> list[dict[str, Any]]:
    return [
        _card_out(request.auth, card)
        for card in selectors.list_board(stage=stage, search=search, active_only=active_only)
    ]


@router.get("/gantt", response=list[GanttOrderOut], operation_id="getProductionGantt")
def get_gantt(request: AuthenticatedHttpRequest) -> list[dict[str, Any]]:
    can_plan = bool(rules.can_plan_operations(request.auth))
    return [{**asdict(order), "can_plan": can_plan} for order in selectors.list_gantt()]


@router.get("/my-visas", response=list[VisaItemOut], operation_id="listMyProductionVisas")
def my_visas(request: AuthenticatedHttpRequest) -> list[Any]:
    employee_id = _employee(request)
    if employee_id is None:
        return []
    return selectors.list_my_visas(employee_id)


# --- Заказ -------------------------------------------------------------------------


@router.get("/orders/{order_id}", response=OrderOut, operation_id="getProductionOrder")
def get_order(request: AuthenticatedHttpRequest, order_id: UUID) -> dict[str, Any]:
    return _order_out(request.auth, order_id)


@router.patch("/orders/{order_id}", response=OrderOut, operation_id="updateProductionOrder")
def update_order(
    request: AuthenticatedHttpRequest, order_id: UUID, data: OrderUpdateIn
) -> dict[str, Any]:
    _card_or_404(order_id)
    if not rules.can_manage_orders(request.auth):
        raise PermissionDenied("Реквизиты заказа меняет начальник производства.")
    order_services.update_order(
        order_id,
        due_date=data.due_date,
        manager_id=data.manager_id,
        actor_id=request.auth.id,
        actor_employee_id=_employee(request),
    )
    return _order_out(request.auth, order_id)


@router.post("/orders/{order_id}/stage", response=OrderOut, operation_id="moveProductionOrderStage")
def move_stage(
    request: AuthenticatedHttpRequest, order_id: UUID, data: StageMoveIn
) -> dict[str, Any]:
    order = selectors.get_order(order_id)
    if order is None:
        raise Http404
    current = selectors.get_stage_approval(order_id, order.stage)
    if not rules.can_move_order(request.auth, order, current):
        raise PermissionDenied(
            "Этап переводит ответственный за этап, менеджер заказа или начальник производства."
        )
    may_approve = current is not None and rules.can_approve_stage(request.auth, current)
    order_services.move_order_stage(
        order_id,
        data.to,
        actor_id=request.auth.id,
        actor_employee_id=_employee(request),
        comment=data.comment,
        may_approve=may_approve,
    )
    return _order_out(request.auth, order_id)


@router.post(
    "/orders/{order_id}/stages/{stage}/approve",
    response=OrderOut,
    operation_id="approveProductionOrderStage",
)
def approve_stage(
    request: AuthenticatedHttpRequest, order_id: UUID, stage: OrderStage, data: StageApproveIn
) -> dict[str, Any]:
    approval = selectors.get_stage_approval(order_id, stage)
    if approval is None:
        raise Http404
    if not rules.can_approve_stage(request.auth, approval):
        raise PermissionDenied("Визу этапа ставит ответственный за этап.")
    order_services.approve_order_stage(
        order_id,
        stage,
        actor_id=request.auth.id,
        approver_id=_require_employee(request),
        comment=data.comment,
    )
    return _order_out(request.auth, order_id)


@router.patch(
    "/orders/{order_id}/stages/{stage}",
    response=OrderOut,
    operation_id="setProductionStageResponsible",
)
def set_stage_responsible(
    request: AuthenticatedHttpRequest, order_id: UUID, stage: OrderStage, data: StageResponsibleIn
) -> dict[str, Any]:
    _card_or_404(order_id)
    if not rules.can_manage_orders(request.auth):
        raise PermissionDenied("Ответственных за этапы назначает начальник производства.")
    order_services.set_stage_responsible(
        order_id,
        stage,
        data.responsible_id,
        actor_id=request.auth.id,
        actor_employee_id=_employee(request),
    )
    return _order_out(request.auth, order_id)


@router.get(
    "/orders/{order_id}/schedule", response=ScheduleOut, operation_id="getProductionOrderSchedule"
)
def get_schedule(request: AuthenticatedHttpRequest, order_id: UUID) -> dict[str, Any]:
    order = selectors.get_order(order_id)
    schedule = selectors.get_order_schedule(order_id)
    if order is None or schedule is None:
        raise Http404
    payload = asdict(schedule)
    payload["operations"] = [
        _row_out(request.auth, row, order.stage) for row in schedule.operations
    ]
    return payload


def _require_planner(request: AuthenticatedHttpRequest, order_id: UUID) -> None:
    if selectors.get_order(order_id) is None:
        raise Http404
    if not rules.can_plan_operations(request.auth):
        raise PermissionDenied("План заказа ведёт начальник производства.")


@router.post(
    "/orders/{order_id}/replan", response=ScheduleOut, operation_id="replanProductionOrder"
)
def replan(request: AuthenticatedHttpRequest, order_id: UUID, data: ReplanIn) -> dict[str, Any]:
    _require_planner(request, order_id)
    order_services.replan_order(
        order_id,
        data.planned_start,
        actor_id=request.auth.id,
        actor_employee_id=_employee(request),
    )
    return get_schedule(request, order_id)


@router.post("/orders/{order_id}/shift", response=ScheduleOut, operation_id="shiftProductionOrder")
def shift(request: AuthenticatedHttpRequest, order_id: UUID, data: ShiftIn) -> dict[str, Any]:
    _require_planner(request, order_id)
    order_services.shift_order(
        order_id, data.days, actor_id=request.auth.id, actor_employee_id=_employee(request)
    )
    return get_schedule(request, order_id)


# --- Журнал и комментарии ----------------------------------------------------------


@router.get(
    "/orders/{order_id}/journal",
    response=list[JournalEntryOut],
    operation_id="listProductionJournal",
)
def list_journal(
    request: AuthenticatedHttpRequest,
    order_id: UUID,
    operation_id: UUID | None = None,
    kind: JournalKind | None = None,
    author_id: UUID | None = None,
) -> list[Any]:
    if selectors.get_order(order_id) is None:
        raise Http404
    return selectors.list_journal(
        order_id, operation_id=operation_id, kind=kind, author_id=author_id
    )


@router.post(
    "/orders/{order_id}/comments", response=CreatedOut, operation_id="addProductionComment"
)
def add_comment(
    request: AuthenticatedHttpRequest, order_id: UUID, data: CommentIn
) -> dict[str, UUID]:
    if selectors.get_order(order_id) is None:
        raise Http404
    entry_id = journal_services.add_comment(
        order_id,
        data.text,
        operation_id=data.operation_id,
        author_employee_id=_require_employee(request),
    )
    return {"id": entry_id}


# --- Документы ---------------------------------------------------------------------


@router.get(
    "/orders/{order_id}/documents",
    response=list[DocumentOut],
    operation_id="listProductionOrderDocuments",
)
def list_documents(request: AuthenticatedHttpRequest, order_id: UUID) -> list[Any]:
    if selectors.get_order(order_id) is None:
        raise Http404
    return selectors.list_order_documents(order_id)


def _require_documents_right(request: AuthenticatedHttpRequest, order_id: UUID) -> None:
    if selectors.get_order(order_id) is None:
        raise Http404
    if not rules.can_manage_documents(request.auth):
        raise PermissionDenied("Документы заказа ведут конструктор и технолог.")


@router.post(
    "/orders/{order_id}/documents",
    response=list[DocumentOut],
    operation_id="uploadProductionOrderDocument",
)
def upload_document(
    request: AuthenticatedHttpRequest,
    order_id: UUID,
    file: UploadedFile = File(...),
    doc_type_code: str = Form(...),
    operation_id: UUID | None = Form(None),
    description: str = Form(""),
) -> list[Any]:
    _require_documents_right(request, order_id)
    document_services.upload_order_document(
        order_id,
        file,
        doc_type_code=doc_type_code,
        operation_id=operation_id,
        description=description,
        actor_id=request.auth.id,
        actor_employee_id=_employee(request),
    )
    return selectors.list_order_documents(order_id)


@router.post(
    "/orders/{order_id}/documents/{document_id}/approve",
    response=list[DocumentOut],
    operation_id="approveProductionOrderDocument",
)
def approve_document(
    request: AuthenticatedHttpRequest, order_id: UUID, document_id: UUID
) -> list[Any]:
    _require_documents_right(request, order_id)
    document_services.approve_document(
        order_id, document_id, actor_id=request.auth.id, approver_id=_require_employee(request)
    )
    return selectors.list_order_documents(order_id)


@router.delete(
    "/orders/{order_id}/documents/{document_id}",
    response=list[DocumentOut],
    operation_id="annulProductionOrderDocument",
)
def annul_document(
    request: AuthenticatedHttpRequest, order_id: UUID, document_id: UUID
) -> list[Any]:
    _require_documents_right(request, order_id)
    document_services.annul_document(
        order_id, document_id, actor_id=request.auth.id, actor_employee_id=_employee(request)
    )
    return selectors.list_order_documents(order_id)


# --- Операция ----------------------------------------------------------------------


def _operation_or_404(operation_id: UUID) -> tuple[OperationRow, str]:
    operation = selectors.get_operation(operation_id)
    if operation is None:
        raise Http404
    schedule = selectors.get_order_schedule(operation.order_id)
    assert schedule is not None
    row = next(r for r in schedule.operations if r.id == operation_id)
    return row, operation.order.stage


def _operation_card(user: User, operation_id: UUID) -> dict[str, Any]:
    card = selectors.get_operation_card(operation_id)
    if card is None:
        raise Http404
    payload = asdict(card)
    payload["operation"] = _row_out(user, card.operation, card.order.stage)
    payload["order"] = _card_out(user, card.order)
    return payload


@router.get(
    "/operations/{operation_id}", response=OperationCardOut, operation_id="getProductionOperation"
)
def get_operation(request: AuthenticatedHttpRequest, operation_id: UUID) -> dict[str, Any]:
    return _operation_card(request.auth, operation_id)


@router.patch(
    "/operations/{operation_id}",
    response=OperationCardOut,
    operation_id="updateProductionOperation",
)
def update_operation(
    request: AuthenticatedHttpRequest, operation_id: UUID, data: OperationUpdateIn
) -> dict[str, Any]:
    row, stage = _operation_or_404(operation_id)
    abilities = _operation_abilities(request.auth, row, stage)
    fields = data.model_fields_set
    actor_id, employee_id = request.auth.id, _employee(request)
    if "responsible_id" in fields:
        if not abilities.can_set_responsible:
            raise PermissionDenied("Ответственного за операцию назначает начальник производства.")
        if data.responsible_id is not None:
            operation_services.set_operation_responsible(
                operation_id,
                data.responsible_id,
                actor_id=actor_id,
                actor_employee_id=employee_id,
            )
    if {"people", "not_before"} & fields and not rules.can_plan_operations(request.auth):
        raise PermissionDenied("План операции ведёт начальник производства.")
    if "people" in fields and data.people is not None:
        operation_services.set_operation_people(
            operation_id, data.people, actor_id=actor_id, actor_employee_id=employee_id
        )
    if "not_before" in fields:
        operation_services.set_operation_not_before(
            operation_id, data.not_before, actor_id=actor_id, actor_employee_id=employee_id
        )
    return _operation_card(request.auth, operation_id)


@router.post(
    "/operations/{operation_id}/status",
    response=OperationCardOut,
    operation_id="setProductionOperationStatus",
)
def set_status(
    request: AuthenticatedHttpRequest, operation_id: UUID, data: OperationStatusIn
) -> dict[str, Any]:
    row, stage = _operation_or_404(operation_id)
    if not _operation_abilities(request.auth, row, stage).can_change_status:
        raise PermissionDenied("Статус операции меняет её ответственный.")
    operation_services.set_operation_status(
        operation_id, data.status, actor_id=request.auth.id, actor_employee_id=_employee(request)
    )
    return _operation_card(request.auth, operation_id)


@router.post(
    "/operations/{operation_id}/progress",
    response=OperationCardOut,
    operation_id="setProductionOperationProgress",
)
def set_progress(
    request: AuthenticatedHttpRequest, operation_id: UUID, data: OperationProgressIn
) -> dict[str, Any]:
    row, stage = _operation_or_404(operation_id)
    if not _operation_abilities(request.auth, row, stage).can_change_status:
        raise PermissionDenied("Ход операции отмечает её ответственный.")
    operation_services.set_operation_progress(
        operation_id, data.progress, actor_id=request.auth.id, actor_employee_id=_employee(request)
    )
    return _operation_card(request.auth, operation_id)


@router.post(
    "/operations/{operation_id}/approve",
    response=OperationCardOut,
    operation_id="approveProductionOperation",
)
def approve_operation(
    request: AuthenticatedHttpRequest, operation_id: UUID, data: OperationApproveIn
) -> dict[str, Any]:
    row, stage = _operation_or_404(operation_id)
    me = _employee(request)
    if not (me is not None and me == row.responsible_id) and not rules.can_approve_any(
        request.auth
    ):
        raise PermissionDenied("Визу на операцию ставит ответственный.")
    operation_services.approve_operation(
        operation_id,
        actor_id=request.auth.id,
        approver_id=_require_employee(request),
        comment=data.comment,
    )
    return _operation_card(request.auth, operation_id)


@router.post(
    "/operations/{operation_id}/move",
    response=OperationCardOut,
    operation_id="moveProductionOperation",
)
def move_operation(
    request: AuthenticatedHttpRequest, operation_id: UUID, data: OperationMoveIn
) -> dict[str, Any]:
    _operation_or_404(operation_id)
    if not rules.can_plan_operations(request.auth):
        raise PermissionDenied("План операции ведёт начальник производства.")
    operation_services.move_operation(
        operation_id, data.start, actor_id=request.auth.id, actor_employee_id=_employee(request)
    )
    return _operation_card(request.auth, operation_id)


@router.put(
    "/operations/{operation_id}/predecessors",
    response=OperationCardOut,
    operation_id="setProductionOperationPredecessors",
)
def set_predecessors(
    request: AuthenticatedHttpRequest, operation_id: UUID, data: PredecessorsIn
) -> dict[str, Any]:
    _operation_or_404(operation_id)
    if not rules.can_plan_operations(request.auth):
        raise PermissionDenied("Связи операций ведёт начальник производства.")
    operation_services.set_predecessors(
        operation_id,
        data.predecessor_ids,
        actor_id=request.auth.id,
        actor_employee_id=_employee(request),
    )
    return _operation_card(request.auth, operation_id)
