import { useState } from 'react'
import { sha256Hex, uploadClip, type Clip } from '../api'

type Step = 'idle' | 'hashing' | 'uploading' | 'done' | 'error'

export default function CaptureView({ hasPlan, onUploaded }: { hasPlan: boolean; onUploaded: () => void }) {
  const [step, setStep] = useState<Step>('idle')
  const [error, setError] = useState('')
  const [clip, setClip] = useState<Clip | null>(null)

  async function onFile(file: File | undefined) {
    if (!file) return
    setError('')
    setClip(null)
    try {
      setStep('hashing')
      const hash = await sha256Hex(file)
      setStep('uploading')
      setClip(await uploadClip(file, hash))
      setStep('done')
      onUploaded()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setStep('error')
    }
  }

  const busy = step === 'hashing' || step === 'uploading'

  return (
    <section>
      <h2>Capture a shelf</h2>
      {!hasPlan && <p className="warn">Upload the book stock first (Book stock tab).</p>}
      <ol className="steps">
        <li>
          Film <strong>one shelf face</strong> per clip, slowly, with the phone held the way it will be reviewed.
        </li>
        <li>
          Say the location first, for example <em>"Aisle A1, shelf B2"</em>, then the item names.
        </li>
        <li>Keep every carton in view and do not cover labels.</li>
      </ol>
      <input
        type="file"
        accept="video/*"
        capture="environment"
        disabled={!hasPlan || busy}
        onChange={(e) => {
          void onFile(e.target.files?.[0])
          e.target.value = ''
        }}
      />
      {step === 'hashing' && <p role="status">Fingerprinting the video on this device…</p>}
      {step === 'uploading' && <p role="status">Uploading…</p>}
      {step === 'error' && <p className="warn">{error}</p>}
      {step === 'done' && clip && (
        <p role="status">
          Received <strong>{clip.original_name}</strong> ({(clip.size_bytes / 1e6).toFixed(1)} MB). The server confirmed the same fingerprint:{' '}
          <code>{clip.sha256.slice(0, 12)}…</code>. Counting has started; follow it in the Clips tab.
        </p>
      )}
    </section>
  )
}
