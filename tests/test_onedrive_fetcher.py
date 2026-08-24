import unittest
from unittest.mock import patch, MagicMock
from source_service.fetchers.onedrive_fetcher import OneDriveSource


class TestOneDriveSource(unittest.TestCase):
    def setUp(self):
        self.config = {
            'access_token': 'test_token',
            'client_id': 'test_client',
            'client_secret': 'test_secret',
            'refresh_token': 'test_refresh',
            'path': '/Documents',
        }
        self.source = OneDriveSource()

    @patch.object(OneDriveSource, '_get_drive_id')
    @patch.object(OneDriveSource, '_request')
    def test_list_documents_success(self, mock_request, mock_get_drive_id):
        mock_get_drive_id.return_value = 'drive123'

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "value": [
                {"id": "file1", "name": "doc1.pdf", "size": 1024,
                "lastModifiedDateTime": "2023-01-01T00:00:00Z", "file": {}},
                {"id": "file2", "name": "doc2.txt", "size": 2048,
                "lastModifiedDateTime": "2023-01-02T00:00:00Z", "file": {}},
            ],
            "@odata.nextLink": None
        }
        mock_request.return_value = mock_response

        docs = self.source.list_documents(self.config)
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].key, "file1")
        self.assertEqual(docs[0].metadata['name'], "doc1.pdf")
        self.assertEqual(docs[1].key, "file2")

    @patch.object(OneDriveSource, '_get_drive_id')
    @patch.object(OneDriveSource, '_request')
    def test_fetch_document_success(self, mock_request, mock_get_drive_id):
        """Descarga exitosa de un documento."""
        mock_get_drive_id.return_value = 'drive123'

        # Simular contenido y metadata (dos llamadas a _request)
        mock_content = MagicMock()
        mock_content.content = b"PDF content"

        mock_meta = MagicMock()
        mock_meta.json.return_value = {"name": "doc1.pdf", "size": 1024}

        # Primera llamada: contenido, segunda: metadata
        mock_request.side_effect = [mock_content, mock_meta]

        doc = self.source.fetch_document(self.config, "file1")
        self.assertEqual(doc.key, "file1")
        self.assertEqual(doc.content, b"PDF content")
        self.assertEqual(doc.metadata['name'], "doc1.pdf")
        self.assertEqual(doc.metadata['size'], 1024)

    @patch('source_service.fetchers.onedrive_fetcher.requests.post')
    @patch('source_service.fetchers.onedrive_fetcher.requests.request')
    @patch.object(OneDriveSource, '_get_drive_id')
    def test_token_refresh_on_401(self, mock_get_drive_id, mock_request, mock_post):
        """Verifica que se refresca el token ante un 401."""
        mock_get_drive_id.return_value = 'drive123'

        # Simular respuestas de requests.request:
        # 1. Primera llamada a /children -> 401
        mock_resp_401 = MagicMock()
        mock_resp_401.status_code = 401
        # 2. Segunda llamada a /children -> 200 (éxito después del refresh)
        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_resp_200.json.return_value = {"value": []}

        # Simular respuesta de requests.post para el refresh token
        mock_refresh_resp = MagicMock()
        mock_refresh_resp.status_code = 200
        mock_refresh_resp.json.return_value = {"access_token": "new_token"}

        mock_request.side_effect = [mock_resp_401, mock_resp_200]
        mock_post.return_value = mock_refresh_resp

        docs = self.source.list_documents(self.config)
        self.assertEqual(docs, [])

        # Verificar que se llamó a requests.post para refrescar
        mock_post.assert_called_once_with(
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": "test_refresh",
                "client_id": "test_client",
                "client_secret": "test_secret",
                "scope": "https://graph.microsoft.com/Files.ReadWrite offline_access",
            },
            timeout=30
        )
