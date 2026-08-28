export interface VideoInfo {
  path: string; duration_s: number; width: number; height: number;
  fps: string; frames: number; codec: string; has_audio: boolean; size_bytes: number;
}
export interface ActionRow {
  action: string; start: number; end: number; status: string; confidence: string;
}
export interface VisualEvent {
  action: string; kind: string; t_s: number; confidence: string; basis: string;
}
export interface FoleyMetrics {
  peak_dbfs: number; dynamic_range_db: number; effective_bits: number;
  harmonic_ratio: number; required_gain_db: number; spectral_flatness?: number;
  active_rms_dbfs?: number; sample_rate?: number; channels?: number; duration_s?: number
}
export interface CandidateAttempt {
  candidate: number; seed: number; ok: boolean; score: number
  cached: boolean; reason: string; metrics: FoleyMetrics
}
export interface GeneratedSound {
  key: string; label: string; cached: boolean
  validated?: boolean; quality?: FoleyMetrics
  candidates?: number; selected_seed?: number | null; selected_score?: number
  attempts?: CandidateAttempt[]
}
export interface Unsupported {
  action: string; start: number; end: number; reason: string
  detail?: string; status?: string; metrics?: FoleyMetrics
  candidates_tried?: number
}
export interface JobStatus {
  job_id: string; status: 'created'|'queued'|'running'|'completed'|'failed';
  progress: number; current_stage: string; stages: Record<string, string>;
  errors: string[]; warnings: string[]; counts: Record<string, number>;
  generated_audio: GeneratedSound[]; updated_at: string;
}
export interface ResultPayload {
  job_id: string; video_url: string; audio_url: string; download_url: string;
  counts: { actions_detected: number; sounds_generated: number;
            placements: number; unsupported_actions: number };
  sync: { worst_error_ms: number | null; note: string };
  mix: { peak_dbfs: number; rms_dbfs: number; crest_db: number;
         clipped_samples: number; duration_s: number; channels: number; subtype: string };
  render: Record<string, any>;
  actions: ActionRow[]; generated: GeneratedSound[]; unsupported: Unsupported[];
}
export interface Health {
  status: string; ffmpeg: boolean; action_recognition_env: boolean;
  sound_generation_env: boolean; moss_checkpoints: boolean; demo_available: boolean;
  stages: { key: string; label: string }[];
  defaults: Record<string, number | string>;
  limits: { max_upload_mb: number; max_video_seconds: number; allowed: string[] };
}
export interface Settings {
  seed: number; steps: number; cfg_scale: number;
  sigma_shift: number; duration: number; sample_rate: number; max_candidates: number;
}
