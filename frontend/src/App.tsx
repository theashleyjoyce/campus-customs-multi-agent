import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  approveAndPay,
  denyApproval,
  fetchApprovals,
  fetchCash,
  fetchHealth,
  fetchTeam,
  fetchTickets,
  resetBoard,
  runTicketStream,
} from './api'
import type {
  AgentState,
  AgentSummary,
  Approval,
  Cash,
  FeedEvent,
  Health,
  TeamMember,
  Ticket,
} from './types'
import './App.css'

const APPROVER = 'Ashley Joyce'

const AGENT_LABEL: Record<string, string> = {
  boss: 'Boss',
  inventory: 'Inventory',
  accounting: 'Accounting',
  facilities: 'Facilities',
  customer_service: 'Customer Service',
}

/** Turn one audit step into a readable line. Agents speak, they do not emit JSON. */
function toFeedEvent(step: Record<string, any>): FeedEvent | null {
  const agent = String(step.agent ?? '')
  const kind = String(step.kind ?? '')
  const base = { seq: Number(step.seq ?? 0), kind, agent, ticket_id: step.ticket_id, tools: [] as string[], said: '' }

  switch (kind) {
    case 'run_start':
      return { ...base, said: 'picked up the ticket' }
    case 'prompt':
      return { ...base, said: String(step.task ?? 'started working') }
    case 'model_response': {
      const tools = (step.tool_calls ?? []).map((c: any) => c.tool)
      const text = String(step.text ?? '').trim()
      if (!text && !tools.length) return null
      return { ...base, tools, said: text || (tools.length ? 'reaching for tools' : '') }
    }
    case 'tool_call':
      return { ...base, tools: [String(step.tool)], said: `called ${step.tool}` }
    case 'delegation_start':
      return { ...base, to_agent: step.to_agent, said: `asked ${AGENT_LABEL[step.to_agent] ?? step.to_agent}: ${step.task ?? ''}` }
    case 'delegation_end':
      return { ...base, to_agent: step.to_agent, said: `${AGENT_LABEL[step.to_agent] ?? step.to_agent} reported back` }
    case 'answer':
      return { ...base, said: String(step.answer ?? '') }
    case 'refusal':
      return { ...base, said: `refused: ${step.detail ?? ''}` }
    case 'error':
      return { ...base, said: `error: ${step.error ?? step.detail ?? ''}` }
    default:
      return null
  }
}

