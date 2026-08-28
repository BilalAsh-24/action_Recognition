import { useState } from 'react'
import type { Settings } from '../types'

interface Props { value: Settings; onChange: (s: Settings) => void; disabled: boolean }

const FIELDS: { key: keyof Settings; label: string; min: number; max: number;
                step: number; hint: string }[] = [
  { key: 'seed',        label: 'Seed',           min: 0,    max: 999999, step: 1,   hint: 'reproducibility' },
  { key: 'steps',       label: 'Inference steps',min: 10,   max: 150,    step: 1,   hint: 'quality vs time' },
  { key: 'cfg_scale',   label: 'CFG scale',      min: 1,    max: 8,      step: 0.5, hint: 'prompt adherence' },
  { key: 'sigma_shift', label: 'Sigma shift',    min: 0,    max: 10,     step: 0.5, hint: 'flow schedule' },
  { key: 'duration',    label: 'Duration (s)',   min: 1,    max: 30,     step: 1,   hint: 'generated length' },
  { key: 'max_candidates', label: 'Max candidates', min: 1, max: 5,      step: 1,   hint: 'retries on failure' },
]

export function AdvancedSettings({ value, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false)
  return (
    <div className="card overflow-hidden">
      <button onClick={() => setOpen(o => !o)}
              className="flex w-full items-center justify-between px-6 py-4 text-left
                         transition-colors hover:bg-ink-850/50">
        <span className="label">Advanced settings</span>
        <span className={`text-ink-500 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}>
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               strokeWidth="2" strokeLinecap="round"><polyline points="6 9 12 15 18 9" /></svg>
        </span>
      </button>
      {open && (
        <div className="border-t border-ink-800 px-6 py-5">
          <p className="mb-4 text-[12px] leading-relaxed text-ink-500">
            Defaults are the validated MOSS-SoundEffect v2.0 settings. Changing them
            produces a different cache entry, so a new generation will run.
          </p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">
            {FIELDS.map(f => (
              <label key={f.key} className="block">
                <span className="label">{f.label}</span>
                <input type="number" disabled={disabled}
                       min={f.min} max={f.max} step={f.step}
                       value={value[f.key] as number}
                       onChange={e => onChange({ ...value, [f.key]: Number(e.target.value) })}
                       className="mono mt-1.5 w-full rounded-lg border border-ink-700 bg-ink-850
                                  px-3 py-2 text-ink-100 outline-none transition-colors
                                  focus:border-accent disabled:opacity-50" />
                <span className="mt-1 block text-[11px] text-ink-600">{f.hint}</span>
              </label>))}
            <label className="block">
              <span className="label">Sample rate</span>
              <input readOnly value="48000 Hz"
                     className="mono mt-1.5 w-full rounded-lg border border-ink-800 bg-ink-900
                                px-3 py-2 text-ink-500 outline-none" />
              <span className="mt-1 block text-[11px] text-ink-600">fixed by the model</span>
            </label>
          </div>
        </div>)}
    </div>)
}
