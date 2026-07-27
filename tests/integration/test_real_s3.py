from pathlib import Path
import os
import unittest
import time
import boto3
from botocore.exceptions import ClientError
from io import BytesIO
from dotenv import load_dotenv
from source_service import SourceFactory

# Cargar variables de entorno
test_dir = Path(__file__).parent
env_path = test_dir / '.env.test'
load_dotenv(env_path)

# Verificar credenciales
REQUIRED_ENV = [
    'S3_TEST_BUCKET',
    'S3_TEST_ACCESS_KEY',
    'S3_TEST_SECRET_KEY',
    'S3_TEST_REGION',
]
MISSING = [v for v in REQUIRED_ENV if not os.getenv(v)]


class TestS3Real(unittest.TestCase):
    """Pruebas de integración con AWS S3 real (o LocalStack)."""

    @classmethod
    def setUpClass(cls):
        if MISSING:
            raise unittest.SkipTest(
                f"Faltan variables en .env.test: {', '.join(MISSING)}"
            )

        # Configuración del fetcher
        cls.config = {
            'bucket': os.getenv('S3_TEST_BUCKET'),
            'access_key': os.getenv('S3_TEST_ACCESS_KEY'),
            'secret_key': os.getenv('S3_TEST_SECRET_KEY'),
            'region': os.getenv('S3_TEST_REGION', 'us-east-1'),
            'prefix': os.getenv('S3_TEST_PREFIX', ''),
            'endpoint_url': os.getenv('S3_TEST_ENDPOINT_URL'),  # ← Añadir esto
        }
        cls.source = SourceFactory.get_source("s3")

        # Cliente boto3 para subir/eliminar archivos
        endpoint_url = os.getenv('S3_TEST_ENDPOINT_URL')
        cls.s3_client = boto3.client(
            's3',
            aws_access_key_id=cls.config['access_key'],
            aws_secret_access_key=cls.config['secret_key'],
            region_name=cls.config['region'],
            endpoint_url=endpoint_url if endpoint_url else None,
        )

        # Nombre y contenido del archivo de prueba (con prefijo para evitar colisiones)
        prefix = cls.config['prefix']
        if prefix and not prefix.endswith('/'):
            prefix += '/'
        cls.test_key = f"{prefix}test_upload_{os.urandom(4).hex()}.txt"
        cls.test_content = b"Contenido de prueba para S3.\n" * 50

    @classmethod
    def tearDownClass(cls):
        """Eliminar el archivo de prueba y limpiar."""
        try:
            cls.s3_client.delete_object(
                Bucket=cls.config['bucket'],
                Key=cls.test_key
            )
            print(f"🗑️  Eliminado objeto: {cls.test_key}")
        except Exception as e:
            print(f"⚠️  No se pudo eliminar {cls.test_key}: {e}")

    def setUp(self):
        """Subir el archivo de prueba una sola vez."""
        if not hasattr(self.__class__, '_file_uploaded'):
            try:
                buffer = BytesIO(self.test_content)
                self.s3_client.upload_fileobj(
                    buffer,
                    self.config['bucket'],
                    self.test_key,
                    ExtraArgs={'ContentType': 'text/plain'}
                )
                time.sleep(1)  # Pequeña pausa para eventual consistencia
                self.__class__._file_uploaded = True
                print(f"✅ Archivo subido: s3://{self.config['bucket']}/{self.test_key} "
                      f"({len(self.test_content)} bytes)")
            except ClientError as e:
                self.skipTest(f"No se pudo subir archivo de prueba: {e}")

    def test_list_documents_includes_uploaded_file(self):
        """Verificar que el archivo subido aparece en el listado."""
        docs = self.source.list_documents(self.config)
        found = any(doc.key == self.test_key for doc in docs)
        self.assertTrue(found, f"El objeto '{self.test_key}' no se encontró.")
        print("✅ Objeto encontrado en el listado.")

    def test_fetch_document_uploaded_file(self):
        """Descargar el archivo subido y verificar su contenido."""
        docs = self.source.list_documents(self.config)
        target = next((doc for doc in docs if doc.key == self.test_key), None)
        self.assertIsNotNone(
            target, f"Objeto '{self.test_key}' no encontrado.")
        doc = self.source.fetch_document(self.config, target.key)
        self.assertEqual(doc.content, self.test_content,
                         "El contenido descargado no coincide.")
        print(
            f"📄 Descargado: {doc.key} ({len(doc.content)} bytes) - Contenido correcto.")


if __name__ == '__main__':
    unittest.main()
