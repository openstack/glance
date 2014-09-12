--
-- This file is necessary because MySQL does not support
-- renaming indexes.
--
DROP INDEX ix_image_properties_image_id_name ON image_properties;

-- Rename the `key` column to `name`
ALTER TABLE image_properties
CHANGE COLUMN name `key` VARCHAR(255) NOT NULL;

CREATE UNIQUE INDEX ix_image_properties_image_id_key ON image_properties (image_id, `key`);
