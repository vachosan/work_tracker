from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage


class PrefixedMediaStorage(S3Boto3Storage):
    """Put media objects under AWS_MEDIA_PREFIX when configured."""

    def __init__(self, *args, **kwargs):
        prefix = getattr(settings, "AWS_MEDIA_PREFIX", "")
        if prefix:
            kwargs.setdefault("location", prefix.strip("/"))
        super().__init__(*args, **kwargs)
