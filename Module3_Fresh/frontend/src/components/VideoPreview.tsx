import type { VideoInfo } from '../types'

interface Props {
  src: string; info: VideoInfo; filename: string
  warnings: string[]; onGenerate: () => void; onReset: () => void; busy: boolean
}

const fmtSize = (b: number) =>
  b > 1e9 ? `${(b / 1e9).toFixed(2)} GB` : `${(b / 1e6).toFixed(1)} MB`

export function VideoPreview({ src, info, filename, warnings, onGenerate, onReset, busy }: Props) {
  const fields = [
    { label: 'File', value: filename },
    { label: 'Duration', value: `${info.duration_s.toFixed(2)} seconds` },
    { label: 'Resolution', value: `${info.width} × ${info.height}` },
    { label: 'Size', value: fmtSize(info.size_bytes) },
  ]
  return (
    <div className="animate-fade-up space-y-5">
      <div className="card overflow-hidden">
        <video src={src} controls className="w-full bg-black" style={{ maxHeight: '52vh' }} />
      </div>

      <div className="card p-6">
        <p className="label mb-4">Video preview</p>
        <dl className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-4">
          {fields.map(f => (
            <div key={f.label}>
              <dt className="label">{f.label}</dt>
              <dd className="mt-1 truncate text-sm text-ink-100" title={f.value}>{f.value}</dd>
            </div>
          ))}
        </dl>

        <div className="mt-5 flex items-center gap-2 border-t border-ink-800 pt-5">
          {info.has_audio ? (
            <span className="inline-flex items-center gap-2 rounded-md bg-warn/10 px-2.5 py-1
                             text-[12px] font-medium text-warn">
              Audio track present — it will be ignored
            </span>
          ) : (
            <span className="inline-flex items-center gap-2 rounded-md bg-ok/10 px-2.5 py-1
                             text-[12px] font-medium text-ok">
              No audio detected ✓
            </span>
          )}
        </div>

        {warnings.length > 0 && (
          <ul className="mt-4 space-y-1.5">
            {warnings.map((w, i) => (
              <li key={i} className="text-[13px] leading-relaxed text-ink-400">· {w}</li>
            ))}
          </ul>
        )}

        <div className="mt-6 flex flex-wrap gap-3">
          <button className="btn-primary" onClick={onGenerate} disabled={busy}>
            Generate Sound
          </button>
          <button className="btn-ghost" onClick={onReset} disabled={busy}>
            Choose another video
          </button>
        </div>
      </div>
    </div>
  )
}
