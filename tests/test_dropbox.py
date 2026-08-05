import unittest
from unittest.mock import patch, MagicMock
from source_service.fetchers.dropbox_fetcher import DropboxSource
from source_service.exceptions import AuthenticationError


class TestDropboxSource(unittest.TestCase):
    def setUp(self):
        self.config = {
            'access_token': 'test_token',
            'path': '',
        }
        self.source = DropboxSource()

    @patch('source_service.fetchers.dropbox_fetcher.requests.request')
    def test_list_documents_success(self, mock_request):
        # Mock response for list_folder
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "entries": [
                {"name": "doc1.pdf", "path_lower": "/doc1.pdf",
                    "size": 1024, "server_modified": "2023-01-01T00:00:00Z"},
                {"name": "doc2.txt", "path_lower": "/folder/doc2.txt",
                    "size": 2048, "server_modified": "2023-01-02T00:00:00Z"},
            ],
            "has_more": False,
            "cursor": None,
        }
        mock_request.return_value = mock_resp

        docs = self.source.list_documents(self.config)
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].key, "doc1.pdf")
        self.assertEqual(docs[0].metadata['size'], 1024)
        self.assertEqual(docs[1].key, "folder/doc2.txt")
        mock_request.assert_called_once()

    @patch('source_service.fetchers.dropbox_fetcher.requests.request')
    def test_fetch_document_success(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"PDF content"
        mock_resp.headers = {
            'dropbox-api-result': '{"size": 1024, "server_modified": "2023-01-01"}'}
        mock_request.return_value = mock_resp

        doc = self.source.fetch_document(self.config, "doc1.pdf")
        self.assertEqual(doc.key, "doc1.pdf")
        self.assertEqual(doc.content, b"PDF content")
        self.assertEqual(doc.metadata['size'], 1024)
        mock_request.assert_called_once()

    @patch('source_service.fetchers.dropbox_fetcher.requests.request')
    def test_authentication_error(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_request.return_value = mock_resp

        with self.assertRaises(AuthenticationError):
            self.source.list_documents(self.config)
