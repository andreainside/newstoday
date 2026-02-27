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

CREATE TABLE IF NOT EXISTS algorithm_eval_logs (
  id bigserial PRIMARY KEY,
  run_id text NOT NULL,
  eval_type text NOT NULL,
  algorithm_name text NOT NULL,
  algorithm_version text,
  baseline_name text,
  baseline_version text,
  sample_window_hours integer,
  sample_event_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  algo_topk jsonb,
  baseline_topk jsonb,
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  params jsonb NOT NULL DEFAULT '{}'::jsonb,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE VIEW vw_gap_hints_daily AS
SELECT
  date_trunc('day', created_at) AS day,
  COUNT(*) AS events_checked,
  SUM(CASE WHEN (metrics->>'gap_found')::boolean THEN 1 ELSE 0 END) AS events_with_gap,
  AVG((metrics->>'dominant_source_ratio')::double precision) AS avg_dominant_source_ratio,
  AVG((metrics->>'missing_type_count')::double precision) AS avg_missing_type_count
FROM algorithm_eval_logs
WHERE eval_type = 'gap_hints_daily'
GROUP BY 1
ORDER BY 1 DESC;

CREATE OR REPLACE VIEW vw_top_events_params_daily AS
SELECT
  date_trunc('day', created_at) AS day,
  MAX((params->>'window_hours')::integer) AS window_hours,
  MAX((params->>'tau_hours')::integer) AS tau_hours,
  MAX((params->'weights'->>'hot')::double precision) AS w_hot,
  MAX((params->'weights'->>'div')::double precision) AS w_div,
  MAX((params->'weights'->>'fresh')::double precision) AS w_fresh,
  COUNT(*) AS runs
FROM algorithm_eval_logs
WHERE eval_type = 'top_events_params'
GROUP BY 1
ORDER BY 1 DESC;
