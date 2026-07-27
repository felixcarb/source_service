import boto3
from botocore.exceptions import ClientError
from typing import List, Dict, Any, Optional
from ..base import DocumentSource, Document
from ..exceptions import SourceConnectionError, DocumentNotFoundError, InvalidConfigurationError


class S3Source(DocumentSource):
    def _get_client(self, config: Dict[str, Any]):
        """Crea y devuelve un cliente S3 con endpoint personalizado si se proporciona."""
        session = boto3.Session(
            aws_access_key_id=config.get('access_key'),
            aws_secret_access_key=config.get('secret_key'),
            region_name=config.get('region', 'eu-west-2')
        )
        endpoint_url = config.get('endpoint_url')
        if endpoint_url:
            return session.client('s3', endpoint_url=endpoint_url)
        return session.client('s3')

    def list_documents(self, config: Dict[str, Any]) -> List[Document]:
        bucket = config.get('bucket')
        prefix = config.get('prefix', '')
        if not bucket:
            raise InvalidConfigurationError("Missing 'bucket' in S3 config")

        s3 = self._get_client(config)
        try:
            paginator = s3.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
            documents = []
            for page in pages:
                for obj in page.get('Contents', []):
                    documents.append(Document(
                        key=obj['Key'],
                        metadata={
                            'size': obj['Size'],
                            'last_modified': obj['LastModified'],
                            'etag': obj.get('ETag'),
                            'storage_class': obj.get('StorageClass'),
                        }
                    ))
            return documents
        except ClientError as e:
            raise SourceConnectionError(f"S3 error: {e}")

    def fetch_document(self, config: Dict[str, Any], key: str) -> Document:
        bucket = config.get('bucket')
        if not bucket:
            raise InvalidConfigurationError("Missing 'bucket' in S3 config")

        s3 = self._get_client(config)
        try:
            response = s3.get_object(Bucket=bucket, Key=key)
            content = response['Body'].read()
            return Document(
                key=key,
                metadata={
                    'size': response['ContentLength'],
                    'last_modified': response['LastModified'],
                    'etag': response.get('ETag'),
                    'content_type': response.get('ContentType'),
                },
                content=content
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise DocumentNotFoundError(
                    f"Key '{key}' not found in bucket '{bucket}'")
            raise SourceConnectionError(f"S3 error: {e}")

    def fetch_documents(self, config: Dict[str, Any], keys: Optional[List[str]] = None) -> List[Document]:
        if keys:
            return [self.fetch_document(config, key) for key in keys]
        docs = self.list_documents(config)
        return [self.fetch_document(config, doc.key) for doc in docs]

    # ─── Métodos adicionales para mover/eliminar en S3 ────────────────

    def move_object(self, config: Dict[str, Any], source_key: str, dest_bucket: str, dest_key: str) -> bool:
        """
        Mueve un objeto S3 de una ubicación a otra (mismo o diferente bucket)
        sin descargar el contenido. Retorna True si éxito, lanza excepción si falla.
        """
        source_bucket = config.get('bucket')
        if not source_bucket:
            raise InvalidConfigurationError(
                "Missing 'source bucket' in S3 config")

        s3 = self._get_client(config)
        try:
            # Copiar objeto al destino
            copy_source = {'Bucket': source_bucket, 'Key': source_key}
            s3.copy_object(
                CopySource=copy_source,
                Bucket=dest_bucket,
                Key=dest_key
            )
            # Eliminar el original
            s3.delete_object(Bucket=source_bucket, Key=source_key)
            return True
        except ClientError as e:
            # Si falla la copia o el borrado, lanzamos excepción para que el
            # original no se pierda si algo falla a medias.
            raise SourceConnectionError(f"S3 move error: {e}")

    def delete_object(self, config: Dict[str, Any], key: str) -> bool:
        """Elimina un objeto de S3. Retorna True si éxito, lanza excepción si falla."""
        bucket = config.get('bucket')
        if not bucket:
            raise InvalidConfigurationError("Missing 'bucket' in S3 config")

        s3 = self._get_client(config)
        try:
            s3.delete_object(Bucket=bucket, Key=key)
            return True
        except ClientError as e:
            raise SourceConnectionError(f"S3 delete error: {e}")
