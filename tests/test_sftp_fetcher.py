import unittest
from unittest.mock import patch, MagicMock
from paramiko import AuthenticationException, SFTPClient
import socket  # Importar socket para mockear
from source_service.fetchers.sftp_fetcher import SFTPSource
from source_service.base import Document
from source_service.exceptions import (
    SourceConnectionError,
    AuthenticationError,
    DocumentNotFoundError,
)


class TestSFTPSource(unittest.TestCase):
    def setUp(self):
        self.config = {
            'host': 'sftp.example.com',
            'port': 22,
            'username': 'user',
            'password': 'pass',
            'path': '/documents',
        }
        self.fetcher = SFTPSource()

    # Añadir un decorador para mockear socket.socket en todos los tests que usen _connect
    # O puedes aplicar el patch en cada método individualmente.

    @patch('socket.socket')
    @patch('source_service.fetchers.sftp_fetcher.paramiko.Transport')
    @patch('source_service.fetchers.sftp_fetcher.paramiko.SFTPClient.from_transport')
    def test_list_documents_success(self, mock_sftp_from_transport, mock_transport, mock_socket):
        # Mock del socket
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock

        mock_sftp = MagicMock(spec=SFTPClient)
        mock_sftp_from_transport.return_value = mock_sftp

        class Attr:
            filename = 'doc1.pdf'
            st_size = 1234
            st_mtime = 1234567890
            st_mode = 33188
            st_uid = 1000
            st_gid = 1000

        mock_sftp.listdir_attr.return_value = [
            Attr(),
            type('Attr', (), {'filename': 'doc2.txt', 'st_size': 5678,
                 'st_mtime': 1234567891, 'st_mode': 33188, 'st_uid': 1000, 'st_gid': 1000})(),
            type('Attr', (), {'filename': '.hidden', 'st_size': 0, 'st_mtime': 0,
                 'st_mode': 33188, 'st_uid': 1000, 'st_gid': 1000})(),
        ]

        docs = self.fetcher.list_documents(self.config)

        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].key, '/documents/doc1.pdf')
        self.assertEqual(docs[0].metadata['size'], 1234)
        self.assertEqual(docs[1].key, '/documents/doc2.txt')
        self.assertEqual(docs[1].metadata['size'], 5678)

        mock_sock.connect.assert_called_once_with(('sftp.example.com', 22))
        mock_transport.assert_called_once_with(mock_sock)
        mock_transport.return_value.connect.assert_called_once_with(
            username='user', password='pass')
        mock_sftp.listdir_attr.assert_called_once_with('/documents')
        mock_sftp.close.assert_called_once()

    @patch('socket.socket')
    @patch('source_service.fetchers.sftp_fetcher.paramiko.Transport')
    @patch('source_service.fetchers.sftp_fetcher.paramiko.SFTPClient.from_transport')
    def test_list_documents_empty(self, mock_sftp_from_transport, mock_transport, mock_socket):
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        mock_sftp = MagicMock(spec=SFTPClient)
        mock_sftp_from_transport.return_value = mock_sftp
        mock_sftp.listdir_attr.return_value = []

        docs = self.fetcher.list_documents(self.config)
        self.assertEqual(docs, [])

    @patch('socket.socket')
    @patch('source_service.fetchers.sftp_fetcher.paramiko.Transport')
    def test_list_documents_authentication_error(self, mock_transport, mock_socket):
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        # Simular que la autenticación falla
        mock_transport.return_value.connect.side_effect = AuthenticationException(
            "Authentication failed")

        with self.assertRaises(AuthenticationError) as ctx:
            self.fetcher.list_documents(self.config)
        self.assertIn("Authentication failed", str(ctx.exception))

    @patch('socket.socket')
    @patch('source_service.fetchers.sftp_fetcher.paramiko.Transport')
    @patch('source_service.fetchers.sftp_fetcher.paramiko.SFTPClient.from_transport')
    def test_list_documents_connection_error(self, mock_sftp_from_transport, mock_transport, mock_socket):
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        # Simular que el socket lanza un timeout
        mock_sock.connect.side_effect = socket.timeout("timed out")

        # El método _connect captura socket.timeout y lanza SourceConnectionError con el mensaje adecuado
        with self.assertRaises(SourceConnectionError) as ctx:
            self.fetcher.list_documents(self.config)
        self.assertIn("SFTP connection timeout", str(ctx.exception))

    @patch('socket.socket')
    @patch('source_service.fetchers.sftp_fetcher.paramiko.Transport')
    @patch('source_service.fetchers.sftp_fetcher.paramiko.SFTPClient.from_transport')
    def test_fetch_document_success(self, mock_sftp_from_transport, mock_transport, mock_socket):
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        mock_sftp = MagicMock(spec=SFTPClient)
        mock_sftp_from_transport.return_value = mock_sftp

        mock_file = MagicMock()
        mock_file.read.return_value = b'PDF content'
        mock_sftp.open.return_value.__enter__.return_value = mock_file

        class Attr:
            st_size = 1234
            st_mtime = 1234567890
            st_mode = 33188
        mock_sftp.stat.return_value = Attr()

        doc = self.fetcher.fetch_document(self.config, '/documents/report.pdf')

        self.assertEqual(doc.key, '/documents/report.pdf')
        self.assertEqual(doc.content, b'PDF content')
        self.assertEqual(doc.metadata['size'], 1234)
        mock_sftp.open.assert_called_once_with('/documents/report.pdf', 'rb')
        mock_sftp.stat.assert_called_once_with('/documents/report.pdf')
        mock_sftp.close.assert_called_once()

    @patch('socket.socket')
    @patch('source_service.fetchers.sftp_fetcher.paramiko.Transport')
    @patch('source_service.fetchers.sftp_fetcher.paramiko.SFTPClient.from_transport')
    def test_fetch_document_not_found(self, mock_sftp_from_transport, mock_transport, mock_socket):
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        mock_sftp = MagicMock(spec=SFTPClient)
        mock_sftp_from_transport.return_value = mock_sftp
        mock_sftp.open.side_effect = FileNotFoundError("No such file")

        with self.assertRaises(DocumentNotFoundError) as ctx:
            self.fetcher.fetch_document(self.config, 'missing.pdf')
        self.assertIn("'missing.pdf' not found", str(ctx.exception))

    @patch('socket.socket')
    @patch('source_service.fetchers.sftp_fetcher.paramiko.Transport')
    @patch('source_service.fetchers.sftp_fetcher.paramiko.SFTPClient.from_transport')
    def test_fetch_documents_with_keys(self, mock_sftp_from_transport, mock_transport, mock_socket):
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        mock_sftp = MagicMock(spec=SFTPClient)
        mock_sftp_from_transport.return_value = mock_sftp

        mock_file = MagicMock()
        mock_file.read.return_value = b'content'
        mock_sftp.open.return_value.__enter__.return_value = mock_file

        class Attr:
            st_size = 10
            st_mtime = 0
            st_mode = 0
        mock_sftp.stat.return_value = Attr()

        keys = ['file1.pdf', 'file2.pdf']
        docs = self.fetcher.fetch_documents(self.config, keys)

        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].key, 'file1.pdf')
        self.assertEqual(docs[1].key, 'file2.pdf')
        self.assertEqual(mock_sftp.open.call_count, 2)

    @patch.object(SFTPSource, 'list_documents')
    @patch('socket.socket')
    @patch('source_service.fetchers.sftp_fetcher.paramiko.Transport')
    @patch('source_service.fetchers.sftp_fetcher.paramiko.SFTPClient.from_transport')
    def test_fetch_documents_all(self, mock_sftp_from_transport, mock_transport, mock_socket, mock_list_documents):
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock
        doc1 = Document(key='/doc/a.pdf', metadata={'size': 10})
        doc2 = Document(key='/doc/b.pdf', metadata={'size': 20})
        mock_list_documents.return_value = [doc1, doc2]

        mock_sftp = MagicMock(spec=SFTPClient)
        mock_sftp_from_transport.return_value = mock_sftp

        mock_file = MagicMock()
        mock_file.read.return_value = b'content'
        mock_sftp.open.return_value.__enter__.return_value = mock_file

        class Attr:
            st_size = 10
            st_mtime = 0
            st_mode = 0
        mock_sftp.stat.return_value = Attr()

        docs = self.fetcher.fetch_documents(self.config, keys=None)

        self.assertEqual(len(docs), 2)
        self.assertEqual(mock_sftp.open.call_count, 2)
        mock_list_documents.assert_called_once_with(self.config)

    @patch('socket.socket')
    @patch('source_service.fetchers.sftp_fetcher.paramiko.Transport')
    @patch('source_service.fetchers.sftp_fetcher.paramiko.SFTPClient.from_transport')
    def test_ssh_key_authentication(self, mock_sftp_from_transport, mock_transport, mock_socket):
        config = self.config.copy()
        config['ssh_key_path'] = '/path/to/key'
        mock_sock = MagicMock()
        mock_socket.return_value = mock_sock

        mock_transport_instance = MagicMock()
        mock_transport.return_value = mock_transport_instance

        mock_sftp = MagicMock(spec=SFTPClient)
        mock_sftp_from_transport.return_value = mock_sftp
        mock_sftp.listdir_attr.return_value = []

        with patch('paramiko.RSAKey.from_private_key_file') as mock_key:
            mock_key.return_value = 'mock_key'
            self.fetcher.list_documents(config)

            mock_key.assert_called_once_with('/path/to/key')
            mock_transport_instance.auth_publickey.assert_called_once_with(
                'user', 'mock_key')
