CREATE TEMPORARY TABLE images_backup (
    id VARCHAR(36) NOT NULL,
    name VARCHAR(255),
    size INTEGER,
    status VARCHAR(30) NOT NULL,
    is_public BOOLEAN NOT NULL,
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
    protected BOOLEAN DEFAULT 0 NOT NULL,
    virtual_size INTEGER,
    PRIMARY KEY (id),
    CHECK (is_public IN (0, 1)),
    CHECK (deleted IN (0, 1)),
    CHECK (protected IN (0, 1))
);

INSERT INTO images_backup
    SELECT id,
        name,
        size,
        status,
        is_public,
        created_at,
        updated_at,
        deleted_at,
        deleted,
        disk_format,
        container_format,
        checksum,
        owner,
        min_disk,
        min_ram,
        protected,
        virtual_size
    FROM images;

DROP TABLE images;

CREATE TABLE images (
    id VARCHAR(36) NOT NULL,
    name VARCHAR(255),
    size INTEGER,
    status VARCHAR(30) NOT NULL,
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
    protected BOOLEAN DEFAULT 0 NOT NULL,
    virtual_size INTEGER,
    visibility VARCHAR(9) DEFAULT 'shared' NOT NULL,
    PRIMARY KEY (id),
    CHECK (deleted IN (0, 1)),
    CHECK (protected IN (0, 1)),
    CONSTRAINT image_visibility CHECK (visibility IN ('private', 'public', 'shared', 'community'))
);

CREATE INDEX checksum_image_idx ON images (checksum);
CREATE INDEX visibility_image_idx ON images (visibility);
CREATE INDEX ix_images_deleted ON images (deleted);
CREATE INDEX owner_image_idx ON images (owner);
CREATE INDEX created_at_image_idx ON images (created_at);
CREATE INDEX updated_at_image_idx ON images (updated_at);

-- Copy over all the 'public' rows

INSERT INTO images (
    id,
    name,
    size,
    status,
    created_at,
    updated_at,
    deleted_at,
    deleted,
    disk_format,
    container_format,
    checksum,
    owner,
    min_disk,
    min_ram,
    protected,
    virtual_size
    )
    SELECT id,
        name,
        size,
        status,
        created_at,
        updated_at,
        deleted_at,
        deleted,
        disk_format,
        container_format,
        checksum,
        owner,
        min_disk,
        min_ram,
        protected,
        virtual_size
    FROM images_backup
    WHERE is_public=1;


UPDATE images SET visibility='public';

-- Now copy over the 'private' rows

INSERT INTO images (
    id,
    name,
    size,
    status,
    created_at,
    updated_at,
    deleted_at,
    deleted,
    disk_format,
    container_format,
    checksum,
    owner,
    min_disk,
    min_ram,
    protected,
    virtual_size
    )
    SELECT id,
        name,
        size,
        status,
        created_at,
        updated_at,
        deleted_at,
        deleted,
        disk_format,
        container_format,
        checksum,
        owner,
        min_disk,
        min_ram,
        protected,
        virtual_size
    FROM images_backup
    WHERE is_public=0;

UPDATE images SET visibility='private' WHERE visibility='shared';
UPDATE images SET visibility='shared' WHERE visibility='private' AND id IN (SELECT DISTINCT image_id FROM image_members WHERE deleted != 1);

DROP TABLE images_backup;
