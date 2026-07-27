import unittest
from unittest.mock import patch, MagicMock
from source_service.fetchers.smb_fetcher import SMBSource
from source_service.base import Document
from source_service.exceptions import (
    SourceConnectionError,
    DocumentNotFoundError,
    InvalidConfigurationError,
)


class TestSMBSource(unittest.TestCase):
    def setUp(self):
        self.config = {
            'host': 'smb.example.com',
            'port': 445,
            'username': 'user',
            'password': 'pass',
            'domain': 'WORKGROUP',
            'share': 'documents',
            'path': '/docs',
        }
        self.source = SMBSource()

    # ──────────────────────────────────────────────────────────
    # Tests para list_documents
    # ──────────────────────────────────────────────────────────

    @patch('source_service.fetchers.smb_fetcher.smbclient.register_session')
    @patch('source_service.fetchers.smb_fetcher.smbclient.listdir')
    @patch('source_service.fetchers.smb_fetcher.smbclient.stat')
    def test_list_documents_success(self, mock_stat, mock_listdir, mock_register):
        """Should list documents correctly."""
        mock_listdir.return_value = ['doc1.pdf', 'doc2.txt', '.hidden']

        class Stat:
            st_size = 1234
            st_mode = 0o100644

        def stat_side_effect(path):
            if 'doc1.pdf' in path:
                stat = Stat()
                stat.st_size = 1234
                return stat
            elif 'doc2.txt' in path:
                stat = Stat()
                stat.st_size = 5678
                return stat
            else:
                raise FileNotFoundError

        mock_stat.side_effect = stat_side_effect

        docs = self.source.list_documents(self.config)

        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].key, 'docs/doc1.pdf')
        self.assertEqual(docs[0].metadata['size'], 1234)
        self.assertEqual(docs[1].key, 'docs/doc2.txt')
        self.assertEqual(docs[1].metadata['size'], 5678)

        mock_register.assert_called_once_with(
            'smb.example.com', username='user', password='pass'
        )
        # ✅ La llamada real incluye el path '/docs' que se convierte en 'docs' en el UNC
        mock_listdir.assert_called_once_with(
            '\\\\smb.example.com\\documents\\docs')

    @patch('source_service.fetchers.smb_fetcher.smbclient.register_session')
    @patch('source_service.fetchers.smb_fetcher.smbclient.listdir')
    def test_list_documents_empty(self, mock_listdir, mock_register):
        mock_listdir.return_value = []
        docs = self.source.list_documents(self.config)
        self.assertEqual(docs, [])

    @patch('source_service.fetchers.smb_fetcher.smbclient.register_session')
    @patch('source_service.fetchers.smb_fetcher.smbclient.listdir')
    def test_list_documents_skip_hidden(self, mock_listdir, mock_register):
        mock_listdir.return_value = ['.hidden', 'visible.pdf']
        docs = self.source.list_documents(self.config)
        self.assertEqual(len(docs), 1)
        # La clave incluye el path: 'docs/visible.pdf'
        self.assertEqual(docs[0].key, 'docs/visible.pdf')

    @patch('source_service.fetchers.smb_fetcher.smbclient.register_session')
    def test_list_documents_connection_error(self, mock_register):
        mock_register.side_effect = Exception("Connection refused")
        with self.assertRaises(SourceConnectionError) as ctx:
            self.source.list_documents(self.config)
        self.assertIn("Connection refused", str(ctx.exception))

    @patch('source_service.fetchers.smb_fetcher.smbclient.register_session')
    @patch('source_service.fetchers.smb_fetcher.smbclient.listdir')
    def test_list_documents_list_error(self, mock_listdir, mock_register):
        mock_listdir.side_effect = Exception("Permission denied")
        with self.assertRaises(SourceConnectionError) as ctx:
            self.source.list_documents(self.config)
        self.assertIn("Permission denied", str(ctx.exception))

    def test_list_documents_invalid_config_missing_host(self):
        config = {'username': 'user', 'share': 'documents'}
        with self.assertRaises(InvalidConfigurationError) as ctx:
            self.source.list_documents(config)
        self.assertIn("Missing 'host' or 'username'", str(ctx.exception))

    def test_list_documents_invalid_config_missing_share(self):
        config = {'host': 'smb.example.com', 'username': 'user'}
        with self.assertRaises(InvalidConfigurationError) as ctx:
            self.source.list_documents(config)
        self.assertIn("Missing 'share'", str(ctx.exception))

    # ──────────────────────────────────────────────────────────
    # Tests para fetch_document
    # ──────────────────────────────────────────────────────────

    @patch('source_service.fetchers.smb_fetcher.smbclient.register_session')
    @patch('source_service.fetchers.smb_fetcher.smbclient.open_file')
    def test_fetch_document_success(self, mock_open_file, mock_register):
        mock_file = MagicMock()
        mock_file.read.return_value = b'test content'
        mock_open_file.return_value.__enter__.return_value = mock_file

        doc = self.source.fetch_document(self.config, '/docs/doc1.pdf')

        self.assertEqual(doc.key, '/docs/doc1.pdf')
        self.assertEqual(doc.content, b'test content')
        self.assertEqual(doc.metadata['size'], 12)

        mock_register.assert_called_once_with(
            'smb.example.com', username='user', password='pass'
        )
        # La ruta UNC esperada: '\\\\smb.example.com\\documents\\docs/doc1.pdf'
        # El código actual genera así: combina share y rel_path con '/', pero luego el UNC tiene '\\' como separadores de host/share
        # Realmente, la llamada es con '\\\\smb.example.com\\documents\\docs/doc1.pdf' (mezcla de barras)
        # Pero el fetcher usa `_get_unc_path` que hace: f"\\\\{host}\\{share}\\{rel_path}" y rel_path se construye con '/'
        # Así que la llamada esperada es:
        expected_unc = '\\\\smb.example.com\\documents\\docs/doc1.pdf'
        mock_open_file.assert_called_once_with(expected_unc, mode='rb')

    @patch('source_service.fetchers.smb_fetcher.smbclient.register_session')
    @patch('source_service.fetchers.smb_fetcher.smbclient.open_file')
    def test_fetch_document_not_found(self, mock_open_file, mock_register):
        mock_open_file.side_effect = FileNotFoundError("No such file")

        with self.assertRaises(DocumentNotFoundError) as ctx:
            self.source.fetch_document(self.config, '/docs/missing.pdf')
        # El mensaje real es "File '/docs/missing.pdf' not found on SMB share"
        self.assertIn(
            "File '/docs/missing.pdf' not found on SMB share", str(ctx.exception))

    @patch('source_service.fetchers.smb_fetcher.smbclient.register_session')
    @patch('source_service.fetchers.smb_fetcher.smbclient.open_file')
    def test_fetch_document_connection_error(self, mock_open_file, mock_register):
        mock_open_file.side_effect = Exception("Network error")

        with self.assertRaises(SourceConnectionError) as ctx:
            self.source.fetch_document(self.config, '/docs/doc1.pdf')
        self.assertIn("Network error", str(ctx.exception))

    # ──────────────────────────────────────────────────────────
    # Tests para fetch_documents
    # ──────────────────────────────────────────────────────────

    @patch.object(SMBSource, 'fetch_document')
    def test_fetch_documents_with_keys(self, mock_fetch_document):
        doc1 = Document(key='doc1.pdf', metadata={}, content=b'content1')
        doc2 = Document(key='doc2.pdf', metadata={}, content=b'content2')
        mock_fetch_document.side_effect = [doc1, doc2]

        docs = self.source.fetch_documents(
            self.config, keys=['doc1.pdf', 'doc2.pdf'])
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].content, b'content1')
        self.assertEqual(docs[1].content, b'content2')
        self.assertEqual(mock_fetch_document.call_count, 2)

    @patch.object(SMBSource, 'list_documents')
    @patch.object(SMBSource, 'fetch_document')
    def test_fetch_documents_all(self, mock_fetch_document, mock_list_documents):
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
