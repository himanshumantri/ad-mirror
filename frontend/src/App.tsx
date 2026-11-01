import { useCallback, useEffect, useState } from 'react'
import { getClips, getPlan, getReconciliation, type Clip, type Plan, type Row } from './api'
import { BLURB, DEFAULT_NAME, remember, remembered, ROLES, TABS, type Role } from './roles'
import CaptureView from './views/Capture'
import ClipsView from './views/Clips'
import PlanView from './views/Plan'
import ReconciliationView from './views/Reconciliation'

const asRole = (v: string | null): Role => (ROLES.find((r) => r === v) ?? 'Capturer')

export default function App() {
  const [role, setRole] = useState<Role>(() => asRole(remembered('role')))
  const [names, setNames] = useState<Record<Role, string>>(() =>
    Object.fromEntries(ROLES.map((r) => [r, remembered(`name-${r}`) || DEFAULT_NAME[r]])) as Record<Role, string>,
  )
  const [tab, setTab] = useState<string>(TABS[role][0])
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

  const name = names[role]
  const waiting = clips.filter((c) => c.status === 'done' && c.needs_review && !c.review).length

  function chooseRole(r: Role) {
    setRole(r)
    setTab(TABS[r][0])
    remember('role', r)
  }

  function rename(value: string) {
    setNames({ ...names, [role]: value })
    remember(`name-${role}`, value)
  }

  return (
    <>
      <header>
        <h1>LedgerEyes</h1>
        <div className="roles" role="group" aria-label="Viewing as">
          <span>Viewing as</span>
          {ROLES.map((r) => (
            <button key={r} className={r === role ? 'active' : ''} aria-pressed={r === role} onClick={() => chooseRole(r)}>
              {r}
            </button>
          ))}
          <label className="who">
            Name
            <input value={name} onChange={(e) => rename(e.target.value)} maxLength={60} />
          </label>
        </div>
        <nav aria-label="Sections">
          {TABS[role].map((t) => (
            <button key={t} className={t === tab ? 'active' : ''} aria-current={t === tab ? 'page' : undefined} onClick={() => setTab(t)}>
              {t}
              {t === 'Clips' && waiting > 0 && role !== 'Capturer' && <span className="badge">{waiting}</span>}
            </button>
          ))}
        </nav>
      </header>
      <main>
        <p className="hint">{BLURB[role]}</p>
        {error && <p className="warn">{error}</p>}
        {tab === 'Book stock' && <PlanView plan={plan} reload={reload} />}
        {tab === 'Capture' && <CaptureView hasPlan={(plan?.lines.length ?? 0) > 0} capturer={name} onUploaded={reload} />}
        {tab === 'Clips' && plan && <ClipsView clips={clips} plan={plan} role={role} name={name} reload={reload} />}
        {tab === 'Reconciliation' && <ReconciliationView rows={rows} reload={reload} />}
      </main>
    </>
  )
}
