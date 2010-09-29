from common.db import api

def make_fake_image():
    """Create a fake image record """
    image = api.image_create(
        None,
        dict(name="Test Image",
             state="available",
             public=True,
             image_type="tarball"))

    api.image_chunk_create(
        None, 
        dict(image_id=image.id,
             location="swift://myacct/mycontainer/obj.tar.gz.0",
             size=101))
    api.image_chunk_create(
        None, 
        dict(image_id=image.id,
             location="swift://myacct/mycontainer/obj.tar.gz.1",
             size=101))

    api.image_metadatum_create(
        None,
        dict(image_id=image.id,
             key_name="testkey",
             key_data="testvalue"))


if __name__ == "__main__":
    make_fake_image()
