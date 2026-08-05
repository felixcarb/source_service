import unittest
from unittest.mock import patch, MagicMock
from source_service.fetchers.drive_fetcher import DriveSource
from source_service.exceptions import AuthenticationError


class TestDriveSource(unittest.TestCase):
    def setUp(self):
        self.config = {
            'access_token': 'test_token',
            'client_id': 'test_client',
            'client_secret': 'test_secret',
            'refresh_token': 'test_refresh',
        }
        self.source = DriveSource()

    @patch('source_service.fetchers.drive_fetcher.requests.request')
    def test_list_documents_success(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "files": [
                {"id": "file1", "name": "doc1.pdf", "mimeType": "application/pdf",
                    "size": 1024, "modifiedTime": "2023-01-01T00:00:00Z"},
                {"id": "file2", "name": "doc2.txt", "mimeType": "text/plain",
                    "size": 2048, "modifiedTime": "2023-01-02T00:00:00Z"},
            ],
            "nextPageToken": None
        }
        mock_request.return_value = mock_resp

        docs = self.source.list_documents(self.config)
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].key, "file1")
        self.assertEqual(docs[0].metadata['name'], "doc1.pdf")
        self.assertEqual(docs[1].key, "file2")

        # Verify the request URL and params
        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        self.assertEqual(args[0], 'GET')
        self.assertIn('https://www.googleapis.com/drive/v3/files', args[1])
        self.assertIn('q', kwargs['params'])
        self.assertIn("trashed = false", kwargs['params']['q'])
        self.assertIn(
            "mimeType != 'application/vnd.google-apps.folder'", kwargs['params']['q'])

    @patch('source_service.fetchers.drive_fetcher.requests.request')
    def test_fetch_document_regular_file(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"PDF content"
        mock_request.return_value = mock_resp

        # Mock metadata request
        mock_meta_resp = MagicMock()
        mock_meta_resp.status_code = 200
        mock_meta_resp.json.return_value = {
            "id": "file1",
            "name": "doc1.pdf",
            "mimeType": "application/pdf",
            "size": 1024,
            "modifiedTime": "2023-01-01T00:00:00Z"
        }
        # Make first call return metadata, second return content
        mock_request.side_effect = [mock_meta_resp, mock_resp]

        doc = self.source.fetch_document(self.config, "file1")
        self.assertEqual(doc.key, "file1")
        self.assertEqual(doc.content, b"PDF content")
        self.assertEqual(doc.metadata['name'], "doc1.pdf")
        self.assertEqual(doc.metadata['mime_type'], "application/pdf")
        self.assertEqual(mock_request.call_count, 2)

    @patch('source_service.fetchers.drive_fetcher.requests.request')
    def test_fetch_document_google_workspace(self, mock_request):
        # First call: metadata (Google Doc)
        mock_meta_resp = MagicMock()
        mock_meta_resp.status_code = 200
        mock_meta_resp.json.return_value = {
            "id": "doc123",
            "name": "My Document",
            "mimeType": "application/vnd.google-apps.document",
            "modifiedTime": "2023-01-01T00:00:00Z"
        }
        # Second call: export
        mock_export_resp = MagicMock()
        mock_export_resp.status_code = 200
        mock_export_resp.content = b"PDF exported content"
        mock_request.side_effect = [mock_meta_resp, mock_export_resp]

        doc = self.source.fetch_document(self.config, "doc123")
        self.assertEqual(doc.key, "doc123")
        self.assertEqual(doc.content, b"PDF exported content")
        self.assertEqual(doc.metadata['mime_type'],
                         "application/pdf")  # exported
        self.assertEqual(mock_request.call_count, 2)

    @patch('source_service.fetchers.drive_fetcher.requests.request')
    def test_authentication_error(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_request.return_value = mock_resp

        with self.assertRaises(AuthenticationError):
            self.source.list_documents(self.config)

    @patch('source_service.fetchers.drive_fetcher.requests.request')
    def test_token_refresh_on_401(self, mock_request):
        # First request returns 401, second succeeds
        mock_resp_401 = MagicMock()
        mock_resp_401.status_code = 401

        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.json.return_value = {"files": []}

        # Mock refresh token request
        mock_refresh = MagicMock()
        mock_refresh.status_code = 200
        mock_refresh.json.return_value = {"access_token": "new_token"}

        # Configure side_effect: first call is the refresh, then list request returns 401, then list request returns 200
        # Actually, _request calls refresh internally, then retries.
        # So we need to mock requests.post for refresh, and requests.request for the API calls.
        with patch('source_service.fetchers.drive_fetcher.requests.post') as mock_post:
            mock_post.return_value = mock_refresh
            mock_request.side_effect = [mock_resp_401, mock_resp_ok]

            docs = self.source.list_documents(self.config)
            self.assertEqual(docs, [])
            # Verify refresh was called
            mock_post.assert_called_once_with(
                "https://oauth2.googleapis.com/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": "test_refresh",
                    "client_id": "test_client",
                    "client_secret": "test_secret",
                },
                timeout=30
            )
