import unittest
from unittest.mock import patch, MagicMock
from ftplib import error_perm
from source_service.fetchers.ftp_fetcher import FTPSource
from source_service.exceptions import (
    AuthenticationError,
    SourceConnectionError,
    DocumentNotFoundError,
    InvalidConfigurationError,
)
from source_service.base import Document


class TestFTPSource(unittest.TestCase):
    """Test suite for FTP source fetcher."""

    def setUp(self):
        self.config = {
            'host': 'ftp.example.com',
            'port': 21,
            'username': 'user',
            'password': 'pass',
            'path': '/docs',
        }
        self.source = FTPSource()

    # ──────────────────────────────────────────────────────────
    # Tests para list_documents
    # ──────────────────────────────────────────────────────────

    @patch('source_service.fetchers.ftp_fetcher.FTP')
    def test_list_documents_success(self, mock_ftp_class):
        """Should list documents correctly."""
        mock_ftp = MagicMock()
        mock_ftp_class.return_value = mock_ftp

        def retrlines(cmd, callback):
            callback("-rw-r--r-- 1 user group 1234 Jan 1 12:34 doc1.pdf")
            callback("-rw-r--r-- 1 user group 5678 Feb 2 10:20 doc2.txt")
        mock_ftp.retrlines.side_effect = retrlines

        docs = self.source.list_documents(self.config)

        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].key, '/docs/doc1.pdf')
        self.assertEqual(docs[0].metadata['size'], 1234)
        self.assertEqual(docs[1].key, '/docs/doc2.txt')
        self.assertEqual(docs[1].metadata['size'], 5678)

        # Verificar llamadas con timeout
        mock_ftp.connect.assert_called_once_with(
            'ftp.example.com', 21, timeout=30)
        mock_ftp.login.assert_called_once_with('user', 'pass')
        mock_ftp.cwd.assert_called_once_with('/docs')
        mock_ftp.retrlines.assert_called_once()
        mock_ftp.quit.assert_called_once()

    @patch('source_service.fetchers.ftp_fetcher.FTP')
    def test_list_documents_empty(self, mock_ftp_class):
        """Should return empty list when no files are found."""
        mock_ftp = MagicMock()
        mock_ftp_class.return_value = mock_ftp
        mock_ftp.retrlines.side_effect = lambda cmd, callback: None

        docs = self.source.list_documents(self.config)
        self.assertEqual(docs, [])

    @patch('source_service.fetchers.ftp_fetcher.FTP')
    def test_list_documents_skip_hidden_files(self, mock_ftp_class):
        """Should skip hidden files (starting with '.')."""
        mock_ftp = MagicMock()
        mock_ftp_class.return_value = mock_ftp

        def retrlines(cmd, callback):
            callback("-rw-r--r-- 1 user group 1234 Jan 1 12:34 visible.pdf")
            callback("-rw-r--r-- 1 user group 5678 Jan 2 09:00 .hidden")
        mock_ftp.retrlines.side_effect = retrlines

        docs = self.source.list_documents(self.config)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].key, '/docs/visible.pdf')

    @patch('source_service.fetchers.ftp_fetcher.FTP')
    def test_list_documents_parse_line_with_spaces(self, mock_ftp_class):
        """Should parse filenames with spaces correctly."""
        mock_ftp = MagicMock()
        mock_ftp_class.return_value = mock_ftp

        def retrlines(cmd, callback):
            callback("-rw-r--r-- 1 user group 1234 Jan 1 12:34 my document.pdf")
        mock_ftp.retrlines.side_effect = retrlines

        docs = self.source.list_documents(self.config)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].key, '/docs/my document.pdf')

    @patch('source_service.fetchers.ftp_fetcher.FTP')
    def test_list_documents_authentication_error(self, mock_ftp_class):
        """Should raise AuthenticationError on login failure."""
        mock_ftp = MagicMock()
        mock_ftp_class.return_value = mock_ftp
        # Simular error en login (capturado en _connect)
        mock_ftp.login.side_effect = error_perm("530 Login incorrect")

        with self.assertRaises(AuthenticationError) as ctx:
            self.source.list_documents(self.config)
        self.assertIn("Login incorrect", str(ctx.exception))

    @patch('source_service.fetchers.ftp_fetcher.FTP')
    def test_list_documents_connection_error(self, mock_ftp_class):
        """Should raise SourceConnectionError on connection failure."""
        mock_ftp_class.side_effect = Exception("Connection refused")

        with self.assertRaises(SourceConnectionError) as ctx:
            self.source.list_documents(self.config)
        self.assertIn("Connection refused", str(ctx.exception))

    def test_list_documents_invalid_config(self):
        """Should raise InvalidConfigurationError when 'host' is missing."""
        config = {'username': 'user'}  # no host
        with self.assertRaises(InvalidConfigurationError) as ctx:
            self.source.list_documents(config)
        self.assertIn("Missing 'host'", str(ctx.exception))

    # ──────────────────────────────────────────────────────────
    # Tests para fetch_document
    # ──────────────────────────────────────────────────────────

    @patch('source_service.fetchers.ftp_fetcher.FTP')
    def test_fetch_document_success(self, mock_ftp_class):
        """Should fetch a single document successfully."""
        mock_ftp = MagicMock()
        mock_ftp_class.return_value = mock_ftp
        mock_ftp.size.return_value = 10
        mock_ftp.retrbinary.side_effect = lambda cmd, callback: callback(
            b'content')

        doc = self.source.fetch_document(self.config, '/docs/doc1.pdf')

        self.assertEqual(doc.content, b'content')
        self.assertEqual(doc.metadata['size'], 10)
        mock_ftp.cwd.assert_called_once_with('/docs')
        mock_ftp.retrbinary.assert_called_once_with(
            'RETR doc1.pdf', mock_ftp.retrbinary.call_args[0][1])

    @patch('source_service.fetchers.ftp_fetcher.FTP')
    def test_fetch_document_without_leading_slash(self, mock_ftp_class):
        """Should handle key without leading slash."""
        mock_ftp = MagicMock()
        mock_ftp_class.return_value = mock_ftp
        mock_ftp.size.return_value = 7
        mock_ftp.retrbinary.side_effect = lambda cmd, callback: callback(
            b'data')

        doc = self.source.fetch_document(self.config, 'docs/doc1.pdf')
        self.assertEqual(doc.key, 'docs/doc1.pdf')
        mock_ftp.cwd.assert_called_once_with('docs')
        mock_ftp.retrbinary.assert_called_once_with(
            'RETR doc1.pdf', mock_ftp.retrbinary.call_args[0][1])

    @patch('source_service.fetchers.ftp_fetcher.FTP')
    def test_fetch_document_not_found(self, mock_ftp_class):
        """Should raise DocumentNotFoundError when file is missing."""
        mock_ftp = MagicMock()
        mock_ftp_class.return_value = mock_ftp
        mock_ftp.retrbinary.side_effect = error_perm("550 File not found")

        with self.assertRaises(DocumentNotFoundError) as ctx:
            self.source.fetch_document(self.config, 'missing.pdf')
        self.assertIn("'missing.pdf' not found", str(ctx.exception))

    @patch('source_service.fetchers.ftp_fetcher.FTP')
    def test_fetch_document_connection_error(self, mock_ftp_class):
        """Should raise SourceConnectionError on fetch failure."""
        mock_ftp = MagicMock()
        mock_ftp_class.return_value = mock_ftp
        mock_ftp.retrbinary.side_effect = Exception("Timeout")

        with self.assertRaises(SourceConnectionError) as ctx:
            self.source.fetch_document(self.config, 'doc1.pdf')
        self.assertIn("Timeout", str(ctx.exception))

    # ──────────────────────────────────────────────────────────
    # Tests para fetch_documents
    # ──────────────────────────────────────────────────────────

    @patch.object(FTPSource, 'fetch_document')
    def test_fetch_documents_with_keys(self, mock_fetch_document):
        """Should fetch specific documents by keys."""
        doc1 = Document(key='doc1.pdf', metadata={}, content=b'content1')
        doc2 = Document(key='doc2.pdf', metadata={}, content=b'content2')
        mock_fetch_document.side_effect = [doc1, doc2]

        docs = self.source.fetch_documents(
            self.config, keys=['doc1.pdf', 'doc2.pdf'])
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].content, b'content1')
        self.assertEqual(docs[1].content, b'content2')
        self.assertEqual(mock_fetch_document.call_count, 2)

    @patch.object(FTPSource, 'list_documents')
    @patch.object(FTPSource, 'fetch_document')
    def test_fetch_documents_all(self, mock_fetch_document, mock_list_documents):
        """Should fetch all documents when keys is None."""
        doc1 = Document(key='/docs/a.pdf', metadata={'size': 10})
        doc2 = Document(key='/docs/b.pdf', metadata={'size': 20})
        mock_list_documents.return_value = [doc1, doc2]

        mock_fetch_document.side_effect = [
            Document(key='/docs/a.pdf', metadata={'size': 10}, content=b'a'),
            Document(key='/docs/b.pdf', metadata={'size': 20}, content=b'b'),
        ]

        docs = self.source.fetch_documents(self.config, keys=None)
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].content, b'a')
        self.assertEqual(docs[1].content, b'b')
        mock_list_documents.assert_called_once_with(self.config)
        self.assertEqual(mock_fetch_document.call_count, 2)
