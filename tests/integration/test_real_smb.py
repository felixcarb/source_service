import smbclient
from pathlib import Path
import os
import unittest
import time
from dotenv import load_dotenv
from source_service import SourceFactory

test_dir = Path(__file__).parent
env_path = test_dir / '.env.test'
load_dotenv(env_path)

REQUIRED_ENV = ['SMB_TEST_HOST', 'SMB_TEST_USERNAME',
                'SMB_TEST_PASSWORD', 'SMB_TEST_SHARE']
MISSING = [v for v in REQUIRED_ENV if not os.getenv(v)]


class TestSMBReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if MISSING:
            raise unittest.SkipTest(f"Faltan variables: {', '.join(MISSING)}")

        cls.config = {
            'host': os.getenv('SMB_TEST_HOST'),
            'port': int(os.getenv('SMB_TEST_PORT', 445)),
            'username': os.getenv('SMB_TEST_USERNAME'),
            'password': os.getenv('SMB_TEST_PASSWORD'),
            'domain': os.getenv('SMB_TEST_DOMAIN'),
            'share': os.getenv('SMB_TEST_SHARE'),
            'path': '',  # Usar raíz del share
        }
        cls.source = SourceFactory.get_source("smb")

        # Registrar sesión para operaciones directas
        try:
            smbclient.register_session(
                cls.config['host'], username=cls.config['username'], password=cls.config['password'])
            cls.unc_base = f"\\\\{cls.config['host']}\\{cls.config['share']}"
        except Exception as e:
            raise unittest.SkipTest(
                f"No se pudo conectar al servidor SMB: {e}")

        cls.test_filename = f"test_upload_{os.urandom(4).hex()}.txt"
        cls.test_content = b"Contenido de prueba para SMB.\n" * 50

    @classmethod
    def tearDownClass(cls):
        try:
            smbclient.remove(f"{cls.unc_base}/{cls.test_filename}")
            print(f"🗑️  Eliminado archivo: {cls.test_filename}")
        except Exception:
            pass
        print("🔌 Conexión SMB cerrada.")

    def setUp(self):
        if not hasattr(self.__class__, '_file_uploaded'):
            try:
                with smbclient.open_file(f"{self.unc_base}/{self.test_filename}", mode='wb') as fd:
                    fd.write(self.test_content)
                time.sleep(1)
                self.__class__._file_uploaded = True
                print(
                    f"✅ Archivo subido: {self.test_filename} ({len(self.test_content)} bytes)")
            except Exception as e:
                self.skipTest(f"No se pudo subir archivo: {e}")

    def test_list_documents_includes_uploaded_file(self):
        docs = self.source.list_documents(self.config)
        found = any(doc.key == self.test_filename for doc in docs)
        self.assertTrue(
            found, f"Archivo '{self.test_filename}' no encontrado.")
        print("✅ Archivo encontrado en el listado.")

    def test_fetch_document_uploaded_file(self):
        docs = self.source.list_documents(self.config)
        target = next((doc for doc in docs if doc.key ==
                      self.test_filename), None)
        self.assertIsNotNone(
            target, f"Archivo '{self.test_filename}' no encontrado.")
        doc = self.source.fetch_document(self.config, target.key)
        self.assertEqual(doc.content, self.test_content,
                         "Contenido descargado no coincide.")
        print(
            f"📄 Descargado: {doc.key} ({len(doc.content)} bytes) - Contenido correcto.")


if __name__ == '__main__':
    unittest.main()
