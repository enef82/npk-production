"use client";

import {
  Controller,
  useForm,
  type DefaultValues,
  type FieldValues,
  type Resolver,
  type UseFormReturn,
} from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { z } from "zod";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api/mutator";
import { readDraft, useDraftAutosave } from "./use-draft-autosave";
import { useUnsavedChangesGuard } from "./use-unsaved-changes-guard";

export type EntityFormField =
  | { type: "text"; name: string; label: string; placeholder?: string; autoFocus?: boolean }
  | { type: "select"; name: string; label: string; options: { value: string; label: string }[] }
  | { type: "checkbox"; name: string; label: string };

export type EntityFormProps<TFieldValues extends FieldValues> = {
  /** Zod-схема — из сгенерированного orval-клиента (lib/api/schemas.ts), без ручного дубля. */
  schema: z.ZodType<TFieldValues>;
  fields: EntityFormField[];
  defaultValues: DefaultValues<TFieldValues>;
  onSubmit: (values: TFieldValues) => Promise<void>;
  /**
   * Доменная ошибка (409 и т.п.) — не поле формы, решает вызывающая сторона
   * (например, диалог подтверждения при найденных дубликатах). Если не задан,
   * такая ошибка просто показывается общей строкой над кнопкой отправки.
   */
  onDomainError?: (error: ApiError) => void;
  submitLabel?: string;
  /** Ключ автосохранения черновика в localStorage; без него автосохранения нет. */
  draftKey?: string;
};

export function EntityForm<TFieldValues extends FieldValues>({
  schema,
  fields,
  defaultValues,
  onSubmit,
  onDomainError,
  submitLabel = "Сохранить",
  draftKey,
}: EntityFormProps<TFieldValues>) {
  const draft = draftKey ? readDraft<TFieldValues>(draftKey) : null;

  // react-hook-form + zodResolver с явно generic-параметризованным z.ZodType<TFieldValues>
  // (не конкретной схемой) не выводят совпадающий Resolver<TFieldValues>, а сам useForm(),
  // если типизировать его результат через ReturnType в другом месте компонента, даёт
  // структурно тот же, но номинально «другой» тип — известное ограничение вывода типов
  // на стыке двух generic-библиотек, не ошибка в разметке формы. `UseFormReturn<TFieldValues>`
  // здесь и в `EntityFormField` ниже — единственная точка приведения типа во всём компоненте,
  // дальше `form` используется с обычной типобезопасностью.
  const form: UseFormReturn<TFieldValues> = useForm<TFieldValues>({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    resolver: zodResolver(schema as any) as unknown as Resolver<TFieldValues>,
    defaultValues: (draft ?? defaultValues) as DefaultValues<TFieldValues>,
  });
  const { clearDraft } = useDraftAutosave(draftKey, form);
  useUnsavedChangesGuard(form.formState.isDirty && !form.formState.isSubmitSuccessful);

  async function handleSubmit(values: TFieldValues) {
    try {
      await onSubmit(values);
      clearDraft();
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;

      if (error.fieldErrors && error.fieldErrors.length > 0) {
        for (const fieldError of error.fieldErrors) {
          const name = fieldError.loc[fieldError.loc.length - 1];
          if (typeof name === "string") {
            form.setError(name as never, { message: fieldError.msg });
          }
        }
        return;
      }

      if (onDomainError) {
        onDomainError(error);
        return;
      }

      form.setError("root" as never, { message: error.message });
    }
  }

  return (
    <form onSubmit={form.handleSubmit(handleSubmit)} className="flex flex-col gap-4" noValidate>
      {fields.map((field) => (
        <EntityFormField key={field.name} field={field} form={form} />
      ))}

      {form.formState.errors.root?.message && (
        <p className="text-sm text-destructive">{String(form.formState.errors.root.message)}</p>
      )}

      <Button type="submit" disabled={form.formState.isSubmitting} className="mt-2">
        {form.formState.isSubmitting ? "Сохранение…" : submitLabel}
      </Button>
    </form>
  );
}

function EntityFormField<TFieldValues extends FieldValues>({
  field,
  form,
}: {
  field: EntityFormField;
  form: UseFormReturn<TFieldValues>;
}) {
  const error = form.formState.errors[field.name as keyof TFieldValues];
  const errorMessage = typeof error?.message === "string" ? error.message : undefined;

  if (field.type === "checkbox") {
    return (
      <Controller
        control={form.control}
        name={field.name as never}
        render={({ field: controllerField }) => (
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={!!controllerField.value}
              onCheckedChange={(checked) => controllerField.onChange(!!checked)}
            />
            {field.label}
          </label>
        )}
      />
    );
  }

  if (field.type === "select") {
    return (
      <div className="flex flex-col gap-2">
        <Label htmlFor={field.name}>{field.label}</Label>
        <Controller
          control={form.control}
          name={field.name as never}
          render={({ field: controllerField }) => (
            <Select value={controllerField.value} onValueChange={controllerField.onChange}>
              <SelectTrigger id={field.name} aria-invalid={!!error}>
                <SelectValue>
                  {(value: string | null) =>
                    field.options.find((option) => option.value === value)?.label ?? ""
                  }
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {field.options.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        />
        {errorMessage && <p className="text-sm text-destructive">{errorMessage}</p>}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={field.name}>{field.label}</Label>
      <Input
        id={field.name}
        placeholder={field.placeholder}
        autoFocus={field.autoFocus}
        aria-invalid={!!error}
        {...form.register(field.name as never)}
      />
      {errorMessage && <p className="text-sm text-destructive">{errorMessage}</p>}
    </div>
  );
}
