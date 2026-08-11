/** Snowflake / entity ID — always treat as string in the browser. */
export type EntityId = string

export function sid(id: unknown): string {
  if (id == null) return ''
  return String(id)
}

export function isValidEntityId(id: unknown): boolean {
  return /^\d{1,20}$/.test(sid(id))
}

/**
 * Quote JSON integers with ≥16 digits so JSON.parse does not lose Snowflake precision.
 * Backend may still emit numeric Longs until Jackson ToStringSerializer is deployed.
 */
export function parseJsonPreserveIds<T = unknown>(text: string): T {
  const quoted = text.replace(/([:\[,\s])(-?\d{16,})(?=\s*[,\]}])/g, '$1"$2"')
  return JSON.parse(quoted) as T
}
