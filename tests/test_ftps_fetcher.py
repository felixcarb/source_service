import unittest
from unittest.mock import patch, MagicMock
from ftplib import error_perm
from source_service.fetchers.ftps_fetcher import FTPSSource
from source_service.exceptions import (
    AuthenticationError,
    DocumentNotFoundError,
    InvalidConfigurationError,
)


class TestFTPSSource(unittest.TestCase):
    def setUp(self):
        self.config = {
            'host': 'ftps.example.com',
            'port': 21,
            'username': 'user',
            'password': 'pass',
            'path': '/docs',
            'passive': True,
            'validate_cert': True,
        }
        self.source = FTPSSource()

    @patch('source_service.fetchers.ftps_fetcher.FTP_TLS')
    def test_list_documents_success(self, mock_ftp_class):
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

        # Verify connection flow
        mock_ftp.connect.assert_called_once_with(
            'ftps.example.com', 21, timeout=30)
        mock_ftp.auth.assert_called_once()
        mock_ftp.login.assert_called_once_with('user', 'pass')
        mock_ftp.set_pasv.assert_called_once_with(True)
        mock_ftp.prot_p.assert_called_once()
        mock_ftp.cwd.assert_called_once_with('/docs')
        mock_ftp.quit.assert_called_once()

    @patch('source_service.fetchers.ftps_fetcher.FTP_TLS')
    def test_authentication_error(self, mock_ftp_class):
        mock_ftp = MagicMock()
        mock_ftp_class.return_value = mock_ftp
        mock_ftp.login.side_effect = error_perm("530 Login incorrect")

        with self.assertRaises(AuthenticationError):
            self.source.list_documents(self.config)

    @patch('source_service.fetchers.ftps_fetcher.FTP_TLS')
    def test_fetch_document_success(self, mock_ftp_class):
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

    @patch('source_service.fetchers.ftps_fetcher.FTP_TLS')
    def test_fetch_document_not_found(self, mock_ftp_class):
        mock_ftp = MagicMock()
        mock_ftp_class.return_value = mock_ftp
        mock_ftp.retrbinary.side_effect = error_perm("550 File not found")

        with self.assertRaises(DocumentNotFoundError):
            self.source.fetch_document(self.config, 'missing.pdf')

    @patch('source_service.fetchers.ftps_fetcher.FTP_TLS')
    def test_invalid_config_missing_host(self, mock_ftp_class):
        config = {'username': 'user'}
        with self.assertRaises(InvalidConfigurationError):
            self.source.list_documents(config)

    @patch('source_service.fetchers.ftps_fetcher.FTP_TLS')
    @patch('source_service.fetchers.ftps_fetcher.ssl.create_default_context')
    def test_implicit_ftps(self, mock_create_context, mock_ftp_class):
        config = self.config.copy()
        config['implicit'] = True
        config['port'] = 990
        mock_ftp = MagicMock()
        mock_ftp_class.return_value = mock_ftp
        mock_ftp.retrlines.side_effect = lambda cmd, callback: None

        # Guardar referencia al socket que se usará
        socket_mock = mock_ftp.sock

        mock_context = MagicMock()
        mock_create_context.return_value = mock_context

        self.source.list_documents(config)

        mock_create_context.assert_called_once()
        mock_context.wrap_socket.assert_called_once_with(
            socket_mock, server_hostname=config['host'])
        mock_ftp.auth.assert_not_called()
        mock_ftp.prot_p.assert_not_called()
        mock_ftp.login.assert_called_once_with('user', 'pass')
