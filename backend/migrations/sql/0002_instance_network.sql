-- Instances can be attached to a subnet with an allocated address.
ALTER TABLE instances
    ADD COLUMN network_id uuid REFERENCES networks(id) ON DELETE RESTRICT,
    ADD COLUMN subnet_id uuid REFERENCES subnets(id) ON DELETE RESTRICT,
    ADD COLUMN ip inet,
    ADD CONSTRAINT instances_network_all_or_none CHECK ((network_id IS NULL) = (subnet_id IS NULL) AND (subnet_id IS NULL) = (ip IS NULL));
