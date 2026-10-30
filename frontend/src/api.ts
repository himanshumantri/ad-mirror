export const API: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type Clip = {
  id: string
  original_name: string
  sha256: string
  size_bytes: number
  uploaded_at: string
  finished_at: string | null
  status: 'queued' | 'running' | 'done' | 'failed'
  error: string
  location: string | null
  narrated_location: string | null
  item: string | null
  machine_count: number | null
  needs_review: boolean
  reasons: string[]
  has_evidence: boolean
  transcript: string
  review: { reviewer: string; created_at: string; lines: { item: string; qty: number; note: string }[] } | null
}

export type PlanLine = { item: string; location: string; book_qty: number; unit_cost: number }
export type Plan = { locations: string[]; lines: PlanLine[] }

export type Row = {
  location: string
  item: string
  book_qty: number
  counted_qty: number | null
  variance_qty: number | null
  unit_cost: number | null
  variance_value: number | null
  status: 'match' | 'variance' | 'pending_review' | 'not_counted'
  count_source: string
  reviewer: string
  flag: string
  note: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(API + path, init)
  if (!res.ok) {
    let message = res.statusText
    try {
      const body = await res.json()
      message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* keep the status text */
    }
    throw new Error(message)
  }
  return res.json() as Promise<T>
}

export const getPlan = () => request<Plan>('/plan')
export const getClips = () => request<Clip[]>('/clips')
export const getReconciliation = () => request<Row[]>('/reconciliation')

export function putPlan(file: File) {
  const form = new FormData()
  form.append('file', file)
  return request<{ lines: number; locations: number }>('/plan', { method: 'PUT', body: form })
}

export function uploadClip(file: File, sha256: string) {
  const form = new FormData()
  form.append('file', file)
  form.append('client_sha256', sha256)
  return request<Clip>('/clips', { method: 'POST', body: form })
}

export function postReview(clipId: string, body: { reviewer: string; location?: string; lines: { item: string; qty: number; note: string }[] }) {
  return request<Clip>(`/clips/${clipId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

/** SHA-256 of the file as the device holds it, so the server can tell if the upload changed in transit. */
export async function sha256Hex(file: Blob): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}
