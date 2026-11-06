"""Эндпоинты django-ninja модуля «Заявки и калькуляция»
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.2, §4, §6).

Права проверяются здесь, сервисы их не проверяют. Карточка отдаёт серверные
`abilities`, посчитанные теми же функциями, что и проверки эндпоинтов.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any
from uuid import UUID

from django.http import Http404, HttpRequest
from ninja import Router

from src.core.accounts.models import User
from src.core.common.exceptions import PermissionDenied
from src.sales import rules, selectors
from src.sales.exceptions import EmployeeNotFound
from src.sales.models import InquiryStage
from src.sales.selectors import InquiryCard
from src.sales.services import calculation as calc_services
from src.sales.services import inquiry as inquiry_services

from .schemas import (
    CalcOperationIn,
    CalcPredecessorsIn,
    FillFromTemplateIn,
    InquiryAbilitiesOut,
    InquiryCardOut,
    InquiryCreateIn,
    InquiryOut,
    InquiryStageApproveIn,
    InquiryStageMoveIn,
    InquiryStageResponsibleIn,
    InquiryUpdateIn,
    InquiryVisaItemOut,
    LaunchIn,
    LaunchOut,
    LaunchPreviewOut,
    LoseIn,
    LossReasonOut,
    MaterialIn,
    PlanIn,
    SalesSettingsOut,
)

router = Router(tags=["sales"])


class AuthenticatedHttpRequest(HttpRequest):
    auth: User


def _abilities(user: User, card: InquiryCard) -> InquiryAbilitiesOut:
    responsible = card.stage_responsible_id
    is_open = card.stage in (InquiryStage.NEW, InquiryStage.CALC, InquiryStage.APPROVAL)
    return InquiryAbilitiesOut(
        can_edit=rules.can_edit_inquiry(user, card),
        can_edit_calculation=rules.can_edit_calculation(user, card),
        can_move=rules.can_move_inquiry(user, card, responsible),
        can_approve_stage=(
            is_open and not card.stage_approved and rules.can_approve_stage(user, responsible)
        ),
        can_launch=card.stage == InquiryStage.APPROVAL and bool(rules.can_launch_inquiry(user)),
        can_lose=rules.can_edit_inquiry(user, card),
    )


def _detail(inquiry_id: UUID) -> selectors.InquiryDetail:
    detail = selectors.get_inquiry_detail(inquiry_id)
    if detail is None:
        raise Http404
    return detail


def _out(user: User, inquiry_id: UUID) -> dict[str, Any]:
    detail = _detail(inquiry_id)
    return {**asdict(detail), "abilities": _abilities(user, detail)}


def _require_edit(request: AuthenticatedHttpRequest, inquiry_id: UUID) -> None:
    if not rules.can_edit_inquiry(request.auth, _detail(inquiry_id)):
        raise PermissionDenied("Заявку ведёт её менеджер.")


def _require_calc(request: AuthenticatedHttpRequest, inquiry_id: UUID | None) -> UUID:
    if inquiry_id is None:
        raise Http404
    if not rules.can_edit_calculation(request.auth, _detail(inquiry_id)):
        raise PermissionDenied("Калькуляцию ведут экономист и менеджер заявки.")
    return inquiry_id


# --- Справочники и списки ----------------------------------------------------------


@router.get("/loss-reasons", response=list[LossReasonOut], operation_id="listLossReasons")
def list_loss_reasons(request: AuthenticatedHttpRequest) -> list[Any]:
    return selectors.list_loss_reasons()


@router.get("/settings", response=SalesSettingsOut, operation_id="getSalesSettings")
def get_settings(request: AuthenticatedHttpRequest) -> dict[str, Any]:
    settings = selectors.get_settings()
    if settings is None:
        settings = inquiry_services.get_settings()
    return {
        "economist_id": settings.economist_id,
        "economist_name": settings.economist.full_name if settings.economist else "",
        "prob_new": settings.prob_new,
        "prob_calc": settings.prob_calc,
        "prob_approval": settings.prob_approval,
    }


@router.get("/board", response=list[InquiryCardOut], operation_id="getSalesBoard")
def get_board(
    request: AuthenticatedHttpRequest,
    stage: InquiryStage | None = None,
    search: str = "",
    include_closed: bool = False,
) -> list[dict[str, Any]]:
    return [
        {**asdict(card), "abilities": _abilities(request.auth, card)}
        for card in selectors.list_board(stage=stage, search=search, include_closed=include_closed)
    ]


@router.get("/my-visas", response=list[InquiryVisaItemOut], operation_id="listMySalesVisas")
def my_visas(request: AuthenticatedHttpRequest) -> list[Any]:
    employee_id = rules.employee_id_of(request.auth)
    if employee_id is None:
        return []
    return selectors.list_my_visas(employee_id)


# --- Заявка ------------------------------------------------------------------------


@router.post("/inquiries", response=InquiryOut, operation_id="createInquiry")
def create_inquiry(request: AuthenticatedHttpRequest, data: InquiryCreateIn) -> dict[str, Any]:
    if not rules.can_create_inquiries(request.auth):
        raise PermissionDenied("Заявку заводит менеджер проекта.")
    manager_id = data.manager_id or rules.employee_id_of(request.auth)
    if manager_id is None:
        raise EmployeeNotFound("Укажите менеджера заявки.")
    inquiry_id = inquiry_services.create_inquiry(
        inquiry_services.InquiryCreateDTO(
            customer_id=data.customer_id,
            new_customer=(
                inquiry_services.NewCustomer(
                    short_name=data.new_customer.short_name, inn=data.new_customer.inn
                )
                if data.new_customer
                else None
            ),
            object_name=data.object_name,
            template_id=data.template_id,
            product_name=data.product_name,
            quantity=data.quantity,
            due_date=data.due_date,
            manager_id=manager_id,
        ),
        actor_id=request.auth.id,
    )
    return _out(request.auth, inquiry_id)


@router.get("/inquiries/{inquiry_id}", response=InquiryOut, operation_id="getInquiry")
def get_inquiry(request: AuthenticatedHttpRequest, inquiry_id: UUID) -> dict[str, Any]:
    return _out(request.auth, inquiry_id)


@router.patch("/inquiries/{inquiry_id}", response=InquiryOut, operation_id="updateInquiry")
def update_inquiry(
    request: AuthenticatedHttpRequest, inquiry_id: UUID, data: InquiryUpdateIn
) -> dict[str, Any]:
    _require_edit(request, inquiry_id)
    inquiry_services.update_inquiry(
        inquiry_id,
        inquiry_services.InquiryUpdateDTO(**data.model_dump()),
        actor_id=request.auth.id,
    )
    return _out(request.auth, inquiry_id)


@router.post("/inquiries/{inquiry_id}/stage", response=InquiryOut, operation_id="moveInquiryStage")
def move_stage(
    request: AuthenticatedHttpRequest, inquiry_id: UUID, data: InquiryStageMoveIn
) -> dict[str, Any]:
    detail = _detail(inquiry_id)
    if not rules.can_move_inquiry(request.auth, detail, detail.stage_responsible_id):
        raise PermissionDenied("Этап переводит менеджер заявки или ответственный за этап.")
    inquiry_services.move_inquiry_stage(
        inquiry_id,
        data.to,
        actor_id=request.auth.id,
        actor_employee_id=rules.employee_id_of(request.auth),
        comment=data.comment,
        may_approve=rules.can_approve_stage(request.auth, detail.stage_responsible_id),
    )
    return _out(request.auth, inquiry_id)


@router.post(
    "/inquiries/{inquiry_id}/stages/{stage}/approve",
    response=InquiryOut,
    operation_id="approveInquiryStage",
)
def approve_stage(
    request: AuthenticatedHttpRequest,
    inquiry_id: UUID,
    stage: InquiryStage,
    data: InquiryStageApproveIn,
) -> dict[str, Any]:
    approval = selectors.get_stage_approval(inquiry_id, stage)
    if approval is None:
        raise Http404
    if not rules.can_approve_stage(request.auth, approval.responsible_id):
        raise PermissionDenied("Визу этапа ставит ответственный за этап.")
    approver = rules.employee_id_of(request.auth)
    if approver is None:
        raise EmployeeNotFound("Текущий пользователь не связан с сотрудником.")
    inquiry_services.approve_inquiry_stage(
        inquiry_id, stage, actor_id=request.auth.id, approver_id=approver, comment=data.comment
    )
    return _out(request.auth, inquiry_id)


@router.patch(
    "/inquiries/{inquiry_id}/stages/{stage}",
    response=InquiryOut,
    operation_id="setInquiryStageResponsible",
)
def set_stage_responsible(
    request: AuthenticatedHttpRequest,
    inquiry_id: UUID,
    stage: InquiryStage,
    data: InquiryStageResponsibleIn,
) -> dict[str, Any]:
    _require_edit(request, inquiry_id)
    inquiry_services.set_inquiry_stage_responsible(
        inquiry_id, stage, data.responsible_id, actor_id=request.auth.id
    )
    return _out(request.auth, inquiry_id)


@router.post("/inquiries/{inquiry_id}/launch", response=LaunchOut, operation_id="launchInquiry")
def launch(request: AuthenticatedHttpRequest, inquiry_id: UUID, data: LaunchIn) -> dict[str, Any]:
    detail = _detail(inquiry_id)
    if not rules.can_launch_inquiry(request.auth):
        raise PermissionDenied("Запускает в работу начальник производства.")
    result = inquiry_services.launch_inquiry(
        inquiry_id,
        planned_start=data.planned_start,
        due_date=data.due_date,
        actor_id=request.auth.id,
        actor_employee_id=rules.employee_id_of(request.auth),
        may_approve=rules.can_approve_stage(request.auth, detail.stage_responsible_id),
    )
    return {"inquiry_id": inquiry_id, "order_id": result.order_id, "warnings": result.warnings}


@router.get(
    "/inquiries/{inquiry_id}/launch-preview",
    response=LaunchPreviewOut,
    operation_id="previewInquiryLaunch",
)
def launch_preview(
    request: AuthenticatedHttpRequest, inquiry_id: UUID, planned_start: date, due_date: date
) -> Any:
    preview = selectors.launch_preview(inquiry_id, planned_start, due_date)
    if preview is None:
        raise Http404
    return preview


@router.post("/inquiries/{inquiry_id}/lose", response=InquiryOut, operation_id="loseInquiry")
def lose(request: AuthenticatedHttpRequest, inquiry_id: UUID, data: LoseIn) -> dict[str, Any]:
    _require_edit(request, inquiry_id)
    inquiry_services.lose_inquiry(
        inquiry_id, data.reason_id, data.comment, actor_id=request.auth.id
    )
    return _out(request.auth, inquiry_id)


# --- Калькуляция и план ------------------------------------------------------------


@router.post(
    "/inquiries/{inquiry_id}/fill-from-template",
    response=InquiryOut,
    operation_id="fillInquiryFromTemplate",
)
def fill_from_template(
    request: AuthenticatedHttpRequest, inquiry_id: UUID, data: FillFromTemplateIn
) -> dict[str, Any]:
    _require_calc(request, inquiry_id)
    calc_services.fill_from_template(inquiry_id, data.template_id, actor_id=request.auth.id)
    return _out(request.auth, inquiry_id)


@router.post(
    "/inquiries/{inquiry_id}/materials", response=InquiryOut, operation_id="addCalcMaterial"
)
def add_material(
    request: AuthenticatedHttpRequest, inquiry_id: UUID, data: MaterialIn
) -> dict[str, Any]:
    _require_calc(request, inquiry_id)
    calc_services.add_material(
        inquiry_id, calc_services.MaterialDTO(**data.model_dump()), actor_id=request.auth.id
    )
    return _out(request.auth, inquiry_id)


@router.patch("/materials/{material_id}", response=InquiryOut, operation_id="updateCalcMaterial")
def update_material(
    request: AuthenticatedHttpRequest, material_id: UUID, data: MaterialIn
) -> dict[str, Any]:
    inquiry_id = _require_calc(request, selectors.inquiry_id_of_material(material_id))
    calc_services.update_material(
        material_id, calc_services.MaterialDTO(**data.model_dump()), actor_id=request.auth.id
    )
    return _out(request.auth, inquiry_id)


@router.delete("/materials/{material_id}", response=InquiryOut, operation_id="deleteCalcMaterial")
def delete_material(request: AuthenticatedHttpRequest, material_id: UUID) -> dict[str, Any]:
    inquiry_id = _require_calc(request, selectors.inquiry_id_of_material(material_id))
    calc_services.delete_material(material_id, actor_id=request.auth.id)
    return _out(request.auth, inquiry_id)


@router.post(
    "/inquiries/{inquiry_id}/operations", response=InquiryOut, operation_id="addCalcOperation"
)
def add_operation(
    request: AuthenticatedHttpRequest, inquiry_id: UUID, data: CalcOperationIn
) -> dict[str, Any]:
    _require_calc(request, inquiry_id)
    calc_services.add_operation(
        inquiry_id, calc_services.CalcOperationDTO(**data.model_dump()), actor_id=request.auth.id
    )
    return _out(request.auth, inquiry_id)


@router.patch("/operations/{operation_id}", response=InquiryOut, operation_id="updateCalcOperation")
def update_operation(
    request: AuthenticatedHttpRequest, operation_id: UUID, data: CalcOperationIn
) -> dict[str, Any]:
    inquiry_id = _require_calc(request, selectors.inquiry_id_of_operation(operation_id))
    calc_services.update_operation(
        operation_id, calc_services.CalcOperationDTO(**data.model_dump()), actor_id=request.auth.id
    )
    return _out(request.auth, inquiry_id)


@router.delete(
    "/operations/{operation_id}", response=InquiryOut, operation_id="deleteCalcOperation"
)
def delete_operation(request: AuthenticatedHttpRequest, operation_id: UUID) -> dict[str, Any]:
    inquiry_id = _require_calc(request, selectors.inquiry_id_of_operation(operation_id))
    calc_services.delete_operation(operation_id, actor_id=request.auth.id)
    return _out(request.auth, inquiry_id)


@router.put(
    "/operations/{operation_id}/predecessors",
    response=InquiryOut,
    operation_id="setCalcOperationPredecessors",
)
def set_predecessors(
    request: AuthenticatedHttpRequest, operation_id: UUID, data: CalcPredecessorsIn
) -> dict[str, Any]:
    inquiry_id = _require_calc(request, selectors.inquiry_id_of_operation(operation_id))
    calc_services.set_predecessors(operation_id, data.predecessor_ids, actor_id=request.auth.id)
    return _out(request.auth, inquiry_id)


@router.post(
    "/inquiries/{inquiry_id}/link-sequential",
    response=InquiryOut,
    operation_id="linkCalcOperationsSequentially",
)
def link_sequential(request: AuthenticatedHttpRequest, inquiry_id: UUID) -> dict[str, Any]:
    _require_calc(request, inquiry_id)
    calc_services.link_sequential(inquiry_id, actor_id=request.auth.id)
    return _out(request.auth, inquiry_id)


@router.post("/inquiries/{inquiry_id}/plan", response=InquiryOut, operation_id="buildInquiryPlan")
def build_plan(request: AuthenticatedHttpRequest, inquiry_id: UUID, data: PlanIn) -> dict[str, Any]:
    _require_calc(request, inquiry_id)
    calc_services.build_plan(inquiry_id, data.planned_start, actor_id=request.auth.id)
    return _out(request.auth, inquiry_id)
