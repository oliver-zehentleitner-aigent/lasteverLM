/** Base URL of the API gateway, set at build time. Empty means same origin,
 *  which is the deployed case: ingress-nginx routes the three /api prefixes. */
export const API_BASE_URL: string = (import.meta.env.API_BASE_URL ?? '').replace(/\/$/, '')

export const INGEST_PREFIX = `${API_BASE_URL}/api/ingest`
export const RAG_PREFIX = `${API_BASE_URL}/api/rag`
export const ACCOUNT_PREFIX = `${API_BASE_URL}/api/account`

/** The admin endpoints' exact shapes are owned by the account service and not
 *  final yet; until they are, the admin pages run against an in-memory mock. */
export const ADMIN_MOCK: boolean = import.meta.env.VITE_ADMIN_MOCK === 'true'

/** How often lists are refreshed while an item is still processing. */
export const SOURCE_POLL_INTERVAL_MS = 2000
export const OUTPUT_POLL_INTERVAL_MS = 3000
