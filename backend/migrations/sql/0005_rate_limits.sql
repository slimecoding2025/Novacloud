-- Shared fixed-window rate limiter state (all API replicas count into the same rows). Keys are SHA-256 hashes.
CREATE TABLE rate_limits (
    key          text    NOT NULL,
    window_start bigint  NOT NULL,
    hits         integer NOT NULL DEFAULT 0,
    PRIMARY KEY (key, window_start)
);
CREATE INDEX rate_limits_window_idx ON rate_limits(window_start);
