-- NOVACLOUD initial schema. Every tenant-owned table carries organization_id.
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE TABLE organizations (
    id uuid PRIMARY KEY,
    name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 80),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id uuid PRIMARY KEY,
    email text NOT NULL UNIQUE CHECK (email = lower(email)),
    password_hash text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE memberships (
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('owner','admin','member','viewer')),
    PRIMARY KEY (user_id, organization_id)
);

CREATE TABLE sessions (
    id uuid PRIMARY KEY,
    token_hash text NOT NULL UNIQUE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);

CREATE TABLE audit_log (
    id bigserial PRIMARY KEY,
    actor_id text NOT NULL,
    organization_id uuid,
    action text NOT NULL,
    resource_type text NOT NULL,
    resource_id text NOT NULL,
    result text NOT NULL CHECK (result IN ('success','denied','failure')),
    correlation_id text NOT NULL DEFAULT '',
    ts text NOT NULL,              -- ISO-8601 string, kept verbatim so the hash can be recomputed
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    prev_hash text NOT NULL UNIQUE, -- uniqueness forbids forks of the chain
    hash text NOT NULL UNIQUE
);
CREATE INDEX audit_log_org_idx ON audit_log (organization_id, id DESC);

CREATE FUNCTION audit_log_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END $$;
CREATE TRIGGER audit_log_no_update BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();
CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION audit_log_immutable();

CREATE TABLE instances (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name text NOT NULL,
    template text NOT NULL,
    state text NOT NULL CHECK (state IN ('planned','provisioning','running','stopping','stopped','failed','deleting','deleted')),
    provider_ref text,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX instances_org_name_active ON instances (organization_id, name) WHERE state <> 'deleted';

CREATE TABLE jobs (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    kind text NOT NULL,
    payload jsonb NOT NULL,
    idempotency_key text NOT NULL,
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed')),
    attempts int NOT NULL DEFAULT 0,
    max_attempts int NOT NULL DEFAULT 3,
    error text,
    result jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, idempotency_key)
);
CREATE INDEX jobs_queue_idx ON jobs (created_at) WHERE status = 'queued';

CREATE TABLE storage_objects (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name text NOT NULL,
    size bigint NOT NULL CHECK (size >= 0),
    sha256 text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE networks (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name text NOT NULL,
    cidr cidr NOT NULL,
    UNIQUE (organization_id, name)
);
-- Networks of one organization may not overlap.
ALTER TABLE networks ADD CONSTRAINT networks_no_overlap EXCLUDE USING gist (organization_id WITH =, cidr inet_ops WITH &&)
    DEFERRABLE INITIALLY IMMEDIATE;

CREATE TABLE subnets (
    id uuid PRIMARY KEY,
    network_id uuid NOT NULL REFERENCES networks(id) ON DELETE RESTRICT,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name text NOT NULL,
    cidr cidr NOT NULL,
    gateway inet NOT NULL,
    UNIQUE (network_id, name)
);

CREATE TABLE ip_allocations (
    subnet_id uuid NOT NULL REFERENCES subnets(id) ON DELETE RESTRICT,
    ip inet NOT NULL,
    resource_id text NOT NULL,
    PRIMARY KEY (subnet_id, ip),
    UNIQUE (subnet_id, resource_id)
);
