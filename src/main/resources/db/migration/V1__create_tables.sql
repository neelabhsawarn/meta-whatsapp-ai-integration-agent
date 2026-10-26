CREATE TABLE outbound_messages (
  key_hash VARCHAR(64) PRIMARY KEY,
  payload_hash VARCHAR(64) NOT NULL,
  state VARCHAR(24) NOT NULL,
  provider_message_id VARCHAR(160),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE inbound_events (
  event_hash VARCHAR(64) PRIMARY KEY,
  kind VARCHAR(24) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE diagnostic_events (
  id BIGSERIAL PRIMARY KEY,
  category VARCHAR(40) NOT NULL,
  http_status INTEGER,
  context VARCHAR(80) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX diagnostic_events_recent_idx ON diagnostic_events (created_at DESC);
