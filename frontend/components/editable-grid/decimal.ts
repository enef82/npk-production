/**
 * Денежная арифметика для `EditableGrid` — на строках и `BigInt`, без `Number` на пути
 * ввод -> подытог -> `onChange`. Ни `parseFloat`, ни `Number()`, ни `+value` здесь нет
 * намеренно: `0.1 + 0.2` в double даёт `0.30000000000000004`, и на экране расчёта КП
 * это копейка расхождения между показанной и сохранённой суммой.
 *
 * ВТОРАЯ реализация той же арифметики, что `src/crm/calculations.py` (первая — на
 * Python, на бэкенде). Правила округления обязаны совпадать буквально, иначе стороны
 * разойдутся — не «если», а «когда»:
 *
 *   - единица округления — копейка, 2 знака;
 *   - режим — `ROUND_HALF_UP` (полкопейки вверх, от нуля), НЕ банковское `HALF_EVEN`;
 *   - квантуется КАЖДАЯ строка, а не только итог; сумма уже квантованных строк точна
 *     и повторного округления не требует.
 *
 * Основание и числовые образцы — `docs/analiz-rascheta-kp.md` §3.6 и тесты
 * `src/crm/tests/test_calculations.py` (командировка из трёх строк -> 145 500,00;
 * `10.005` -> `10.01`, где `HALF_UP` и `HALF_EVEN` расходятся). Правишь округление
 * здесь — правь и там, и наоборот.
 *
 * Компонент этим модулем только суммирует колонки с `aggregate`. Производные величины
 * (количество x цена) считает потребитель — см. `setValue` демо-страницы и, дальше,
 * экран расчёта: формула предметной области в общий компонент не просачивается.
 */

const NBSP = " ";
const ZERO = BigInt(0);
const ONE = BigInt(1);
const TEN = BigInt(10);
const TWO = BigInt(2);

// Разделители разрядов, которые может содержать ввод или уже отформатированное
// значение: любой юникод-пробел (\s покрывает обычный, неразрывный 00A0, узкий
// неразрывный 202F, тонкий 2009 и прочие). Запятая — десятичный разделитель.
const SEPARATORS = /\s/g;

function cleanInput(raw: string): string {
  return raw.replace(SEPARATORS, "").replace(",", ".");
}

function pow10(n: number): bigint {
  return TEN ** BigInt(n);
}

/**
 * Каноничная форма: `-?цифры[.цифры]`, без ведущих нулей, без хвостовых нулей дроби,
 * ноль — всегда `"0"` без знака. Вход должен уже быть валиден (см. `isValidDecimalInput`).
 */
export function normalizeDecimal(value: string): string {
  const s = cleanInput(value);
  const negative = s.startsWith("-");
  const body = negative ? s.slice(1) : s;
  const [rawInt = "", rawFrac = ""] = body.split(".");
  const int = rawInt.replace(/^0+/, "") || "0";
  const frac = rawFrac.replace(/0+$/, "");
  if (int === "0" && frac === "") return "0";
  return `${negative ? "-" : ""}${int}${frac ? `.${frac}` : ""}`;
}

/** Пустая строка, одинокий знак/точка и мусор — не число. Требуется хотя бы одна цифра. */
export function isValidDecimalInput(raw: string): boolean {
  const s = cleanInput(raw);
  if (!/\d/.test(s)) return false;
  return /^-?\d*\.?\d*$/.test(s);
}

/** Сырой ввод -> каноничная строка, либо `null`, если это не число. */
export function parseDecimalInput(raw: string): string | null {
  if (!isValidDecimalInput(raw)) return null;
  return normalizeDecimal(raw);
}

type Scaled = { mant: bigint; scale: number };

function toScaled(value: string): Scaled {
  const canonical = normalizeDecimal(value);
  const negative = canonical.startsWith("-");
  const body = negative ? canonical.slice(1) : canonical;
  const [int, frac = ""] = body.split(".");
  const digits = `${int}${frac}` || "0";
  const mant = BigInt(digits) * (negative ? -ONE : ONE);
  return { mant, scale: frac.length };
}