function money(n: number): string {
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [team, setTeam] = useState<TeamMember[]>([])
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [cash, setCash] = useState<Cash | null>(null)
  const [approvals, setApprovals] = useState<Approval[]>([])

  const [selected, setSelected] = useState<number | null>(null)
  const [running, setRunning] = useState<number | null>(null)
  const [feed, setFeed] = useState<FeedEvent[]>([])
  const [agentState, setAgentState] = useState<Record<string, AgentState>>({})
  const [finishedTicket, setFinishedTicket] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cashFlash, setCashFlash] = useState(false)
  const [busyApproval, setBusyApproval] = useState<number | null>(null)

  const feedEnd = useRef<HTMLDivElement>(null)
  const prevBalance = useRef<number | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [h, t, c, a] = await Promise.all([
        fetchHealth(),
        fetchTickets(),
        fetchCash(),
        fetchApprovals(),
      ])
      setHealth(h)
      setTickets(t.tickets)
      setApprovals(a.approvals)
      if (prevBalance.current !== null && c.balance !== prevBalance.current) {
        setCashFlash(true)
        window.setTimeout(() => setCashFlash(false), 1600)
      }
      prevBalance.current = c.balance
      setCash(c)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    fetchTeam()
      .then((r) => setTeam(r.agents))
      .catch(() => setTeam([]))
    void refresh()
  }, [refresh])

  // Poll only while idle. During a run the SSE stream is the source of truth.
  useEffect(() => {
    if (running !== null) return
    const id = window.setInterval(refresh, 5000)
    return () => window.clearInterval(id)
  }, [running, refresh])

  useEffect(() => {
    feedEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [feed.length])

  async function startRun(ticketId: number) {
    if (running !== null) return
    setRunning(ticketId)
    setSelected(ticketId)
    setFeed([])
    setFinishedTicket(null)
    setError(null)
    setAgentState({ boss: 'working' })

    try {
      await runTicketStream(ticketId, (step) => {
        const ev = toFeedEvent(step)
        if (!ev) return
        setFeed((f) => [...f, ev])

        if (ev.agent) {
          setAgentState((s) => ({
            ...s,
            [ev.agent]: ev.kind === 'answer' ? 'done' : 'working',
          }))
        }
        if (ev.to_agent && ev.kind === 'delegation_start') {
          setAgentState((s) => ({ ...s, [ev.to_agent as string]: 'working' }))
        }
        // An approval request mid-run should surface straight away.
        if (ev.tools.includes('request_approval')) void fetchApprovals().then((a) => setApprovals(a.approvals))
      })
      setFinishedTicket(ticketId)
      setAgentState((s) => {
        const next = { ...s }
        for (const k of Object.keys(next)) if (next[k] === 'working') next[k] = 'done'
        return next
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(null)
      await refresh()
    }
  }

  async function onApprove(id: number) {
    setBusyApproval(id)
    try {
      await approveAndPay(id, APPROVER)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyApproval(null)
    }
  }

  async function onDeny(id: number) {
    setBusyApproval(id)
    try {
      await denyApproval(id, APPROVER)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyApproval(null)
    }
  }

  async function onReset() {
    if (running !== null) return
    await resetBoard()
    setFeed([])
    setAgentState({})
    setSelected(null)
    setFinishedTicket(null)
    prevBalance.current = null
    await refresh()
  }

  /** Roll the feed up into one card per agent, for the post-run summary. */
  const summaries = useMemo<AgentSummary[]>(() => {
    const by = new Map<string, AgentSummary>()
    for (const ev of feed) {
      if (!ev.agent) continue
      const row = by.get(ev.agent) ?? { agent: ev.agent, toolCalls: [], delegatedTo: [], answer: '', turns: 0 }
      if (ev.kind === 'tool_call') for (const t of ev.tools) if (!row.toolCalls.includes(t)) row.toolCalls.push(t)
      if (ev.kind === 'model_response') row.turns += 1
      if (ev.kind === 'delegation_start' && ev.to_agent && !row.delegatedTo.includes(ev.to_agent)) {
        row.delegatedTo.push(ev.to_agent)
      }
      if (ev.kind === 'answer') row.answer = ev.said
      by.set(ev.agent, row)
    }
    return [...by.values()]
  }, [feed])

  const pending = approvals.filter((a) => a.status === 'pending')
  const decided = approvals.filter((a) => a.status !== 'pending')
  const selectedTicket = tickets.find((t) => t.id === selected) ?? null

  /** Ticket notes accumulate as "original | decision | decision". Split them
   *  so the record reads as entries rather than one unbroken paragraph. */
  const decisionLog = useMemo(() => {
    if (!selectedTicket?.notes) return []
    return selectedTicket.notes
      .split('|')
      .map((n) => n.trim())
      .filter(Boolean)
  }, [selectedTicket])

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>Campus Customs</h1>
          <span>Multi-Agent Operations</span>
        </div>

        <div className="stats">
          <div className={`stat cash${cashFlash ? ' flash' : ''}`}>
            <span className="stat-label">Checking</span>
            <strong>{cash ? money(cash.balance) : '—'}</strong>
            {cash && cash.spent > 0 && <em>{money(cash.spent)} paid out</em>}
          </div>
          <div className="stat">
            <span className="stat-label">Shop date</span>
            <strong>{health?.today ?? '—'}</strong>
          </div>
          <div className="stat">
            <span className="stat-label">Model</span>
            <strong className="mono">{health?.model ?? '—'}</strong>
          </div>
          <button className="ghost" onClick={onReset} disabled={running !== null}>
            Reset board
          </button>
        </div>
      </header>

      {error && <div className="banner error">{error}</div>}

      <main className="grid">
        {/* ------------------------------- board ------------------------------ */}
        <section className="col board">
          <h2>The board</h2>
          {tickets.length === 0 && <p className="muted">No tickets loaded.</p>}
          {tickets.map((t) => {
            const isResolved = t.status !== 'open'
            const isRunning = running === t.id
            return (
              <article
                key={t.id}
                className={`ticket${selected === t.id ? ' selected' : ''}${isResolved ? ' resolved' : ''}${isRunning ? ' running' : ''}`}
                onClick={() => setSelected(t.id)}
              >
                <div className="ticket-head">
                  <span className="ticket-id">#{t.id}</span>
                  <span className={`chip ${isResolved ? 'done' : 'open'}`}>
                    {isRunning ? 'running' : t.status}
                  </span>
                </div>
                <h3>{t.subject}</h3>
                <p className="muted">{t.requester}</p>
                {t.sku && (
                  <p className="meta">
                    <code>{t.sku}</code>
                    {t.size && <code>{t.size}</code>}
                    {t.qty && <span>× {t.qty}</span>}
                  </p>
                )}
                <button
                  className="primary"
                  disabled={running !== null}
                  onClick={(e) => {
                    e.stopPropagation()
                    void startRun(t.id)
                  }}
                >
                  {isRunning ? 'Working…' : isResolved ? 'Run again' : 'Run the team'}
                </button>
              </article>
            )
          })}
        </section>

        {/* -------------------------------- feed ------------------------------ */}
        <section className="col feed-col">
          {selectedTicket && (
            <article className={`record${selectedTicket.status !== 'open' ? ' settled' : ''}`}>
              <div className="record-head">
                <div>
                  <span className="muted small">Ticket #{selectedTicket.id}</span>
                  <h2 className="record-title">{selectedTicket.subject}</h2>
                </div>
                <span className={`chip ${selectedTicket.status === 'open' ? 'open' : 'done'}`}>
                  {selectedTicket.status}
                </span>
              </div>

              <p className="muted small record-meta">
                {selectedTicket.requester}
                {selectedTicket.sku && ` · ${selectedTicket.sku}`}
                {selectedTicket.size && ` · size ${selectedTicket.size}`}
                {selectedTicket.qty ? ` · ${selectedTicket.qty} wanted` : ''}
              </p>

              {decisionLog.length > 0 && (
                <>
                  <h3 className="record-label">
                    {decisionLog.length > 1 ? 'What was decided' : 'The ask'}
                  </h3>
                  <ol className="decisions">
                    {decisionLog.map((entry, i) => (
                      <li key={i} className={i === 0 ? 'ask' : ''}>
                        {entry}
                      </li>
                    ))}
                  </ol>
                </>
              )}
            </article>
          )}

          <h2>
            Live agent activity
            {running !== null && <span className="live">● running ticket #{running}</span>}
          </h2>

          {feed.length === 0 ? (
            <div className="empty">
              <p>Pick a ticket and press <strong>Run the team</strong>.</p>
              <p className="muted">
                The Boss reads the ticket, decides who to call, and the specialists report
                back. Every tool call shows up here as it happens.
              </p>
            </div>
          ) : (
            <div className="feed">
              {feed.map((ev, i) => (
                <div key={`${ev.seq}-${i}`} className={`line ${ev.kind}`}>
                  <span className={`who ${ev.agent}`}>{AGENT_LABEL[ev.agent] ?? ev.agent}</span>
                  <div className="what">
                    <p>{ev.said}</p>
                    {ev.tools.length > 0 && (
                      <div className="tools">
                        {ev.tools.map((t, j) => (
                          <code key={j}>{t}</code>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              <div ref={feedEnd} />
            </div>
          )}

          {finishedTicket !== null && summaries.length > 0 && (
            <div className="summary">
              <h2>
                What each agent did on ticket #{finishedTicket}
                <span className="chip done">resolved</span>
              </h2>
              <div className="summary-grid">
                {summaries.map((s) => (
                  <article key={s.agent} className="summary-card">
                    <h3>
                      <span className={`dot ${s.agent}`} />
                      {AGENT_LABEL[s.agent] ?? s.agent}
                    </h3>
                    <p className="muted small">
                      {s.turns} turn{s.turns === 1 ? '' : 's'}
                      {s.delegatedTo.length > 0 &&
                        ` · asked ${s.delegatedTo.map((d) => AGENT_LABEL[d] ?? d).join(', ')}`}
                    </p>
                    {s.toolCalls.length > 0 && (
                      <div className="tools">
                        {s.toolCalls.map((t) => (
                          <code key={t}>{t}</code>
                        ))}
                      </div>
                    )}
                    {s.answer && <p className="said">{s.answer}</p>}
                  </article>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* ------------------------------- right ------------------------------ */}
        <section className="col side">
          <h2>The team</h2>
          <div className="roster">
            {team.map((m) => {
              const state = agentState[m.name] ?? 'idle'
              return (
                <div key={m.name} className={`member ${state}`} title={m.role}>
                  <span className={`dot ${m.name} ${state}`} />
                  <div>
                    <strong>{AGENT_LABEL[m.name] ?? m.name}</strong>
                    <span className="muted small">{state}</span>
                  </div>
                </div>
              )
            })}
          </div>

          <h2>
            Waiting on you
            {pending.length > 0 && <span className="chip warn">{pending.length}</span>}
          </h2>

          {pending.length === 0 && (
            <p className="muted small">
              Nothing to approve. Agents prepare payments, they never make them.
            </p>
          )}

          {pending.map((a) => (
            <article key={a.id} className="approval">
              <div className="approval-head">
                <strong>{money(a.amount)}</strong>
                <span className="chip warn">{a.kind.replace('_', ' ')}</span>
              </div>
              <p className="said">{a.reason}</p>
              <p className="muted small">
                asked by {a.requested_by}
                {a.ticket_id ? ` · ticket #${a.ticket_id}` : ''}
              </p>
              <div className="approval-actions">
                <button
                  className="primary"
                  disabled={busyApproval === a.id}
                  onClick={() => void onApprove(a.id)}
                >
                  {busyApproval === a.id ? 'Paying…' : 'Approve and pay'}
                </button>
                <button
                  className="ghost"
                  disabled={busyApproval === a.id}
                  onClick={() => void onDeny(a.id)}
                >
                  Deny
                </button>
              </div>
            </article>
          ))}

          {decided.length > 0 && (
            <>
              <h2>Already decided</h2>
              {decided.map((a) => (
                <div key={a.id} className="decided">
                  <span className={`chip ${a.status === 'denied' ? 'bad' : 'done'}`}>{a.status}</span>
                  <span>{money(a.amount)}</span>
                  <span className="muted small">{a.decided_by ?? ''}</span>
                </div>
              ))}
            </>
          )}

          {cash && cash.payments.length > 0 && (
            <>
              <h2>Money out</h2>
              {cash.payments.map((p) => (
                <div key={p.id} className="payment">
                  <span>{money(p.amount)}</span>
                  <span className="muted small">
                    {p.kind} #{p.ref_id} · {p.approved_by}
                  </span>
                </div>
              ))}
            </>
          )}
        </section>
      </main>

    </div>
  )
}
