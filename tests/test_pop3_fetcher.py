# tests/test_pop3.py
import poplib
import unittest
from unittest.mock import patch, MagicMock
from source_service.fetchers.pop3_fetcher import POP3Source
from source_service.exceptions import AuthenticationError


class TestPOP3Source(unittest.TestCase):
    def setUp(self):
        self.config = {
            'host': 'pop.example.com',
            'port': 995,
            'username': 'user',
            'password': 'pass',
            'use_ssl': True,
        }
        self.source = POP3Source()

    @patch('source_service.fetchers.pop3_fetcher.poplib.POP3_SSL')
    def test_list_documents_success(self, mock_pop3_ssl):
        mock_conn = MagicMock()
        mock_conn.stat.return_value = (2, 1000)
        mock_conn.top.side_effect = [
            (b'+OK', [b'Subject: Hello', b'From: sender'], b''),
            (b'+OK', [b'Subject: World', b'From: other'], b''),
        ]
        mock_pop3_ssl.return_value = mock_conn

        docs = self.source.list_documents(self.config)
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].metadata['subject'], 'Hello')
        self.assertEqual(docs[1].metadata['subject'], 'World')
        mock_conn.quit.assert_called_once()

    @patch('source_service.fetchers.pop3_fetcher.poplib.POP3_SSL')
    def test_authentication_error(self, mock_pop3_ssl):
        mock_pop3_ssl.side_effect = poplib.error_proto("Authentication failed")
        with self.assertRaises(AuthenticationError):
            self.source.list_documents(self.config)
