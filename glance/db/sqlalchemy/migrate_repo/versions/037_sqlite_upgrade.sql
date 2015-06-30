UPDATE images SET protected = 0 WHERE protected is NULL;
UPDATE image_members SET status = 'pending' WHERE status is NULL;

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
  min_disk INTEGER,
  min_ram INTEGER,
  protected BOOLEAN NOT NULL DEFAULT 0,
  virtual_size INTEGER,
  PRIMARY KEY (id),
  CHECK (is_public IN (0, 1)),
  CHECK (deleted IN (0, 1))
);

INSERT INTO images_backup
  SELECT id, name, size, status, is_public, created_at, updated_at, deleted_at, deleted, disk_format, container_format, checksum, owner, min_disk, min_ram, protected, virtual_size
  FROM images;

DROP TABLE images;

CREATE TABLE images (
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
  protected BOOLEAN NOT NULL DEFAULT 0,
  virtual_size INTEGER,
  PRIMARY KEY (id),
  CHECK (is_public IN (0, 1)),
  CHECK (deleted IN (0, 1))
);

CREATE INDEX ix_images_deleted ON images (deleted);
CREATE INDEX ix_images_is_public ON images (is_public);
CREATE INDEX owner_image_idx ON images (owner);
CREATE INDEX checksum_image_idx ON images (checksum);


INSERT INTO images
  SELECT id, name, size, status, is_public, created_at, updated_at, deleted_at, deleted, disk_format, container_format, checksum, owner, min_disk,  min_ram, protected, virtual_size
  FROM images_backup;

DROP TABLE images_backup;

CREATE TEMPORARY TABLE image_members_backup (
  id INTEGER NOT NULL,
  image_id VARCHAR(36) NOT NULL,
  member VARCHAR(255) NOT NULL,
  can_share BOOLEAN NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME,
  deleted_at DATETIME,
  deleted BOOLEAN NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  PRIMARY KEY (id),
  UNIQUE (image_id, member),
  CHECK (can_share IN (0, 1)),
  CHECK (deleted IN (0, 1)),
  FOREIGN KEY(image_id) REFERENCES images (id)
);

INSERT INTO image_members_backup
  SELECT id, image_id, member, can_share, created_at, updated_at, deleted_at, deleted, status
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
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  PRIMARY KEY (id),
  UNIQUE (image_id, member),
  CHECK (can_share IN (0, 1)),
  CHECK (deleted IN (0, 1)),
  FOREIGN KEY(image_id) REFERENCES images (id),
  CONSTRAINT image_members_image_id_member_deleted_at_key UNIQUE (image_id, member, deleted_at)
);

CREATE INDEX ix_image_members_deleted ON image_members (deleted);
CREATE INDEX ix_image_members_image_id ON image_members (image_id);
CREATE INDEX ix_image_members_image_id_member ON image_members (image_id, member);

INSERT INTO image_members
  SELECT id, image_id, member, can_share, created_at, updated_at, deleted_at, deleted, status
  FROM image_members_backup;

DROP TABLE image_members_backup;

CREATE TEMPORARY TABLE image_properties_backup (
  id INTEGER NOT NULL,
  image_id VARCHAR(36) NOT NULL,
  name VARCHAR(255) NOT NULL,
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
  image_id VARCHAR(36) NOT NULL,
  name VARCHAR(255) NOT NULL,
  value TEXT,
  created_at DATETIME NOT NULL,
  updated_at DATETIME,
  deleted_at DATETIME,
  deleted BOOLEAN NOT NULL,
  PRIMARY KEY (id),
  CHECK (deleted IN (0, 1)),
  FOREIGN KEY(image_id) REFERENCES images (id),
  CONSTRAINT ix_image_properties_image_id_name UNIQUE (image_id, name)
);

CREATE INDEX ix_image_properties_deleted ON image_properties (deleted);
CREATE INDEX ix_image_properties_image_id ON image_properties (image_id);

INSERT INTO image_properties (id, image_id, name, value, created_at, updated_at, deleted_at, deleted)
  SELECT id, image_id, name, value, created_at, updated_at, deleted_at, deleted
  FROM image_properties_backup;

DROP TABLE image_properties_backup;
