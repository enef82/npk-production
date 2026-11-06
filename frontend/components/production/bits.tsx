"use client";

import { cn } from "@/lib/utils";
import { initials } from "@/lib/production/format";

/**
 * Мелкие элементы экранов производства по образцу прототипа: точка здоровья, «пилюля»,
 * аватар, полоса прогресса, плотные поля ввода для таблиц (нативные элементы — в
 * таблице калькуляции десятки строк, а `Select` из shadcn на каждую ячейку тяжёл).
 */

export type Tone = "g" | "y" | "r" | "b" | "c" | "n";

const DOT: Record<string, string> = {
  g: "bg-emerald-600",
  y: "bg-amber-600",
  r: "bg-red-600",
  n: "bg-slate-300",
};

export function HealthDot({ color, title }: { color: string; title?: string }) {
  return <span title={title} className={cn("inline-block size-2 shrink-0 rounded-full", DOT[color] ?? DOT.n)} />;
}

const PILL: Record<Tone, string> = {
  g: "bg-emerald-50 text-emerald-700",
  y: "bg-amber-50 text-amber-700",
  r: "bg-red-50 text-red-700",
  b: "bg-blue-50 text-blue-700",
  c: "bg-orange-50 text-orange-700",
  n: "bg-muted text-muted-foreground",
};

export function Pill({
  tone = "n",
  className,
  children,
  title,
}: {
  tone?: Tone | string;
  className?: string;
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-block rounded-full px-2 py-px text-[11px] leading-4 whitespace-nowrap",
        PILL[(tone as Tone) in PILL ? (tone as Tone) : "n"],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Avatar({ name, mine }: { name: string; mine?: boolean }) {
  if (!name) return null;
  return (
    <span
      title={name}
      className={cn(
        "inline-flex size-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold",
        mine ? "bg-blue-600 text-white" : "bg-blue-100 text-slate-700",
      )}
    >
      {initials(name)}
    </span>
  );
}

export function ProgressBar({ value, className }: { value: number; className?: string }) {
  return (
    <div className={cn("h-1.5 overflow-hidden rounded bg-muted", className)}>
      <i className="block h-full bg-blue-600" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

export function Visa({ children }: { children: React.ReactNode }) {
  return <span className="inline-flex items-center gap-1 text-xs whitespace-nowrap text-emerald-700">✓ {children}</span>;
}

export function Note({ tone, children, className }: { tone?: "warn" | "bad" | "crit" | "ok"; children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "my-2 rounded-lg px-3 py-2 text-[12.5px]",
        tone === "warn" && "bg-amber-50 text-amber-900",
        tone === "bad" && "bg-red-50 text-red-700",
        tone === "crit" && "bg-orange-50 text-orange-900",
        tone === "ok" && "bg-emerald-50 text-emerald-900",
        !tone && "bg-muted text-muted-foreground",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function Field({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={cn("flex flex-col gap-1", className)}>
      <span className="text-xs text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

const INPUT =
  "h-8 w-full rounded-md border border-input bg-background px-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30 disabled:cursor-not-allowed disabled:opacity-60";

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cn(INPUT, props.className)} />;
}

export function NativeSelect(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cn(INPUT, "pr-1", props.className)} />;
}

export function TextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={cn(
        "min-h-16 w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/30",
        props.className,
      )}
    />
  );
}

/** Ячейка таблицы, которая выглядит текстом и становится полем при наведении/фокусе. */
const CELL =
  "h-7 w-full rounded border border-transparent bg-transparent px-1.5 text-[13px] outline-none hover:border-input focus:border-ring focus:bg-background disabled:hover:border-transparent disabled:appearance-none disabled:opacity-100";

export function CellInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cn(CELL, props.className)} />;
}

export function CellSelect(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cn(CELL, props.className)} />;
}

export function Line({ label, value, big }: { label: React.ReactNode; value: React.ReactNode; big?: boolean }) {
  return (
    <div
      className={cn(
        "flex justify-between gap-3 py-0.5 tabular-nums",
        big && "mt-1 border-t pt-1.5 text-[15px] font-semibold",
      )}
    >
      <span>{label}</span>
      <span>{value}</span>
    </div>
  );
}

export function SectionTitle({ children, className }: { children: React.ReactNode; className?: string }) {
  return <h3 className={cn("mt-5 mb-2 flex items-center gap-2 text-sm font-semibold first:mt-0", className)}>{children}</h3>;
}

export const TABLE = "w-full border-collapse text-[13px] [&_th]:border-b [&_th]:px-1.5 [&_th]:py-1.5 [&_th]:text-left [&_th]:text-xs [&_th]:font-medium [&_th]:whitespace-nowrap [&_th]:text-muted-foreground [&_td]:border-b [&_td]:border-muted [&_td]:px-1.5 [&_td]:py-1 [&_td]:align-middle";
