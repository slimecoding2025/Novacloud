-- Optional destination allow-list for subnets with egress (empty = unrestricted outbound).
ALTER TABLE subnets
    ADD COLUMN egress_allow text[] NOT NULL DEFAULT '{}',
    ADD CONSTRAINT subnets_allow_needs_egress CHECK (egress_allow = '{}' OR egress);
