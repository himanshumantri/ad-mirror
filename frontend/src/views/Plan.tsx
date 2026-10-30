import { useState } from 'react'
import { putPlan, type Plan } from '../api'

export default function PlanView({ plan, reload }: { plan: Plan | null; reload: () => void }) {
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  async function onFile(file: File | undefined) {
    if (!file) return
    setBusy(true)
    setMessage('')
    try {
      const r = await putPlan(file)
      setMessage(`Loaded ${r.lines} lines across ${r.locations} locations.`)
      reload()
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <h2>Book stock</h2>
      <p className="hint">
        Upload the inventory export from your ERP as CSV with the columns <code>item, location, book_qty, unit_cost</code>. It
        replaces the current book stock, and its locations are the plan that clips are counted against.
      </p>
      <input type="file" accept=".csv,text/csv" disabled={busy} onChange={(e) => onFile(e.target.files?.[0])} />
      {message && <p role="status">{message}</p>}
      {plan && plan.lines.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Location</th>
              <th>Item</th>
              <th className="num">Book qty</th>
              <th className="num">Unit cost</th>
            </tr>
          </thead>
          <tbody>
            {plan.lines.map((l, i) => (
              <tr key={i}>
                <td>{l.location}</td>
                <td>{l.item}</td>
                <td className="num">{l.book_qty}</td>
                <td className="num">{l.unit_cost.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
