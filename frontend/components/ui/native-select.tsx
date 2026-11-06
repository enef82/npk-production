import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Обычный `<select>` в стиле полей ввода — для плотных форм (строки разноски, исполнители
 * ремонта), где выпадающий список base-ui с порталом на каждую строку тяжёл и неудобен
 * для клавиатуры. Значение — всегда строка, пустая строка — «не выбрано».
 */
function NativeSelect({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      data-slot="native-select"
      className={cn(
        "h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30",
        className,
      )}
      {...props}
    />
  );
}

export { NativeSelect };
