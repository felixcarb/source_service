from pathlib import Path
import os
import unittest
import time
from io import BytesIO
from ftplib import FTP
from dotenv import load_dotenv
from source_service import SourceFactory

# Cargar variables de entorno
test_dir = Path(__file__).parent
env_path = test_dir / '.env.test'
load_dotenv(env_path)

print("FTP_HOST:", os.getenv('FTP_TEST_HOST'))
print("SFTP_HOST:", os.getenv('SFTP_TEST_HOST'))


class TestFTPReal(unittest.TestCase):
    """Pruebas de integración con servidor FTP real."""

    @classmethod
    def setUpClass(cls):
        cls.config = {
            'host': os.getenv('FTP_TEST_HOST'),
            'port': int(os.getenv('FTP_TEST_PORT', 21)),
            'username': os.getenv('FTP_TEST_USERNAME'),
            'password': os.getenv('FTP_TEST_PASSWORD'),
            'timeout': 120,
            'passive': True,
        }
        cls.source = SourceFactory.get_source("ftp")

        # Conexión directa para subir/eliminar archivos
        cls.ftp = FTP()
        try:
            cls.ftp.connect(cls.config['host'],
                            cls.config['port'], timeout=120)
            cls.ftp.login(cls.config['username'], cls.config['password'])
            cls.ftp.set_pasv(True)
        except Exception as e:
            raise unittest.SkipTest(f"No se pudo conectar al FTP: {e}")

        # Nombre y contenido del archivo de prueba
        cls.test_filename = f"test_upload_{os.urandom(4).hex()}.txt"
        cls.test_content = b"Contenido de prueba generado en memoria.\n" * 100

    @classmethod
    def tearDownClass(cls):
        """Limpiar: eliminar archivo de prueba y cerrar conexión."""
        try:
            cls.ftp.delete(cls.test_filename)
            print(f"🗑️  Eliminado archivo de prueba: {cls.test_filename}")
        except Exception:
            pass
        try:
            cls.ftp.quit()
        except Exception:
            cls.ftp.close()

    def setUp(self):
        """Subir el archivo de prueba una sola vez."""
        if not hasattr(self.__class__, '_file_uploaded'):
            try:
                self.ftp.set_pasv(True)  # Asegurar modo pasivo
                buffer = BytesIO(self.test_content)
                self.ftp.storbinary(f'STOR {self.test_filename}', buffer)
                time.sleep(1)  # Pequeña pausa para que el servidor procese
                self.__class__._file_uploaded = True
                print(
                    f"✅ Archivo subido: {self.test_filename} ({len(self.test_content)} bytes)")
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
