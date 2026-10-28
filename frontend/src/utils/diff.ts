// Сравнение секций настроек: в PUT уходят только изменённые ключи

/** Глубокое сравнение через JSON (достаточно для плоских объектов настроек) */
export function sameValue(a: unknown, b: unknown): boolean {
  return JSON.stringify(a ?? null) === JSON.stringify(b ?? null)
}

/** Возвращает объект только с теми ключами из keys, значения которых отличаются от original */
export function changedKeys<T extends object, K extends keyof T>(original: T, current: T, keys: readonly K[]): Partial<Pick<T, K>> {
  const result: Partial<Pick<T, K>> = {}
  for (const key of keys) {
    if (!sameValue(original[key], current[key])) result[key] = current[key]
  }
  return result
}
