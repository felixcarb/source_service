import boto3
from botocore.exceptions import ClientError
import logging
import os
from typing import List, Dict, Any, Optional
from ..base import DocumentSource, Document
from ..exceptions import SourceConnectionError, DocumentNotFoundError, InvalidConfigurationError

logger = logging.getLogger(__name__)


class S3Source(DocumentSource):
    def _get_client(self, config: Dict[str, Any]):
        access_key = config.get('access_key_id') or config.get('access_key')
        secret_key = config.get(
            'secret_access_key') or config.get('secret_key')
        session_token = config.get('session_token')
        region = config.get('region', 'eu-west-2')
        endpoint_url = config.get('endpoint_url')

        if not endpoint_url:
            session = boto3.Session(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                aws_session_token=session_token,
                region_name=region
            )
            return session.client('s3')
        else:
            session = boto3.Session(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                aws_session_token=session_token,
                region_name=region
            )
            return session.client('s3', endpoint_url=endpoint_url)

    def list_documents(self, config: Dict[str, Any]) -> List[Document]:
        bucket = config.get('bucket_name') or config.get('bucket')
        prefix = config.get('prefix', '')
        if not bucket:
            raise InvalidConfigurationError("Missing 'bucket' in S3 config")

        s3 = self._get_client(config)
        try:
            paginator = s3.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

            documents = []
            page_count = 0
            for page in pages:
                page_count += 1
                contents = page.get('Contents', [])
                if contents:
                    for obj in contents:
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
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            print(f"[DEBUG S3] ERROR ClientError: {error_code} - {error_msg}")
            print(f"[DEBUG S3] Complete response: {e.response}")
            raise SourceConnectionError(f"S3 error: {e}")
        except Exception as e:
            print(f"[DEBUG S3] Unexpected ERROR: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise

    def fetch_document(self, config: Dict[str, Any], key: str) -> Document:
        bucket = config.get('bucket_name') or config.get('bucket')
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

    def move_object(self, config: Dict[str, Any], source_key: str, dest_bucket: str, dest_key: str) -> bool:
        """
        Mueve un objeto S3 de una ubicación a otra (mismo o diferente bucket)
        sin descargar el contenido. Retorna True si éxito, lanza excepción si falla.
        """
        source_bucket = config.get(
            'bucket_name') or config.get('bucket')
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
        bucket = config.get('bucket_name') or config.get('bucket')
        if not bucket:
            raise InvalidConfigurationError("Missing 'bucket' in S3 config")

        s3 = self._get_client(config)
        try:
            s3.delete_object(Bucket=bucket, Key=key)
            return True
        except ClientError as e:
            raise SourceConnectionError(f"S3 delete error: {e}")

    def delete_document(self, config: Dict[str, Any], key: str) -> bool:
        """Elimina un objeto de S3."""
        logger.debug(f"S3 delete: key={key}")
        try:
            self.delete_object(config, key)
            logger.debug(f"S3 delete successful: {key}")
            return True
        except Exception as e:
            logger.error(f"S3 delete error for {key}: {e}", exc_info=True)
            return False

    def move_document(self, config: Dict[str, Any], key: str, destination: str) -> bool:
        logger.debug(f"S3 move: key={key}, destination={destination}")
        bucket = config.get('bucket_name') or config.get('bucket')
        if not bucket:
            logger.error("Missing 'bucket' in S3 config")
            return False

        # Normalizar destino: eliminar barras iniciales y finales
        destination = destination.strip('/')

        # Si destination está vacío, usar solo el nombre del archivo (mover a la raíz)
        if not destination:
            dest_key = os.path.basename(key)
        else:
            filename = os.path.basename(key)
            dest_key = f"{destination}/{filename}"

        logger.debug(f"S3 move: resolved dest_key={dest_key}")

        s3 = self._get_client(config)
        try:
            copy_source = {'Bucket': bucket, 'Key': key}
            s3.copy_object(CopySource=copy_source, Bucket=bucket, Key=dest_key)
            s3.delete_object(Bucket=bucket, Key=key)
            logger.debug(f"S3 move successful: {key} -> {dest_key}")
            return True
        except Exception as e:
            logger.error(
                f"S3 move error for {key} to {dest_key}: {e}", exc_info=True)
            return False
