import { NextRequest, NextResponse } from "next/server";

// Дешёвая проверка на входе: если cookie сессии нет вообще — сразу на /login, без
// похода в Django. Не источник истины (cookie может быть просрочена на сервере) —
// финальную проверку делает `(protected)/layout.tsx` через реальный /accounts/me;
// см. lib/auth/session.ts. Имя cookie — SESSION_COOKIE_NAME по умолчанию Django.
const SESSION_COOKIE_NAME = "sessionid";
const PUBLIC_PATHS = ["/login"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (PUBLIC_PATHS.some((path) => pathname.startsWith(path))) {
    return NextResponse.next();
  }

  const hasSession = request.cookies.has(SESSION_COOKIE_NAME);
  if (!hasSession) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
