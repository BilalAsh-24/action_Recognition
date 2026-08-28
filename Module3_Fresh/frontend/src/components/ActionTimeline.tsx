import type { ActionRow, VisualEvent, Unsupported } from '../types'

const PALETTE = ['#4f7cff', '#3fbf7f', '#e0a33e', '#b47ce0', '#e07a5f', '#4fc3d9']

interface Props {
  actions: ActionRow[]; events: VisualEvent[];
  unsupported: Unsupported[]; duration: number
}

export function ActionTimeline({ actions, events, unsupported, duration }: Props) {
  if (!actions.length) return null
  const colour = (i: number) => PALETTE[i % PALETTE.length]
  const unsupportedSet = new Set(unsupported.map(u => `${u.action}@${u.start}`))
  const rejectedSet = new Set(unsupported.filter(u => u.status === 'no_usable_foley')
                                        .map(u => `${u.action}@${u.start}`))
  const d = duration || Math.max(...actions.map(a => a.end), 1)

  return (
    <div className="card animate-fade-up p-6">
      <p className="label mb-4">Action timeline</p>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-sm">
          <thead>
            <tr className="border-b border-ink-800 text-left">
              {['Action', 'Start', 'End', 'Confidence', 'Foley'].map(h => (
                <th key={h} className="pb-2.5 label font-medium">{h}</th>))}
            </tr>
          </thead>
          <tbody>
            {actions.map((a, i) => {
              const noFoley = unsupportedSet.has(`${a.action}@${a.start}`)
              return (
                <tr key={i} className="border-b border-ink-850/70 last:border-0">
                  <td className="py-2.5">
                    <span className="inline-flex items-center gap-2.5">
                      <span className="h-2.5 w-2.5 shrink-0 rounded-sm"
                            style={{ background: noFoley ? '#3d434e' : colour(i) }} />
                      <span className="capitalize text-ink-100">{a.action}</span>
                    </span>
                  </td>
                  <td className="mono py-2.5 text-ink-300">{a.start.toFixed(2)}s</td>
                  <td className="mono py-2.5 text-ink-300">{a.end.toFixed(2)}s</td>
                  <td className="py-2.5">
                    <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${
                      a.confidence === 'High' ? 'bg-ok/12 text-ok' : 'bg-warn/12 text-warn'}`}>
                      {a.confidence}
                    </span>
                  </td>
                  <td className="py-2.5 text-[12px]">
                    {rejectedSet.has(`${a.action}@${a.start}`)
                      ? <span className="text-warn" title="Generated audio failed quality validation">rejected</span>
                      : noFoley ? <span className="text-ink-500">none</span>
                                : <span className="text-ok">✓</span>}
                  </td>
                </tr>)
            })}
          </tbody>
        </table>
      </div>

      {/* visual timeline */}
      <div className="mt-6">
        <div className="relative h-11 overflow-hidden rounded-lg bg-ink-850">
          {actions.map((a, i) => {
            const noFoley = unsupportedSet.has(`${a.action}@${a.start}`)
            return (
              <div key={i}
                   title={`${a.action} · ${a.start.toFixed(2)}–${a.end.toFixed(2)}s`}
                   className="group absolute inset-y-0 flex items-center justify-center
                              overflow-hidden border-r border-ink-950/40 transition-opacity
                              hover:opacity-90"
                   style={{ left: `${(a.start / d) * 100}%`,
                            width: `${((a.end - a.start) / d) * 100}%`,
                            background: noFoley ? '#2a2f38' : colour(i),
                            opacity: noFoley ? 0.55 : 0.88 }}>
                <span className="truncate px-1.5 text-[10px] font-medium capitalize text-white/95">
                  {a.action}
                </span>
              </div>)
          })}
          {/* visual event markers */}
          {events.map((e, i) => (
            <div key={i} title={`${e.kind} @ ${e.t_s.toFixed(3)}s`}
                 className="absolute top-0 h-full w-px bg-white/85"
                 style={{ left: `${(e.t_s / d) * 100}%` }}>
              <span className="absolute -top-0.5 left-1/2 h-1.5 w-1.5 -translate-x-1/2
                               rounded-full bg-white" />
            </div>))}
        </div>
        <div className="mono mt-1.5 flex justify-between text-[10px] text-ink-600">
          <span>0.00s</span><span>{(d / 2).toFixed(2)}s</span><span>{d.toFixed(2)}s</span>
        </div>
        {events.length > 0 && (
          <p className="mt-2.5 text-[12px] text-ink-500">
            White markers are <span className="text-ink-300">visual events</span> —
            the exact frames where sound is anchored, detected independently of the
            action-label boundaries.
          </p>)}
      </div>

      {unsupported.length > 0 && (
        <div className="mt-5 border-t border-ink-800 pt-4">
          <p className="label mb-2">Intervals left silent</p>
          <ul className="space-y-1.5">
            {unsupported.map((u, i) => (
              <li key={i} className="text-[13px] text-ink-400">
                <span className="capitalize text-ink-300">{u.action}</span>
                <span className="mono text-ink-600"> ({u.start.toFixed(2)}–{u.end.toFixed(2)}s)</span>
                {' — '}{u.reason}
              </li>))}
          </ul>
        </div>)}
    </div>
  )
}
