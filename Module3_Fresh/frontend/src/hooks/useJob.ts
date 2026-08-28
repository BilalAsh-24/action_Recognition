import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { JobStatus, ResultPayload, ActionRow, VisualEvent, Unsupported } from '../types'

/** Polls real backend job state. Progress is never synthesised on the client. */
export function useJob(jobId: string | null) {
  const [status, setStatus] = useState<JobStatus | null>(null)
  const [result, setResult] = useState<ResultPayload | null>(null)
  const [actions, setActions] = useState<ActionRow[]>([])
  const [events, setEvents] = useState<VisualEvent[]>([])
  const [unsupported, setUnsupported] = useState<Unsupported[]>([])
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<number | null>(null)
  const seenTimeline = useRef(false)

  const stop = useCallback(() => {
    if (timer.current) { clearInterval(timer.current); timer.current = null }
  }, [])

  useEffect(() => {
    if (!jobId) return
    seenTimeline.current = false
    const tick = async () => {
      try {
        const s = await api.status(jobId)
        setStatus(s)
        // pull the timeline as soon as Module 2 finishes, so the user sees it
        // while Foley generation is still running
        if (!seenTimeline.current && s.stages?.timeline === 'done') {
          seenTimeline.current = true
          const a = await api.actions(jobId)
          setActions(a.actions); setEvents(a.visual_events); setUnsupported(a.unsupported)
        }
        if (s.status === 'completed') {
          stop()
          const [r, a] = await Promise.all([api.result(jobId), api.actions(jobId)])
          setResult(r); setActions(a.actions)
          setEvents(a.visual_events); setUnsupported(a.unsupported)
        } else if (s.status === 'failed') {
          stop(); setError(s.errors?.[0] ?? 'Processing failed.')
        }
      } catch (e) { stop(); setError((e as Error).message) }
    }
    tick()
    timer.current = window.setInterval(tick, 1500)
    return stop
  }, [jobId, stop])

  return { status, result, actions, events, unsupported, error }
}
