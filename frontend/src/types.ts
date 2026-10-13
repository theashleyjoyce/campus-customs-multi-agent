export type TicketStatus = 'open' | 'waiting' | 'closed' | 'resolved'
export type AgentName = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'
export type AgentState = 'idle' | 'working' | 'done'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  sku: string | null
  size: string | null
  qty: number | null
  lease_id: number | null
  invoice_id: number | null
  status: TicketStatus
  notes: string | null
  created_at: string
}

export interface TeamMember {
  name: AgentName
  role: string
}

export interface Approval {
  id: number
  ticket_id: number | null
  kind: 'invoice' | 'rent' | 'purchase_order'
  ref_id: number
  amount: number
  reason: string
  requested_by: string
  requested_at: string
  status: 'pending' | 'approved' | 'denied' | 'paid'
  decided_by: string | null
  decided_at: string | null
}

export interface Payment {
  id: number
  kind: string
  ref_id: number
  amount: number
  account: string
  paid_at: string
  approved_by: string
}

export interface Cash {
  ok: boolean
  today: string
  balance: number
  as_of: string
  spent: number
  payments: Payment[]
}

export interface Health {
  ok: boolean
  model: string
  database: string
  today: string
  open_tickets: number
  cash: number
  tools: number
}

/** One line of the live feed, built from an SSE step. */
export interface FeedEvent {
  seq: number
  kind: string
  agent: string
  ticket_id?: number | null
  said: string
  tools: string[]
  to_agent?: string
}

/** What one agent did on a ticket, rolled up for the summary. */
export interface AgentSummary {
  agent: string
  toolCalls: string[]
  delegatedTo: string[]
  answer: string
  turns: number
}
