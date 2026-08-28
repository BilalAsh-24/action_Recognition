import type { Health, JobStatus, ResultPayload, VideoInfo, ActionRow,
              VisualEvent, Unsupported, Settings } from '../types'

const BASE = '/api'

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = `Request failed (${r.status})`
    try { const d = await r.json(); msg = d.detail ?? d.message ?? msg } catch { /* ignore */ }
    throw new Error(msg)
  }
  return r.json() as Promise<T>
}

export const api = {
  health: () => fetch(`${BASE}/health`).then(j<Health>),

  upload: (file: File, onProgress?: (pct: number) => void) =>
    new Promise<{ job_id: string; video: VideoInfo; warnings: string[]; original_filename: string }>(
      (resolve, reject) => {
        const fd = new FormData(); fd.append('file', file)
        const xhr = new XMLHttpRequest()
        xhr.open('POST', `${BASE}/upload`)
        xhr.upload.onprogress = e => {
          if (e.lengthComputable && onProgress) onProgress((e.loaded / e.total) * 100)
        }
        xhr.onload = () => {
          try {
            const d = JSON.parse(xhr.responseText)
            xhr.status >= 200 && xhr.status < 300 ? resolve(d)
              : reject(new Error(d.detail ?? 'Upload failed'))
          } catch { reject(new Error('Upload failed')) }
        }
        xhr.onerror = () => reject(new Error('Network error during upload'))
        xhr.send(fd)
      }),

  demo: () => fetch(`${BASE}/demo`, { method: 'POST' })
    .then(j<{ job_id: string; video: VideoInfo; demo: boolean; original_filename: string; note: string }>),

  process: (id: string, settings?: Partial<Settings>) =>
    fetch(`${BASE}/process/${id}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings ?? {}),
    }).then(j<{ job_id: string; status: string }>),

  status: (id: string) => fetch(`${BASE}/status/${id}`).then(j<JobStatus>),

  actions: (id: string) => fetch(`${BASE}/actions/${id}`)
    .then(j<{ actions: ActionRow[]; visual_events: VisualEvent[]; unsupported: Unsupported[] }>),

  result: (id: string) => fetch(`${BASE}/result/${id}`).then(j<ResultPayload>),
  report: (id: string) => fetch(`${BASE}/report/${id}`).then(j<any>),

  previewUrl: (id: string) => `${BASE}/preview/${id}`,
  videoUrl: (id: string) => `${BASE}/video/${id}`,
  audioUrl: (id: string) => `${BASE}/audio/${id}`,
  downloadUrl: (id: string) => `${BASE}/download/${id}`,
}
