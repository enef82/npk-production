/**
 * Кастомный fetch-мутатор для orval (client: "react-query", httpClient: "fetch").
 *
 * Единая обработка ошибок: сервер отвечает одним из двух конвертов —
 *   {code, message, details?}       — доменная ошибка (core.common.exceptions.DomainError)
 *   {code: "validation_error", message, errors: [...]}  — 422 от pydantic/ninja
 * Оба нормализуются в ApiError, чтобы вызывающему коду (react-query onError,
 * EntityForm) не нужно было знать про оба формата по отдельности.
 *
 * `/api/*` проксируется Next.js (next.config.ts) на Django — same-origin, поэтому
 * сессионная cookie идёт сама по себе с `credentials: "include"`, CORS не нужен.
 * CSRF — Django ждёт X-CSRFToken на небезопасных методах даже для same-origin.
 */

export type ApiFieldError = {
  loc: (string | number)[];
  msg: string;
  type: string;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly fieldErrors: ApiFieldError[] | null;

  constructor(
    status: number,
    code: string,
    message: string,
    options: { details?: unknown; fieldErrors?: ApiFieldError[] | null } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = options.details ?? null;
    this.fieldErrors = options.fieldErrors ?? null;
  }
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export const customFetch = async <T>(url: string, options: RequestInit): Promise<T> => {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);

  if (UNSAFE_METHODS.has(method)) {
    const csrfToken = readCookie("csrftoken");
    if (csrfToken) headers.set("X-CSRFToken", csrfToken);
  }
  // FormData (multipart-загрузка файлов) — Content-Type ставит браузер сам, вместе с
  // boundary; выставить его руками здесь значит сломать разбор на стороне Django.
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: "include",
  });

  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok) {
    const code = typeof body?.code === "string" ? body.code : "unknown_error";
    const message = typeof body?.message === "string" ? body.message : response.statusText;
    const fieldErrors = code === "validation_error" && Array.isArray(body?.errors) ? body.errors : null;
    throw new ApiError(response.status, code, message, { details: body?.details, fieldErrors });
  }

  return body as T;
};

export default customFetch;
