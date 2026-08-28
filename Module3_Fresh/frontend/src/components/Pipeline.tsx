import type { JobStatus } from '../types'

interface Props {
  status: JobStatus | null
  stages: { key: string; label: string }[]
  generated: { key: string; label: string; cached: boolean }[]
}

function Icon({ state }: { state: string }) {
  if (state === 'done') return (
    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-ok/15 text-ok">
      <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20 6 9 17 4 12" /></svg>
    </span>)
  if (state === 'active') return (
    <span className="flex h-5 w-5 items-center justify-center">
      <svg className="h-4 w-4 animate-spin text-accent" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity=".2" />
        <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      </svg></span>)
  if (state === 'failed') return (
    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-err/15 text-err">
      <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           strokeWidth="3.5" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/>
        <line x1="6" y1="6" x2="18" y2="18"/></svg></span>)
  if (state === 'skipped') return (
    <span className="flex h-5 w-5 items-center justify-center text-ink-600">–</span>)
  return <span className="h-5 w-5 rounded-full border border-ink-700" />
}

export function Pipeline({ status, stages, generated }: Props) {
  const pct = status?.progress ?? 0
  const st = status?.stages ?? {}
  return (
    <div className="card animate-fade-up p-6">
      <div className="mb-5 flex items-baseline justify-between">
        <p className="label">Processing pipeline</p>
        <span className="mono text-ink-400">{pct.toFixed(0)}%</span>
      </div>

      <div className="mb-6 h-1 overflow-hidden rounded-full bg-ink-800">
        <div className="h-full rounded-full bg-accent transition-[width] duration-700 ease-out"
             style={{ width: `${Math.max(2, pct)}%` }} />
      </div>

      <ol className="space-y-1">
        {stages.map((s, i) => {
          const state = st[s.key] ?? 'pending'
          return (
            <li key={s.key}
                className={`flex items-center gap-3 rounded-lg px-2.5 py-2.5 transition-colors
                  ${state === 'active' ? 'bg-accent/[.07]' : ''}`}>
              <span className="mono w-4 shrink-0 text-ink-600">{i + 1}</span>
              <Icon state={state} />
              <span className={`text-sm transition-colors
                ${state === 'done' ? 'text-ink-300'
                  : state === 'active' ? 'font-medium text-ink-50'
                  : state === 'failed' ? 'text-err' : 'text-ink-600'}`}>
                {s.label}
              </span>
              {state === 'active' && s.key === 'foley_generation' && (
                <span className="ml-auto text-[11px] text-ink-500">
                  MOSS generation — this takes a few minutes
                </span>)}
            </li>)
        })}
      </ol>

      {generated.length > 0 && (
        <div className="mt-5 border-t border-ink-800 pt-4">
          <p className="label mb-2.5">Foley assets</p>
          <div className="flex flex-wrap gap-2">
            {generated.map(g => (
              <span key={g.key}
                    className="inline-flex items-center gap-1.5 rounded-md border border-ink-700
                               bg-ink-850 px-2.5 py-1 text-[12px] text-ink-200">
                {g.label}
                <span className={g.cached ? 'text-ok' : 'text-accent'}>
                  {g.cached ? 'cached' : 'generated'}
                </span>
              </span>))}
          </div>
        </div>)}
    </div>
  )
}
