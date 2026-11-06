"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import type { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useGetCsrf, useLogin } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/mutator";
import { LoginBody } from "@/lib/api/schemas";

type LoginFormValues = z.infer<typeof LoginBody>;

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Прогревает cookie csrftoken до сабмита — без неё Django отклонит POST /login
  // как межсайтовый запрос (CsrfViewMiddleware), даже с проксированием same-origin.
  // Кнопка входа заблокирована, пока запрос не завершился: менеджер паролей
  // заполняет форму мгновенно, и сабмит по Enter успевал уйти без токена (403).
  const csrf = useGetCsrf();

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(LoginBody),
    defaultValues: { email: "", password: "" },
  });

  const login = useLogin({
    mutation: {
      meta: { skipGlobalErrorToast: true },
      onSuccess: () => {
        const next = searchParams.get("next") || "/parties";
        router.push(next);
        router.refresh();
      },
      onError: (error) => {
        const message =
          error instanceof ApiError ? error.message : "Не удалось войти. Попробуйте ещё раз.";
        setError("root", { message });
      },
    },
  });

  return (
    <form
      onSubmit={handleSubmit((values) => login.mutate({ data: values }))}
      className="flex flex-col gap-4"
      noValidate
    >
      <div className="flex flex-col gap-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="username"
          autoFocus
          required
          aria-invalid={!!errors.email}
          {...register("email")}
        />
        {errors.email && <p className="text-sm text-destructive">{errors.email.message}</p>}
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="password">Пароль</Label>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          aria-invalid={!!errors.password}
          {...register("password")}
        />
        {errors.password && <p className="text-sm text-destructive">{errors.password.message}</p>}
      </div>

      {errors.root && <p className="text-sm text-destructive">{errors.root.message}</p>}

      <Button
        type="submit"
        disabled={isSubmitting || login.isPending || csrf.isLoading}
        className="mt-2"
      >
        {login.isPending ? "Вход…" : "Войти"}
      </Button>
    </form>
  );
}
