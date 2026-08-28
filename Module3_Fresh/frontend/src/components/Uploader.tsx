import { useCallback, useRef, useState } from 'react'

interface Props {
  onFile: (f: File) => void
  onDemo: () => void
  busy: boolean
  uploadPct: number | null
  limits?: { max_upload_mb: number; allowed: string[] }
  demoAvailable: boolean
}

export function Uploader({ onFile, onDemo, busy, uploadPct, limits, demoAvailable }: Props) {
  const [drag, setDrag] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const handle = useCallback((files: FileList | null) => {
    if (files?.[0]) onFile(files[0])
  }, [onFile])

  return (
    <div className="animate-fade-up">
      <div
        onDragOver={e => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={e => { e.preventDefault(); setDrag(false); handle(e.dataTransfer.files) }}
        onClick={() => !busy && input.current?.click()}
        className={`card relative cursor-pointer overflow-hidden px-8 py-16 text-center
          transition-all duration-300
          ${drag ? 'border-accent bg-accent/[.06] scale-[1.01]' : 'hover:border-ink-700'}
          ${busy ? 'pointer-events-none opacity-60' : ''}`}
      >
        <input ref={input} type="file" hidden accept="video/mp4,video/quicktime,video/x-msvideo,.mp4,.mov,.avi,.m4v,.mkv"
               onChange={e => handle(e.target.files)} />

        <div className={`mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-xl
                        border border-ink-700 bg-ink-850 transition-transform duration-300
                        ${drag ? 'scale-110 border-accent' : ''}`}>
          <svg className="h-6 w-6 text-ink-300" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </div>

        <p className="text-base font-medium text-ink-100">Drag &amp; drop your video here</p>
        <p className="mt-1.5 text-sm text-ink-500">
          Supported: {limits ? limits.allowed.map(s => s.replace('.', '').toUpperCase()).join(' / ')
                             : 'MP4 / MOV / AVI'}
          {limits && <> · up to {limits.max_upload_mb} MB</>}
        </p>

        <button className="btn-ghost mt-7" disabled={busy}
                onClick={e => { e.stopPropagation(); input.current?.click() }}>
          Choose Video
        </button>

        {uploadPct !== null && (
          <div className="absolute inset-x-0 bottom-0 h-1 bg-ink-800">
            <div className="h-full bg-accent transition-[width] duration-200"
                 style={{ width: `${uploadPct}%` }} />
          </div>
        )}
      </div>

      {demoAvailable && (
        <div className="mt-4 flex items-center justify-center gap-3 text-sm">
          <span className="text-ink-500">Or evaluate with the validated sample</span>
          <button className="btn-ghost !py-1.5 !px-3.5 !text-[13px]" onClick={onDemo} disabled={busy}>
            Run Demo
          </button>
        </div>
      )}
    </div>
  )
}
