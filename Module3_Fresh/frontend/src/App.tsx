import { useCallback, useEffect, useState } from 'react'
import { api } from './api/client'
import { useJob } from './hooks/useJob'
import { Uploader } from './components/Uploader'
import { VideoPreview } from './components/VideoPreview'
import { Pipeline } from './components/Pipeline'
import { ActionTimeline } from './components/ActionTimeline'
import { Results } from './components/Results'
import { AdvancedSettings } from './components/AdvancedSettings'
import type { Health, Settings, VideoInfo } from './types'

type Phase = 'idle' | 'ready' | 'processing' | 'done' | 'error'

const DEFAULT_SETTINGS: Settings = {
  seed: 42, steps: 50, cfg_scale: 4, sigma_shift: 5, duration: 10,
  sample_rate: 48000, max_candidates: 3,
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [phase, setPhase] = useState<Phase>('idle')
  const [jobId, setJobId] = useState<string | null>(null)
  const [video, setVideo] = useState<VideoInfo | null>(null)
  const [filename, setFilename] = useState('')
  const [warnings, setWarnings] = useState<string[]>([])
  const [uploadPct, setUploadPct] = useState<number | null>(null)
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS)
  const [uiError, setUiError] = useState<string | null>(null)
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')

  const { status, result, actions, events, unsupported, error } = useJob(
    phase === 'processing' || phase === 'done' ? jobId : null)

  useEffect(() => { api.health().then(setHealth).catch(() => setHealth(null)) }, [])
  useEffect(() => {
    document.documentElement.classList.toggle('light', theme === 'light')
    document.documentElement.classList.toggle('dark', theme === 'dark')
  }, [theme])
  useEffect(() => { if (result) setPhase('done') }, [result])
  useEffect(() => { if (error) { setUiError(error); setPhase('error') } }, [error])

  const reset = useCallback(() => {
    setPhase('idle'); setJobId(null); setVideo(null); setFilename('')
    setWarnings([]); setUploadPct(null); setUiError(null)
  }, [])

  const onFile = useCallback(async (f: File) => {
    setUiError(null); setUploadPct(0)
    try {
      const r = await api.upload(f, p => setUploadPct(p))
      setJobId(r.job_id); setVideo(r.video); setFilename(r.original_filename)
      setWarnings(r.warnings); setPhase('ready')
    } catch (e) { setUiError((e as Error).message); setPhase('error') }
    finally { setUploadPct(null) }
  }, [])

  const onDemo = useCallback(async () => {
    setUiError(null)
    try {
      const r = await api.demo()
      setJobId(r.job_id); setVideo(r.video); setFilename(r.original_filename)
      setWarnings([r.note]); setPhase('ready')
    } catch (e) { setUiError((e as Error).message); setPhase('error') }
  }, [])

  const onGenerate = useCallback(async () => {
    if (!jobId) return
    setUiError(null)
    try { await api.process(jobId, settings); setPhase('processing') }
    catch (e) { setUiError((e as Error).message); setPhase('error') }
  }, [jobId, settings])

  const onReport = useCallback(async () => {
    if (!jobId) return
    const r = await api.report(jobId)
    const blob = new Blob([JSON.stringify(r, null, 2)], { type: 'application/json' })
    window.open(URL.createObjectURL(blob), '_blank')
  }, [jobId])

  const stages = health?.stages ?? []
  const degraded = health && (!health.ffmpeg || !health.sound_generation_env ||
                              !health.action_recognition_env || !health.moss_checkpoints)

  return (
    <div className="min-h-full">
      <header className="border-b border-ink-800/70">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/15">
              <svg className="h-4 w-4 text-accent" viewBox="0 0 24 24" fill="none"
                   stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M3 12h3l3-8 4 16 3-8h5" /></svg>
            </div>
            <span className="text-[13px] font-semibold tracking-wide text-ink-200">
              Final-Year Project
            </span>
          </div>
          <div className="flex items-center gap-3">
            {health && (
              <span className={`hidden items-center gap-1.5 text-[11px] sm:inline-flex
                ${degraded ? 'text-warn' : 'text-ink-500'}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${degraded ? 'bg-warn' : 'bg-ok'}`} />
                {degraded ? 'Degraded' : 'All systems ready'}
              </span>)}
            <button onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
                    className="rounded-lg border border-ink-700 px-2.5 py-1.5 text-[11px]
                               text-ink-400 transition-colors hover:text-ink-200">
              {theme === 'dark' ? 'Light' : 'Dark'}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 pb-24 pt-14">
        <div className="mb-12 text-center">
          <h1 className="text-3xl font-bold leading-tight tracking-tight text-ink-50
                         sm:text-[2.6rem]">
            ACTION RECOGNITION<br className="sm:hidden" /> AND SOUND GENERATION
          </h1>
          <p className="mx-auto mt-3.5 max-w-lg text-[15px] text-ink-400">
            Transform silent videos into synchronized sound
          </p>
        </div>

        {degraded && (
          <div className="card mb-6 border-warn/30 bg-warn/[.05] p-4 text-[13px] text-warn">
            Some backend components are unavailable
            {!health?.ffmpeg && ' · FFmpeg missing'}
            {!health?.action_recognition_env && ' · action-recognition environment missing'}
            {!health?.sound_generation_env && ' · sound-generation environment missing'}
            {!health?.moss_checkpoints && ' · MOSS checkpoints missing'}.
            Processing may fail until these are installed.
          </div>)}

        {uiError && (
          <div className="card mb-6 border-err/30 bg-err/[.05] p-4">
            <p className="text-sm font-medium text-err">Something went wrong</p>
            <p className="mt-1 text-[13px] leading-relaxed text-ink-300">{uiError}</p>
            <button className="btn-ghost mt-3 !py-1.5 !text-[12px]" onClick={reset}>Start over</button>
          </div>)}

        {phase === 'idle' && (
          <Uploader onFile={onFile} onDemo={onDemo} busy={uploadPct !== null}
                    uploadPct={uploadPct} limits={health?.limits}
                    demoAvailable={!!health?.demo_available} />)}

        {phase === 'ready' && video && jobId && (
          <div className="space-y-5">
            <VideoPreview src={api.previewUrl(jobId)} info={video} filename={filename}
                          warnings={warnings} onGenerate={onGenerate} onReset={reset}
                          busy={false} />
            <AdvancedSettings value={settings} onChange={setSettings} disabled={false} />
          </div>)}

        {(phase === 'processing' || phase === 'error') && status && (
          <div className="space-y-5">
            <Pipeline status={status} stages={stages}
                      generated={status.generated_audio ?? []} />
            {actions.length > 0 && (
              <ActionTimeline actions={actions} events={events} unsupported={unsupported}
                              duration={video?.duration_s ?? 0} />)}
          </div>)}

        {phase === 'done' && result && (
          <div className="space-y-5">
            <Results result={result} onReset={reset} onReport={onReport} />
            <ActionTimeline actions={actions} events={events} unsupported={unsupported}
                            duration={video?.duration_s ?? 0} />
          </div>)}
      </main>

      <footer className="border-t border-ink-800/70 py-6">
        <p className="mx-auto max-w-5xl px-6 text-center text-[11px] leading-relaxed text-ink-600">
          Module 2 · Qwen2.5-VL-3B-Instruct &nbsp;·&nbsp; Module 3 · MOSS-SoundEffect v2.0
          &nbsp;·&nbsp; 48 kHz mono &nbsp;·&nbsp; local inference on Apple Silicon (MPS)
        </p>
      </footer>
    </div>)
}
