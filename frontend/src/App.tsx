import { useCallback, useEffect, useState } from 'react'
import { getClips, getPlan, getReconciliation, type Clip, type Plan, type Row } from './api'
import CaptureView from './views/Capture'
import ClipsView from './views/Clips'
import PlanView from './views/Plan'
import ReconciliationView from './views/Reconciliation'

const TABS = ['Book stock', 'Capture', 'Clips', 'Reconciliation'] as const
type Tab = (typeof TABS)[number]

export default function App() {
  const [tab, setTab] = useState<Tab>('Book stock')
  const [plan, setPlan] = useState<Plan | null>(null)
  const [clips, setClips] = useState<Clip[]>([])
  const [rows, setRows] = useState<Row[]>([])
  const [error, setError] = useState('')

  const reload = useCallback(async () => {
    try {
      const [p, c, r] = await Promise.all([getPlan(), getClips(), getReconciliation()])
      setPlan(p)
      setClips(c)
      setRows(r)
      setError('')
    } catch (e) {
      setError(`Cannot reach the API: ${e instanceof Error ? e.message : String(e)}`)
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  // Follow clips that are still being counted.
  const working = clips.some((c) => c.status === 'queued' || c.status === 'running')
  useEffect(() => {
    if (!working) return
    const t = setInterval(() => void reload(), 3000)
    return () => clearInterval(t)
  }, [working, reload])

  const waiting = clips.filter((c) => c.status === 'done' && c.needs_review && !c.review).length

  return (
    <>
      <header>
        <h1>LedgerEyes</h1>
        <nav aria-label="Sections">
          {TABS.map((t) => (
            <button key={t} className={t === tab ? 'active' : ''} aria-current={t === tab ? 'page' : undefined} onClick={() => setTab(t)}>
              {t}
              {t === 'Clips' && waiting > 0 && <span className="badge">{waiting}</span>}
            </button>
          ))}
        </nav>
      </header>
      <main>
        {error && <p className="warn">{error}</p>}
        {tab === 'Book stock' && <PlanView plan={plan} reload={reload} />}
        {tab === 'Capture' && <CaptureView hasPlan={(plan?.lines.length ?? 0) > 0} onUploaded={reload} />}
        {tab === 'Clips' && plan && <ClipsView clips={clips} plan={plan} reload={reload} />}
        {tab === 'Reconciliation' && <ReconciliationView rows={rows} reload={reload} />}
      </main>
    </>
  )
}
