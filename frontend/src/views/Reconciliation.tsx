import { API, type Row } from '../api'

const money = (v: number | null) => (v === null ? '' : v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
const signed = (v: number | null) => (v === null ? '' : v > 0 ? `+${v}` : String(v))

export default function ReconciliationView({ rows, reload }: { rows: Row[]; reload: () => void }) {
  const net = rows.reduce((sum, r) => sum + (r.status === 'variance' ? (r.variance_value ?? 0) : 0), 0)
  const pending = rows.filter((r) => r.status === 'pending_review').length

  return (
    <section>
      <h2>Reconciliation</h2>
      <p className="hint">
        Counted against book stock. Only rows marked <em>variance</em> reach the adjustments file; rows waiting for review or not counted never do.
      </p>
      <p>
        <button onClick={reload}>Refresh</button>{' '}
        <a href={`${API}/reconciliation.csv`}>Download reconciliation.csv</a> · <a href={`${API}/proposed_adjustments.csv`}>Download proposed_adjustments.csv</a>
      </p>
      <p>
        Net variance on confirmed rows: <strong>{money(net)}</strong>
        {pending > 0 && <> · {pending} row(s) pending review</>}
      </p>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>Location</th>
              <th>Item</th>
              <th className="num">Book</th>
              <th className="num">Counted</th>
              <th className="num">Variance</th>
              <th className="num">Value</th>
              <th>Status</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className={`status-${r.status}`}>
                <td>{r.location}</td>
                <td>{r.item}</td>
                <td className="num">{r.book_qty}</td>
                <td className="num">{r.counted_qty ?? ''}</td>
                <td className="num">{signed(r.variance_qty)}</td>
                <td className="num">{money(r.variance_value)}</td>
                <td>
                  {r.status.replace('_', ' ')}
                  {r.flag && <div className="flag">{r.flag}</div>}
                </td>
                <td>{r.count_source === 'reviewed' ? `reviewed by ${r.reviewer}` : r.count_source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
