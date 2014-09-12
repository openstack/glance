CREATE TEMPORARY TABLE image_members_backup (
    id INTEGER NOT NULL,
    image_id VARCHAR(36) NOT NULL,
    member VARCHAR(255) NOT NULL,
    can_share BOOLEAN NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME,
    deleted_at DATETIME,
    deleted BOOLEAN NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (image_id, member),
    CHECK (can_share IN (0, 1)),
    CHECK (deleted IN (0, 1)),
    FOREIGN KEY(image_id) REFERENCES images (id)
);

INSERT INTO image_members_backup
SELECT id, image_id, member, can_share, created_at, updated_at, deleted_at, deleted
FROM image_members;

DROP TABLE image_members;

CREATE TABLE image_members (
    id INTEGER NOT NULL,
    image_id VARCHAR(36) NOT NULL,
    member VARCHAR(255) NOT NULL,
    can_share BOOLEAN NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME,
    deleted_at DATETIME,
    deleted BOOLEAN NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (image_id, member),
    CHECK (can_share IN (0, 1)),
    CHECK (deleted IN (0, 1)),
    FOREIGN KEY(image_id) REFERENCES images (id)
);

INSERT INTO image_members
SELECT id, image_id, member, can_share, created_at, updated_at, deleted_at,     deleted
FROM image_members_backup;

DROP TABLE image_members_backup;
