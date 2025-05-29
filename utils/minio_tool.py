from minio import Minio

from rzx_jms import settings


class MinioManager(object):
    def __init__(self):
        self.client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=False
        )

    def list_buckets(self):
        return self.client.list_buckets()

    def check_exists(self, bucket_name):
        return self.client.bucket_exists(bucket_name)

    def file_upload(
        self, bucket_name, object_name, file_path, content_type=None, metadata=None
    ):
        if not self.check_exists(bucket_name):
            raise
        return self.client.fput_object(
            bucket_name, object_name, file_path,
            content_type=content_type, metadata=metadata
        )

    def object_upload(
        self, bucket_name, object_name, data, file_size
    ):
        if not self.check_exists(bucket_name):
            raise
        return self.client.put_object(bucket_name, object_name, data, file_size)

    def file_download(self, object_name, bucket_name):
        if not self.check_exists(bucket_name):
            raise
        return self.client.get_object(bucket_name, object_name)

    def get_object(self, object_name, bucket_name):
        if not self.check_exists(bucket_name):
            raise
        return self.client.stat_object(bucket_name, object_name)


minio_manager = MinioManager()


if __name__ == "__main__":
    print(minio_manager.list_buckets())
