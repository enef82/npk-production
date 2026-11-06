"""Эндпоинты django-ninja модуля «Ядро: учётные записи».

Логин/логаут — сознательно не под `django_auth` (это же вход и выход), `auth=None`
переопределяет глобальный `auth=django_auth` `NinjaAPI` для этих двух операций.
`GET /csrf` тоже публичный: браузерный SPA-клиент не имеет `csrftoken`-cookie до
первого запроса, а без неё CSRF-проверка не пропустит `POST /login` — эндпоинт
существует только затем, чтобы фронтенд мог явно инициализировать cookie перед входом.

CSRF на `/login` — не автоматика. django-ninja сам глобально помечает свои view
`csrf_exempt` на уровне Django и проверяет CSRF вручную только внутри
`SessionAuth`/`APIKeyCookie.authenticate()` (`ninja.utils.check_csrf`) — то есть
только для операций, где реально сработала cookie-based аутентификация. У `/login`
`auth=None` (иначе пользователь не мог бы залогиниться первый раз), поэтому эта
проверка сама по себе никогда не выполнится — без явного вызова `check_csrf` здесь
эндпоинт был бы уязвим к login CSRF (OWASP): межсайтовая форма могла бы тихо
залогинить жертву под учётной записью, контролируемой атакующим.
"""

from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.http import HttpRequest
from django.middleware.csrf import get_token
from ninja import Router
from ninja.utils import check_csrf

from src.core.accounts.models import User
from src.core.common.exceptions import PermissionDenied

from .schemas import LoginIn, MeOut

router = Router(tags=["accounts"])


class AuthenticatedHttpRequest(HttpRequest):
    """`request.auth` — атрибут, который проставляет django-ninja при аутентификации
    (`NinjaAPI(auth=django_auth)`); в стандартном стабе HttpRequest его нет."""

    auth: User


def _enforce_csrf(request: HttpRequest) -> None:
    if check_csrf(request) is not None:
        raise PermissionDenied("Запрос отклонён проверкой CSRF.")


def _to_me_out(user: User) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_superuser=user.is_superuser,
        roles=list(user.groups.values_list("name", flat=True)),
    )


@router.get("/csrf", auth=None, response=dict[str, bool], operation_id="getCsrf")
def get_csrf(request: HttpRequest) -> dict[str, bool]:
    # `@ensure_csrf_cookie` не годится: она вызывает `.set_cookie()` на возвращаемом
    # значении, ожидая настоящий `HttpResponse`, а ninja-эндпоинт возвращает dict —
    # финальный HttpResponse ninja строит уже после выхода из этой функции.
    # `get_token()` — низкоуровневый штатный способ: помечает cookie к установке,
    # а `CsrfViewMiddleware` (уже в MIDDLEWARE) сам допишет её в тот HttpResponse,
    # который ninja соберёт по возвращённому dict.
    get_token(request)
    return {"ok": True}


@router.post("/login", auth=None, response=MeOut, operation_id="login")
def login_view(request: HttpRequest, data: LoginIn) -> MeOut:
    _enforce_csrf(request)
    user = authenticate(request, username=data.email, password=data.password)
    if user is None or not user.is_active:
        raise PermissionDenied("Неверный email или пароль.")
    login(request, user)
    return _to_me_out(user)


@router.post("/logout", auth=None, response=dict[str, bool], operation_id="logout")
def logout_view(request: HttpRequest) -> dict[str, bool]:
    _enforce_csrf(request)
    logout(request)
    return {"ok": True}


@router.get("/me", response=MeOut, operation_id="getMe")
def me(request: AuthenticatedHttpRequest) -> MeOut:
    return _to_me_out(request.auth)
