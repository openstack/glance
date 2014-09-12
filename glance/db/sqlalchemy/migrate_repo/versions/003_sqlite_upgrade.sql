-- Move type column from base images table
-- to be records in image_properties table
CREATE TEMPORARY TABLE tmp_type_records (id INTEGER NOT NULL, type VARCHAR(30) NOT NULL);
INSERT INTO tmp_type_records
SELECT id, type
FROM images
WHERE type IS NOT NULL;

REPLACE INTO image_properties
(image_id, key, value, created_at, deleted)
SELECT id, 'type', type, date('now'), 0
FROM tmp_type_records;

DROP TABLE tmp_type_records;

-- Make changes to the base images table
CREATE TEMPORARY TABLE images_backup (
	id INTEGER NOT NULL,
	name VARCHAR(255),
	size INTEGER,
	status VARCHAR(30) NOT NULL,
	is_public BOOLEAN NOT NULL,
	location TEXT,
	created_at DATETIME NOT NULL,
	updated_at DATETIME,
	deleted_at DATETIME,
	deleted BOOLEAN NOT NULL,
	PRIMARY KEY (id)
);

INSERT INTO images_backup
SELECT id, name, size, status, is_public, location, created_at, updated_at, deleted_at, deleted
FROM images;

DROP TABLE images;

CREATE TABLE images (
	id INTEGER NOT NULL,
	name VARCHAR(255),
	size INTEGER,
	status VARCHAR(30) NOT NULL,
	is_public BOOLEAN NOT NULL,
	location TEXT,
	created_at DATETIME NOT NULL,
	updated_at DATETIME,
	deleted_at DATETIME,
	deleted BOOLEAN NOT NULL,
	disk_format VARCHAR(20),
	container_format VARCHAR(20),
	PRIMARY KEY (id),
	CHECK (is_public IN (0, 1)),
	CHECK (deleted IN (0, 1))
);
CREATE INDEX ix_images_deleted ON images (deleted);
CREATE INDEX ix_images_is_public ON images (is_public);

INSERT INTO images (id, name, size, status, is_public, location, created_at, updated_at, deleted_at, deleted)
SELECT id, name, size, status, is_public, location, created_at, updated_at, deleted_at, deleted
FROM images_backup;

DROP TABLE images_backup;
