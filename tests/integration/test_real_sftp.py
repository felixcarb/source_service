from pathlib import Path
import os
import unittest
import time
import paramiko
from io import BytesIO
from dotenv import load_dotenv
from source_service import SourceFactory

# Cargar variables de entorno
test_dir = Path(__file__).parent
env_path = test_dir / '.env.test'
load_dotenv(env_path)

# Verificar credenciales
REQUIRED_ENV = ['SFTP_TEST_HOST', 'SFTP_TEST_PORT',
                'SFTP_TEST_USERNAME', 'SFTP_TEST_PASSWORD']
MISSING = [v for v in REQUIRED_ENV if not os.getenv(v)]


class TestSFTPReal(unittest.TestCase):
    """Pruebas de integración con servidor SFTP real (Docker)."""

    @classmethod
    def setUpClass(cls):
        if MISSING:
            raise unittest.SkipTest(
                f"Faltan variables en .env.test: {', '.join(MISSING)}")

        cls.config = {
            'host': os.getenv('SFTP_TEST_HOST'),
            'port': int(os.getenv('SFTP_TEST_PORT', 22)),
            'username': os.getenv('SFTP_TEST_USERNAME'),
            'password': os.getenv('SFTP_TEST_PASSWORD'),
            'path': os.getenv('SFTP_TEST_PATH', '/data'),
            'timeout': 60,
        }
        cls.source = SourceFactory.get_source("sftp")

        # Conexión directa con paramiko para subir archivos
        cls.ssh = paramiko.SSHClient()
        cls.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        cls.ssh.connect(
            cls.config['host'],
            port=cls.config['port'],
            username=cls.config['username'],
            password=cls.config['password']
        )
        cls.sftp = cls.ssh.open_sftp()

        cls.test_filename = f"test_upload_{os.urandom(4).hex()}.txt"
        cls.test_content = b"Contenido de prueba para SFTP.\n" * 50

    @classmethod
    def tearDownClass(cls):
        """Limpiar: eliminar archivo de prueba y cerrar conexión."""
        try:
            cls.sftp.remove(f"{cls.config['path']}/{cls.test_filename}")
            print(f"🗑️  Eliminado archivo: {cls.test_filename}")
        except Exception:
            pass
        cls.sftp.close()
        cls.ssh.close()

    def setUp(self):
        """Subir el archivo de prueba una sola vez."""
        if not hasattr(self.__class__, '_file_uploaded'):
            try:
                remote_path = f"{self.config['path']}/{self.test_filename}"
                with BytesIO(self.test_content) as buffer:
                    self.sftp.putfo(buffer, remote_path)
                time.sleep(1)
                self.__class__._file_uploaded = True
                print(
                    f"✅ Archivo subido: {remote_path} ({len(self.test_content)} bytes)")
            except Exception as e:
                self.skipTest(f"No se pudo subir archivo de prueba: {e}")

    def test_list_documents_includes_uploaded_file(self):
        """Verificar que el archivo subido aparece en el listado."""
        docs = self.source.list_documents(self.config)
        found = any(doc.key.endswith(self.test_filename) for doc in docs)
        self.assertTrue(
            found, f"El archivo '{self.test_filename}' no se encontró.")
        print("✅ Archivo encontrado en el listado.")

    def test_fetch_document_uploaded_file(self):
        """Descargar el archivo subido y verificar su contenido."""
        docs = self.source.list_documents(self.config)
        target = next(
            (doc for doc in docs if doc.key.endswith(self.test_filename)), None)
        self.assertIsNotNone(
            target, f"Archivo '{self.test_filename}' no encontrado.")
        doc = self.source.fetch_document(self.config, target.key)
        self.assertEqual(doc.content, self.test_content,
                         "El contenido descargado no coincide.")
        print(
            f"📄 Descargado: {doc.key} ({len(doc.content)} bytes) - Contenido correcto.")


if __name__ == '__main__':
    unittest.main()
