--
-- This is necessary because SQLite does not support
-- RENAME INDEX or ALTER TABLE CHANGE COLUMN.
--
CREATE TEMPORARY TABLE image_properties_backup (
	id INTEGER NOT NULL,
	image_id INTEGER NOT NULL,
	key VARCHAR(255) NOT NULL,
	value TEXT,
	created_at DATETIME NOT NULL,
	updated_at DATETIME,
	deleted_at DATETIME,
	deleted BOOLEAN NOT NULL,
	PRIMARY KEY (id)
);

INSERT INTO image_properties_backup
SELECT id, image_id, name, value, created_at, updated_at, deleted_at, deleted
FROM image_properties;

DROP TABLE image_properties;

CREATE TABLE image_properties (
	id INTEGER NOT NULL,
	image_id INTEGER NOT NULL,
	key VARCHAR(255) NOT NULL,
	value TEXT,
	created_at DATETIME NOT NULL,
	updated_at DATETIME,
	deleted_at DATETIME,
	deleted BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	CHECK (deleted IN (0, 1)),
	UNIQUE (image_id, key),
	FOREIGN KEY(image_id) REFERENCES images (id)
);
CREATE INDEX ix_image_properties_key ON image_properties (key);

INSERT INTO image_properties (id, image_id, key, value, created_at, updated_at, deleted_at, deleted)
SELECT id, image_id, key, value, created_at, updated_at, deleted_at, deleted
FROM image_properties_backup;

DROP TABLE image_properties_backup;
