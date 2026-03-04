-- Migration: create zh title cache table used by /api/events/{id}/title-zh
CREATE TABLE IF NOT EXISTS event_title_i18n_cache (
  event_id bigint NOT NULL,
  lang text NOT NULL,
  source_title text NOT NULL,
  translated_title text,
  provider text,
  model text,
  status text NOT NULL DEFAULT 'PENDING',
  error text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (event_id, lang)
);

CREATE INDEX IF NOT EXISTS idx_event_title_i18n_cache_status
  ON event_title_i18n_cache (status, updated_at DESC);
