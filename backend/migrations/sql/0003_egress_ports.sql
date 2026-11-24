-- Outbound policy per subnet (default: no egress) and an optional host port published on loopback per instance.
ALTER TABLE subnets ADD COLUMN egress boolean NOT NULL DEFAULT false;
ALTER TABLE instances
    ADD COLUMN published_port integer,
    ADD CONSTRAINT instances_published_port_range CHECK (published_port IS NULL OR (published_port BETWEEN 20000 AND 29999 AND subnet_id IS NOT NULL));
CREATE UNIQUE INDEX instances_published_port_uniq ON instances(published_port) WHERE published_port IS NOT NULL;
