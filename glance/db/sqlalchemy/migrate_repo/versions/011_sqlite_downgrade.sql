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
    disk_format VARCHAR(20),
    container_format VARCHAR(20),
    checksum VARCHAR(32),
    owner VARCHAR(255),
    min_disk INTEGER NOT NULL,
    min_ram INTEGER NOT NULL,
    PRIMARY KEY (id),
    CHECK (is_public IN (0, 1)),
    CHECK (deleted IN (0, 1))
);

INSERT INTO images_backup
SELECT id, name, size, status, is_public, location, created_at, updated_at,     deleted_at, deleted, disk_format, container_format, checksum, owner, min_disk,  min_ram
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
    checksum VARCHAR(32),
    owner VARCHAR(255),
    min_disk INTEGER,
    min_ram INTEGER,
    PRIMARY KEY (id),
    CHECK (is_public IN (0, 1)),
    CHECK (deleted IN (0, 1))
);

CREATE INDEX ix_images_deleted ON images (deleted);
CREATE INDEX ix_images_is_public ON images (is_public);

INSERT INTO images
SELECT id, name, size, status, is_public, location, created_at, updated_at,     deleted_at, deleted, disk_format, container_format, checksum, owner, min_disk,  min_ram
FROM images_backup;

DROP TABLE images_backup;
