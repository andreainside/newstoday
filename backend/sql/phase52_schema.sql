ALTER TABLE events
ADD COLUMN IF NOT EXISTS signature_v0 jsonb;

CREATE TABLE IF NOT EXISTS event_merge_suggestions (
  id bigserial PRIMARY KEY,
  event_id_a bigint NOT NULL,
  event_id_b bigint NOT NULL,
  judge_version text NOT NULL,
  decision text NOT NULL,
  decision_path text NOT NULL,
  score double precision NOT NULL,
  evidence_tokens jsonb NOT NULL DEFAULT '[]'::jsonb,
  top_overlap_weight double precision,
  df_min_overlap integer,
  raw jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(event_id_a, event_id_b, judge_version)
);

CREATE TABLE IF NOT EXISTS event_merge_judgements_cache (
  id bigserial PRIMARY KEY,
  event_id_a bigint NOT NULL,
  event_id_b bigint NOT NULL,
  judge_version text NOT NULL,
  llm_json jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(event_id_a, event_id_b, judge_version)
);

CREATE TABLE IF NOT EXISTS event_ai_cache (
  id bigserial PRIMARY KEY,
  event_id bigint NOT NULL,
  provider text NOT NULL,
  model text NOT NULL,
  status text NOT NULL DEFAULT 'PENDING',
  output_json jsonb,
  error text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(event_id, provider, model)
);
