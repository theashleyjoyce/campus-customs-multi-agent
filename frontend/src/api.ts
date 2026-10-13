import type { Approval, Cash, Health, Ticket, TeamMember } from './types'

/** The backend runs on 8000. The Vite page is a different origin, so the
 *  backend allows this origin explicitly rather than relying on a proxy. */
const API = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`)
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json()
}

async function readError(res: Response): Promise<string> {
  try {
    const data = await res.json()
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail)) return data.detail.map((d: { msg: string }) => d.msg).join(', ')
    return JSON.stringify(data)
  } catch {
    return `HTTP ${res.status}`
  }
}

export const fetchHealth = () => get<Health>('/api/health')
export const fetchTeam = () => get<{ agents: TeamMember[] }>('/api/team')
export const fetchTickets = () => get<{ tickets: Ticket[] }>('/api/tickets')
export const fetchCash = () => get<Cash>('/api/cash')
export const fetchApprovals = () => get<{ approvals: Approval[] }>('/api/approvals?status=all')
export const resetBoard = () => post<{ ok: boolean }>('/api/reset')

/** A human clicks approve. This is the call that actually moves money. */
export const approveAndPay = (id: number, decidedBy: string) =>
  post<{ ok: boolean; paid: number; balance_after: number }>(`/api/approvals/${id}/approve`, {
    decision: 'approved',
    decided_by: decidedBy,
  })

export const denyApproval = (id: number, decidedBy: string) =>
  post<{ ok: boolean }>(`/api/approvals/${id}/decide`, {
    decision: 'denied',
    decided_by: decidedBy,
  })

/** Run the team on one ticket, streaming each step as it happens. */
export async function runTicketStream(
  ticketId: number,
  onStep: (step: Record<string, unknown>) => void,
): Promise<void> {
  const res = await fetch(`${API}/api/run/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticket_id: ticketId }),
  })
  if (!res.ok || !res.body) throw new Error(await readError(res))

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() || ''
    for (const block of blocks) {
      const dataLine = block.split('\n').find((l) => l.startsWith('data: '))
      if (!dataLine) continue
      try {
        onStep(JSON.parse(dataLine.slice(6)))
      } catch {
        // A malformed frame should not kill the stream.
      }
    }
  }
}
