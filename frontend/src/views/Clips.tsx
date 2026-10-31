import { useState } from 'react'
import { API, type Clip, type Plan } from '../api'
import Investigate from './Investigate'
import ReviewForm from './ReviewForm'

function statusLabel(c: Clip): { text: string; tone: string } {
  if (c.status === 'failed') return { text: 'Failed', tone: 'bad' }
  if (c.status !== 'done') return { text: c.status === 'queued' ? 'Queued' : 'Counting…', tone: 'wait' }
  if (c.review) return { text: 'Reviewed', tone: 'ok' }
  return c.needs_review ? { text: 'Needs review', tone: 'warn' } : { text: 'Auto-passed', tone: 'ok' }
}

export default function ClipsView({ clips, plan, reload }: { clips: Clip[]; plan: Plan; reload: () => void }) {
  const [open, setOpen] = useState<string | null>(null)
  const queue = clips.filter((c) => c.status === 'done' && c.needs_review && !c.review).length

  return (
    <section>
      <h2>Clips</h2>
      <p className="hint">{queue > 0 ? `${queue} clip(s) need a reviewer's count before they reach the reconciliation.` : 'Nothing waiting for review.'}</p>
      {clips.length === 0 && <p>No clips yet.</p>}
      <ul className="clips">
        {clips.map((c) => {
          const st = statusLabel(c)
          const isOpen = open === c.id
          return (
            <li key={c.id}>
              <button className="row" onClick={() => setOpen(isOpen ? null : c.id)} aria-expanded={isOpen}>
                <span className="name">{c.original_name}</span>
                <span>{c.location ?? 'location unknown'}</span>
                <span className="num">{c.review ? c.review.lines.reduce((n, l) => n + l.qty, 0) : (c.machine_count ?? '–')}</span>
                <span className={`tag ${st.tone}`}>{st.text}</span>
              </button>
              {isOpen && (
                <div className="detail">
                  {c.status === 'failed' && <p className="warn">{c.error}</p>}
                  {c.reasons.length > 0 && (
                    <ul>
                      {c.reasons.map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ul>
                  )}
                  {c.transcript && <p className="hint">Narration: “{c.transcript}”</p>}
                  <p className="hint">
                    Fingerprint <code>{c.sha256.slice(0, 16)}…</code> · received {new Date(c.uploaded_at).toLocaleString()}
                  </p>
                  {c.has_evidence && (
                    <figure>
                      <img src={`${API}/clips/${c.id}/evidence`} alt="Evidence frame with the counted cartons outlined" />
                      <figcaption>Green: counted. Orange: disputed. Blue ?: carton without a box.</figcaption>
                    </figure>
                  )}
                  {c.review && (
                    <p>
                      Reviewed by {c.review.reviewer}: {c.review.lines.map((l) => `${l.item} ${l.qty}`).join(', ')}
                    </p>
                  )}
                  {c.status === 'done' && (
                    <details className="inv">
                      <summary>Investigate with SAM</summary>
                      <Investigate key={c.id} clip={c} plan={plan} onResolved={reload} />
                    </details>
                  )}
                  {c.status === 'done' && <ReviewForm key={`${c.id}-${c.review?.created_at ?? 'new'}`} clip={c} plan={plan} onSaved={reload} />}
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
