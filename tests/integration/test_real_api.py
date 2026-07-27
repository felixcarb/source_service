from pathlib import Path
import os
import unittest
import json
import requests
from dotenv import load_dotenv
from source_service import SourceFactory

# Cargar variables de entorno
test_dir = Path(__file__).parent
env_path = test_dir / '.env.test'
load_dotenv(env_path)

REQUIRED_ENV = ['API_TEST_URL']
MISSING = [v for v in REQUIRED_ENV if not os.getenv(v)]


class TestAPIReal(unittest.TestCase):
    """Pruebas de integración con API real (Docker mock)."""

    @classmethod
    def setUpClass(cls):
        if MISSING:
            raise unittest.SkipTest(
                f"Faltan variables en .env.test: {', '.join(MISSING)}")

        cls.config = {
            'url': os.getenv('API_TEST_URL'),
            'headers': json.loads(os.getenv('API_TEST_HEADERS', '{}')),
        }
        cls.source = SourceFactory.get_source("api")

        # Verificar que la API está disponible
        try:
            response = requests.get(cls.config['url'], timeout=5)
            response.raise_for_status()
            cls._api_available = True
        except Exception:
            cls._api_available = False
            print("⚠️  API no disponible, los tests se saltarán")

    def test_list_documents(self):
        """Listar documentos desde la API."""
        if not self._api_available:
            self.skipTest("API no disponible")
        docs = self.source.list_documents(self.config)
        self.assertGreater(len(docs), 0, "Debería haber al menos un documento")
        print(f"📂 Documentos encontrados: {len(docs)}")
        for doc in docs[:3]:
            print(f"  - {doc.key}: {doc.metadata}")

    def test_fetch_document(self):
        """Descargar un documento desde la API."""
        if not self._api_available:
            self.skipTest("API no disponible")
        docs = self.source.list_documents(self.config)
        if docs:
            doc = self.source.fetch_document(self.config, docs[0].key)
            self.assertIsNotNone(doc.content)
            self.assertGreater(len(doc.content), 0)
            print(f"📄 Descargado: {doc.key} ({len(doc.content)} bytes)")
            print(f"    Metadata: {doc.metadata}")
        else:
            self.skipTest("No hay documentos para descargar")


if __name__ == '__main__':
    unittest.main()
