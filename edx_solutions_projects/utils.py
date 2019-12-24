import boto3

from django.conf import settings


S3_FILE_URL_TIMEOUT = 60 * 30  # 30 minutes


def make_temporary_s3_link(file_path):
    """
    pre-sign url so that it can be accessible for limited time period
    i,e: S3_FILE_URL_TIMEOUT publicly.
    """
    if settings.DEFAULT_FILE_STORAGE == 'storages.backends.s3boto.S3BotoStorage':
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )
        signed_url = s3_client.generate_presigned_url(
            ClientMethod='get_object',
            ExpiresIn=S3_FILE_URL_TIMEOUT,
            Params={
                'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                'Key': file_path
            }
        )
        return signed_url

    return None
