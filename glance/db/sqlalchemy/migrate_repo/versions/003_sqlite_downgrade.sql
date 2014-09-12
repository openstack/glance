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
	type VARCHAR(30),
	status VARCHAR(30) NOT NULL,
	is_public BOOLEAN NOT NULL,
	location TEXT,
	created_at DATETIME NOT NULL,
	updated_at DATETIME,
	deleted_at DATETIME,
	deleted BOOLEAN NOT NULL,
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

-- Re-insert the type values from the temp table
UPDATE images
SET type = (SELECT value FROM image_properties WHERE image_id = images.id AND key = 'type')
WHERE EXISTS (SELECT * FROM image_properties WHERE image_id = images.id AND key = 'type');

-- Remove the type properties from the image_properties table
DELETE FROM image_properties
WHERE key = 'type';
