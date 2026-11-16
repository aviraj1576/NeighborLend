-- NeighborLend trust score breakdown, all values on a 0–5 scale.
-- Apply only after review/authorization for the target shared database.
CREATE TABLE IF NOT EXISTS trust_score_snapshots (
    user_id VARCHAR PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    rating_component DOUBLE PRECISION NOT NULL DEFAULT 3.12,
    reliability_component DOUBLE PRECISION NOT NULL DEFAULT 5.0,
    experience_component DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    verification_component DOUBLE PRECISION NOT NULL DEFAULT 5.0,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
