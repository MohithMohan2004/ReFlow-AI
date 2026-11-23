/**
 * table[key], but only for the table's own entries. Keys that come from the
 * server or the URL can never reach Object.prototype ("__proto__",
 * "constructor", "toString"…).
 */
export function own<T>(table: Readonly<Record<string, T>>, key: string | null | undefined): T | undefined {
  return key != null && Object.prototype.hasOwnProperty.call(table, key) ? table[key] : undefined;
}

/** Copy of a parsed JSON object without prototype-polluting keys. */
export function safeRecord(value: unknown): Record<string, unknown> {
  const out: Record<string, unknown> = Object.create(null);
  if (value && typeof value === "object" && !Array.isArray(value)) {
    for (const [k, v] of Object.entries(value)) {
      if (k !== "__proto__" && k !== "constructor" && k !== "prototype") out[k] = v;
    }
  }
  return out;
}