function fromScaled(mant: bigint, scale: number): string {
  const negative = mant < ZERO;
  let digits = (negative ? -mant : mant).toString();
  if (scale === 0) return normalizeDecimal((negative ? "-" : "") + digits);
  if (digits.length <= scale) digits = "0".repeat(scale - digits.length + 1) + digits;
  const int = digits.slice(0, digits.length - scale);
  const frac = digits.slice(digits.length - scale);
  return normalizeDecimal(`${negative ? "-" : ""}${int}.${frac}`);
}

function align(a: string, b: string): [bigint, bigint, number] {
  const x = toScaled(a);
  const y = toScaled(b);
  const scale = Math.max(x.scale, y.scale);
  return [x.mant * pow10(scale - x.scale), y.mant * pow10(scale - y.scale), scale];
}

export function addDecimal(a: string, b: string): string {
  const [x, y, scale] = align(a, b);
  return fromScaled(x + y, scale);
}

export function subtractDecimal(a: string, b: string): string {
  const [x, y, scale] = align(a, b);
  return fromScaled(x - y, scale);
}

/** Точное умножение: масштаб результата — сумма масштабов сомножителей, без округления. */
export function multiplyDecimal(a: string, b: string): string {
  const x = toScaled(a);
  const y = toScaled(b);
  return fromScaled(x.mant * y.mant, x.scale + y.scale);
}

/** Точная сумма списка. Пустые значения считаются нулём. */
export function sumDecimals(values: readonly string[]): string {
  return values.reduce<string>((acc, value) => addDecimal(acc, value || "0"), "0");
}

export function compareDecimal(a: string, b: string): -1 | 0 | 1 {
  const [x, y] = align(a, b);
  if (x < y) return -1;
  if (x > y) return 1;
  return 0;
}

/**
 * Квантование до копейки, `ROUND_HALF_UP` (полкопейки — вверх, от нуля). Совпадает с
 * `_round2` из `src/crm/calculations.py`. Результат всегда с ровно двумя знаками дроби
 * (`"10.00"`, `"-0.30"`, `"145500.00"`) — каноничная форма денег, как `Decimal` после
 * `quantize(Decimal("0.01"))` на бэкенде.
 */
export function roundMoney(value: string): string {
  const { mant, scale } = toScaled(value);
  const negative = mant < ZERO;
  let cents = negative ? -mant : mant;

  if (scale < 2) {
    cents *= pow10(2 - scale);
  } else if (scale > 2) {
    const divisor = pow10(scale - 2);
    const quotient = cents / divisor;
    const remainder = cents % divisor;
    cents = remainder * TWO >= divisor ? quotient + ONE : quotient;
  }

  const sign = negative && cents !== ZERO ? "-" : "";
  const digits = cents.toString().padStart(3, "0");
  return `${sign}${digits.slice(0, -2)}.${digits.slice(-2)}`;
}

/**
 * `база × процент / 100`, квантованное до копейки (`ROUND_HALF_UP`). Совпадает с
 * `work_line_overhead` / долевой арифметикой `src/crm/calculations.py`: накладные на
 * труд в строке расчёта = стоимость работ × процент. `ratePercent` — процент («40»),
 * не доля («0.4»). Проверяется на тех же числах, что Python-версия.
 */
export function percentOf(base: string, ratePercent: string): string {
  return roundMoney(multiplyDecimal(base || "0", multiplyDecimal(ratePercent || "0", "0.01")));
}

/**
 * Отображение: разряды целой части — неразрывным пробелом, дробь — через запятую.
 * `minFractionDigits` дотягивает дробь нулями (деньги показываем как `"1 200,00"`).
 * Тоже без `Number`.
 */
export function formatDecimalRu(
  value: string,
  options?: { minFractionDigits?: number },
): string {
  const canonical = normalizeDecimal(value);
  const negative = canonical.startsWith("-");
  const body = negative ? canonical.slice(1) : canonical;
  const [int, rawFrac = ""] = body.split(".");
  const min = options?.minFractionDigits ?? 0;
  const frac =
    rawFrac.length < min ? rawFrac + "0".repeat(min - rawFrac.length) : rawFrac;
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  return `${negative ? "-" : ""}${grouped}${frac ? `,${frac}` : ""}`;
}
