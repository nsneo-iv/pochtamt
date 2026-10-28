// Спам-фильтр и антивирус (только суперадмин): бэкенд проксирует контроллер Rspamd.
// 502 от бэкенда означает, что Rspamd недоступен — переводим в понятную ошибку.
import { ApiError, http, seg } from './client'
import type {
  Antivirus,
  FilterActions,
  FilterHistoryQuery,
  FilterHistoryRow,
  FilterList,
  FilterListId,
  FilterOverview,
  FilterSymbol,
  FilterSymbolUpdate,
} from './types'

/** Оборачивает запрос: 502 → «Rspamd недоступен» */
async function viaRspamd<T>(request: Promise<T>): Promise<T> {
  try {
    return await request
  } catch (e) {
    if (e instanceof ApiError && e.status === 502) {
      throw new ApiError(502, 'Rspamd недоступен')
    }
    throw e
  }
}

export function getFilterOverview(): Promise<FilterOverview> {
  return viaRspamd(http.get<FilterOverview>('/filter/overview'))
}

export function getFilterActions(): Promise<FilterActions> {
  return viaRspamd(http.get<FilterActions>('/filter/actions'))
}

/** Пороги должны возрастать: greylist < add_header < reject */
export function updateFilterActions(data: FilterActions): Promise<FilterActions> {
  return viaRspamd(http.put<FilterActions>('/filter/actions', data))
}

export function listFilterSymbols(q?: string): Promise<FilterSymbol[]> {
  return viaRspamd(http.get<FilterSymbol[]>('/filter/symbols', { q }))
}

/** Отправлять только изменённые символы */
export function updateFilterSymbols(data: FilterSymbolUpdate[]): Promise<void> {
  return viaRspamd(http.put<void>('/filter/symbols', data))
}

export function listFilterLists(): Promise<FilterList[]> {
  return viaRspamd(http.get<FilterList[]>('/filter/lists'))
}

export function updateFilterList(id: FilterListId, entries: string[]): Promise<FilterList> {
  return viaRspamd(http.put<FilterList>(`/filter/lists/${seg(id)}`, { entries }))
}

export function listFilterHistory(query: FilterHistoryQuery = {}): Promise<FilterHistoryRow[]> {
  return viaRspamd(http.get<FilterHistoryRow[]>('/filter/history', { limit: query.limit, action: query.action, q: query.q }))
}

export function getAntivirus(): Promise<Antivirus> {
  return viaRspamd(http.get<Antivirus>('/filter/antivirus'))
}

/** 202 — перезапуск freshclam запрошен, обновление идёт в фоне */
export function requestAntivirusUpdate(): Promise<void> {
  return viaRspamd(http.post<void>('/filter/antivirus/update'))
}
