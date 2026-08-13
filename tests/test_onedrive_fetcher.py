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

    @patch('source_service.fetchers.onedrive_fetcher.requests.request')
    def test_list_documents_success(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "value": [
                {"id": "file1", "name": "doc1.pdf", "size": 1024,
                    "lastModifiedDateTime": "2023-01-01T00:00:00Z", "file": {}},
                {"id": "file2", "name": "doc2.txt", "size": 2048,
                    "lastModifiedDateTime": "2023-01-02T00:00:00Z", "file": {}},
            ],
            "@odata.nextLink": None
        }
        mock_request.return_value = mock_resp

        # Mock the drive ID request
        mock_drive_resp = MagicMock()
        mock_drive_resp.status_code = 200
        mock_drive_resp.json.return_value = {"id": "drive123"}
        # First call is drive, second is list
        mock_request.side_effect = [mock_drive_resp, mock_resp]

        docs = self.source.list_documents(self.config)
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].key, "file1")
        self.assertEqual(docs[0].metadata['name'], "doc1.pdf")
        self.assertEqual(docs[1].key, "file2")

    @patch('source_service.fetchers.onedrive_fetcher.requests.request')
    def test_fetch_document_success(self, mock_request):
        mock_content_resp = MagicMock()
        mock_content_resp.status_code = 200
        mock_content_resp.content = b"PDF content"
        mock_meta_resp = MagicMock()
        mock_meta_resp.status_code = 200
        mock_meta_resp.json.return_value = {"name": "doc1.pdf", "size": 1024}
        mock_request.side_effect = [mock_content_resp, mock_meta_resp]

        doc = self.source.fetch_document(self.config, "file1")
        self.assertEqual(doc.key, "file1")
        self.assertEqual(doc.content, b"PDF content")
        self.assertEqual(doc.metadata['name'], "doc1.pdf")
        self.assertEqual(doc.metadata['size'], 1024)

    @patch('source_service.fetchers.onedrive_fetcher.requests.request')
    def test_token_refresh_on_401(self, mock_request):
        # Mock responses for:
        # 1. Get drive ID (success)
        # 2. List documents (401)
        # 3. List documents after refresh (success)
        mock_drive_resp = MagicMock()
        mock_drive_resp.status_code = 200
        mock_drive_resp.json.return_value = {"id": "drive123"}

        mock_resp_401 = MagicMock()
        mock_resp_401.status_code = 401

        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.json.return_value = {"value": []}

        # Mock refresh token request
        mock_refresh_resp = MagicMock()
        mock_refresh_resp.status_code = 200
        mock_refresh_resp.json.return_value = {"access_token": "new_token"}

        with patch('source_service.fetchers.onedrive_fetcher.requests.post') as mock_post:
            mock_post.return_value = mock_refresh_resp
            # Order of calls: drive_id, list (401), list after refresh
            mock_request.side_effect = [
                mock_drive_resp, mock_resp_401, mock_resp_ok]

            docs = self.source.list_documents(self.config)
            self.assertEqual(docs, [])
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
