import { useState } from 'react'
import { api } from '../api/client'
import type { ResultPayload } from '../types'

interface Props { result: ResultPayload; onReset: () => void; onReport: () => void }

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <p className="label">{label}</p>
      <p className="mt-1 text-xl font-semibold tracking-tight text-ink-50">{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-ink-500">{hint}</p>}
    </div>)
}

export function Results({ result, onReset, onReport }: Props) {
  const [showDetail, setShowDetail] = useState(false)
  const c = result.counts
  const rejected = result.unsupported.filter(u => u.status === 'no_usable_foley')
  const sync = result.sync?.worst_error_ms
  const mix = result.mix ?? {}
  return (
    <div className="animate-fade-up space-y-5">
      <div className="card overflow-hidden">
        <video key={result.job_id} src={api.videoUrl(result.job_id)} controls
               className="w-full bg-black" style={{ maxHeight: '52vh' }} />
      </div>

      <div className="card p-6">
        <div className="mb-5 flex items-center gap-2.5">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-ok/15 text-ok">
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" /></svg>
          </span>
          <h2 className="text-base font-semibold text-ink-50">Sound generation complete</h2>
        </div>

        <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
          <Stat label="Actions detected" value={String(c.actions_detected ?? 0)} />
          <Stat label="Sounds generated" value={String(c.sounds_generated ?? 0)}
                hint={(c as any).sounds_rejected
                  ? `${(c as any).sounds_rejected} rejected by quality check`
                  : c.unsupported_actions ? `${c.unsupported_actions} interval(s) silent` : undefined} />
          <Stat label="Synchronization"
                value={sync == null ? '—' : `≤ ${Math.ceil(sync)} ms`}
                hint={sync == null ? undefined : 'worst alignment error'} />
          <Stat label="Audio"
                value={`${((mix as any).duration_s ?? 0).toFixed(2)}s`}
                hint={`48 kHz mono · peak ${(mix as any).peak_dbfs ?? '—'} dBFS`} />
        </div>

        <div className="mt-6 grid grid-cols-2 gap-x-8 gap-y-3 border-t border-ink-800 pt-5 sm:grid-cols-4">
          {[
            ['Clipping', (mix as any).clipped_samples === 0 ? 'None' : `${(mix as any).clipped_samples} samples`],
            ['Crest factor', `${(mix as any).crest_db ?? '—'} dB`],
            ['Video', result.render?.video_stream_copied ? 'Stream-copied' : 'Re-encoded'],
            ['Frames', String(result.render?.frames ?? '—')],
          ].map(([l, v]) => (
            <div key={l}><p className="label">{l}</p>
              <p className="mono mt-1 text-ink-200">{v}</p></div>))}
        </div>
      </div>

      <div className="card p-6">
        <p className="label mb-3">Generated sounds</p>
        <ul className="space-y-2">
          {result.generated.map(g => (
            <li key={g.key} className="flex items-center gap-2.5 text-sm">
              <span className="text-ok">✓</span>
              <span className="text-ink-100">{g.label}</span>
              {g.cached && <span className="rounded bg-ink-800 px-1.5 py-0.5 text-[10px] text-ink-400">
                reused from cache</span>}
              {(g.candidates ?? 1) > 1 && (
                <span className="rounded bg-accent/12 px-1.5 py-0.5 text-[10px] text-accent"
                      title={`${g.candidates} candidates generated; best selected by quality score`}>
                  best of {g.candidates}
                </span>)}
              {typeof g.selected_score === 'number' && g.selected_score > 0 && (
                <span className="mono text-[10px] text-ink-600">
                  quality {g.selected_score.toFixed(0)}/100
                </span>)}
            </li>))}
          {result.unsupported.map((u, i) => (
            <li key={`u${i}`} className="flex items-start gap-2.5 text-sm">
              <span className={`mt-0.5 ${u.status === 'no_usable_foley' ? 'text-warn' : 'text-ink-600'}`}>○</span>
              <span className="min-w-0">
                <span className="capitalize text-ink-200">{u.action}</span>
                <span className="text-ink-500">
                  {u.status === 'no_usable_foley' ? ' — No usable Foley generated' : ` — ${u.reason}`}
                </span>
                {u.status === 'no_usable_foley' && (
                  <span className="mt-0.5 block text-[12px] leading-relaxed text-ink-500">
                    Reason: generated audio failed quality validation.<br />
                    The interval was intentionally left silent.
                  </span>)}
              </span>
            </li>))}
        </ul>

        {rejected.length > 0 && (
          <div className="mt-4 border-t border-ink-800 pt-4">
            <button onClick={() => setShowDetail(v => !v)}
                    className="text-[12px] text-ink-500 transition-colors hover:text-ink-300">
              {showDetail ? 'Hide' : 'Show'} quality measurements
            </button>
            {showDetail && (
              <div className="mt-3 space-y-3">
                {rejected.map((u, i) => (
                  <div key={i} className="rounded-lg border border-ink-800 bg-ink-950/50 p-3">
                    <p className="mb-2 text-[12px] font-medium capitalize text-ink-300">{u.action}</p>
                    {u.metrics && (
                      <dl className="grid grid-cols-2 gap-x-5 gap-y-1.5 sm:grid-cols-5">
                        {[['Peak', `${u.metrics.peak_dbfs} dBFS`],
                          ['Dynamic range', `${u.metrics.dynamic_range_db} dB`],
                          ['Effective bits', `${u.metrics.effective_bits} / 16`],
                          ['Harmonic ratio', `${u.metrics.harmonic_ratio}`],
                          ['Gain needed', `${u.metrics.required_gain_db > 0 ? '+' : ''}${u.metrics.required_gain_db} dB`],
                        ].map(([k, v]) => (
                          <div key={k}>
                            <dt className="label !text-[10px]">{k}</dt>
                            <dd className="mono mt-0.5 text-ink-300">{v}</dd>
                          </div>))}
                      </dl>)}
                    {u.candidates_tried && u.candidates_tried > 1 && (
                      <p className="mt-2 text-[11px] text-ink-500">
                        {u.candidates_tried} candidates were generated with different seeds;
                        none passed the quality check.
                      </p>)}
                    {u.detail && (
                      <p className="mt-2.5 text-[11px] leading-relaxed text-ink-600">{u.detail}</p>)}
                  </div>))}
              </div>)}
          </div>)}
      </div>

      <div className="flex flex-wrap gap-3">
        <a className="btn-primary" href={api.downloadUrl(result.job_id)} download>
          Download Final Video
        </a>
        <a className="btn-ghost" href={api.audioUrl(result.job_id)} download>
          Download Audio
        </a>
        <button className="btn-ghost" onClick={onReport}>View Processing Report</button>
        <button className="btn-ghost" onClick={onReset}>Process another video</button>
      </div>
    </div>)
}
