import unittest
from unittest.mock import patch, MagicMock
from requests.exceptions import RequestException
from source_service.fetchers.api_fetcher import APISource
from source_service.exceptions import SourceConnectionError, InvalidConfigurationError
from source_service.base import Document


class TestAPISource(unittest.TestCase):
    def setUp(self):
        self.config = {
            'url': 'https://api.example.com/documents',
            'headers': {'Accept': 'application/json'},
        }
        self.source = APISource()

    @patch('source_service.fetchers.api_fetcher.requests.request')
    def test_list_documents_success(self, mock_request):
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {'id': '1', 'metadata': {'name': 'doc1.pdf'}},
            {'id': '2', 'metadata': {'name': 'doc2.pdf'}},
        ]
        mock_request.return_value = mock_response

        docs = self.source.list_documents(self.config)
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].key, '1')

        mock_request.assert_called_once_with(
            'GET',
            'https://api.example.com/documents',
            headers={'Accept': 'application/json'},
            params={},
            auth=None
        )

    @patch('source_service.fetchers.api_fetcher.requests.request')
    def test_list_documents_with_basic_auth(self, mock_request):
        config = self.config.copy()
        config['auth'] = {'username': 'user', 'password': 'pass'}
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_request.return_value = mock_response

        docs = self.source.list_documents(config)
        self.assertEqual(docs, [])
        mock_request.assert_called_once_with(
            'GET',
            'https://api.example.com/documents',
            headers={'Accept': 'application/json'},
            params={},
            auth=('user', 'pass')
        )

    @patch('source_service.fetchers.api_fetcher.requests.request')
    def test_list_documents_with_token_auth(self, mock_request):
        config = self.config.copy()
        config['auth'] = {'token': 'abc123'}
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_request.return_value = mock_response

        docs = self.source.list_documents(config)
        self.assertEqual(docs, [])
        mock_request.assert_called_once_with(
            'GET',
            'https://api.example.com/documents',
            headers={'Accept': 'application/json',
                     'Authorization': 'Bearer abc123'},
            params={},
            auth=None
        )

    @patch('source_service.fetchers.api_fetcher.requests.request')
    def test_list_documents_error(self, mock_request):
        mock_request.side_effect = RequestException("Connection error")
        with self.assertRaises(SourceConnectionError) as ctx:
            self.source.list_documents(self.config)
        self.assertIn("Connection error", str(ctx.exception))

    def test_list_documents_invalid_config(self):
        config = {'headers': {}}
        with self.assertRaises(InvalidConfigurationError) as ctx:
            self.source.list_documents(config)
        self.assertIn("Missing 'url'", str(ctx.exception))

    @patch('source_service.fetchers.api_fetcher.requests.request')
    def test_fetch_document_success(self, mock_request):
        mock_response = MagicMock()
        mock_response.content = b'PDF content'
        mock_response.headers = {'Content-Type': 'application/pdf'}
        mock_request.return_value = mock_response

        doc = self.source.fetch_document(self.config, 'doc1.pdf')
        self.assertEqual(doc.key, 'doc1.pdf')
        self.assertEqual(doc.content, b'PDF content')
        self.assertEqual(doc.metadata['size'], 11)
        self.assertEqual(doc.metadata['content_type'], 'application/pdf')
        mock_request.assert_called_once_with(
            'GET',
            'https://api.example.com/documents/doc1.pdf',
            headers={'Accept': 'application/json'},
            auth=None
        )

    @patch('source_service.fetchers.api_fetcher.requests.request')
    def test_fetch_document_with_basic_auth(self, mock_request):
        config = self.config.copy()
        config['auth'] = {'username': 'user', 'password': 'pass'}
        mock_response = MagicMock()
        mock_response.content = b'content'
        mock_response.headers = {}
        mock_request.return_value = mock_response

        doc = self.source.fetch_document(config, 'doc1.pdf')
        self.assertEqual(doc.content, b'content')
        mock_request.assert_called_once_with(
            'GET',
            'https://api.example.com/documents/doc1.pdf',
            headers={'Accept': 'application/json'},
            auth=('user', 'pass')
        )

    @patch('source_service.fetchers.api_fetcher.requests.request')
    def test_fetch_document_error(self, mock_request):
        mock_request.side_effect = RequestException("404 Not Found")
        with self.assertRaises(SourceConnectionError) as ctx:
            self.source.fetch_document(self.config, 'missing.pdf')
        self.assertIn("404 Not Found", str(ctx.exception))

    @patch.object(APISource, 'fetch_document')
    def test_fetch_documents_with_keys(self, mock_fetch_document):
        doc1 = Document(key='doc1.pdf', metadata={}, content=b'c1')
        doc2 = Document(key='doc2.pdf', metadata={}, content=b'c2')
        mock_fetch_document.side_effect = [doc1, doc2]

        docs = self.source.fetch_documents(
            self.config, keys=['doc1.pdf', 'doc2.pdf'])
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].content, b'c1')
        self.assertEqual(docs[1].content, b'c2')
        self.assertEqual(mock_fetch_document.call_count, 2)

    @patch.object(APISource, 'list_documents')
    def test_fetch_documents_all(self, mock_list_documents):
        doc1 = Document(key='doc1.pdf', metadata={})
        doc2 = Document(key='doc2.pdf', metadata={})
        mock_list_documents.return_value = [doc1, doc2]

        docs = self.source.fetch_documents(self.config, keys=None)
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].key, 'doc1.pdf')
        self.assertEqual(docs[1].key, 'doc2.pdf')
        mock_list_documents.assert_called_once_with(self.config)
