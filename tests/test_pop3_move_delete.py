import unittest
from source_service.fetchers.pop3_fetcher import POP3Source


class TestPOP3SourceOperations(unittest.TestCase):
    """Pruebas para métodos move/delete de POP3 (siempre retornan False)."""

    def setUp(self):
        self.fetcher = POP3Source()
        self.config = {
            'host': 'mail.example.com',
            'username': 'user',
            'password': 'pass',
        }
        self.key = 'msg_1'
        self.destination = '/some/path'

    def test_move_document_returns_false(self):
        """Verifica que move_document siempre retorna False sin conectar."""
        result = self.fetcher.move_document(
            self.config, self.key, self.destination)
        self.assertFalse(result)

    def test_delete_document_returns_false(self):
        """Verifica que delete_document siempre retorna False sin conectar."""
        result = self.fetcher.delete_document(self.config, self.key)
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
