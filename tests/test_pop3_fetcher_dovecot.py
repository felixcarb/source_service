import unittest
from source_service.fetchers.pop3_fetcher import POP3Source
from source_service.exceptions import (
    AuthenticationError,
    SourceConnectionError,
)


class TestPOP3SourceIntegration(unittest.TestCase):
    """Tests de integración con un servidor Dovecot real en Docker."""

    @classmethod
    def setUpClass(cls):
        cls.config = {
            "host": "localhost",
            "port": 1110,
            "username": "testuser",
            "password": "testpass",
            "use_ssl": False,
            "timeout": 10,
        }
        cls.fetcher = POP3Source()
        try:
            conn = cls.fetcher._connect(cls.config)
            conn.quit()
        except Exception as e:
            raise unittest.SkipTest(f"Dovecot server not available: {e}")

    def test_integration_list_documents(self):
        docs = self.fetcher.list_documents(self.config)
        self.assertGreater(len(docs), 0, "Should list at least one email")
        for doc in docs:
            self.assertTrue(doc.key.startswith("msg_"))
            self.assertIn('subject', doc.metadata)
            self.assertIn('message_number', doc.metadata)

    def test_integration_fetch_attachment(self):
        docs = self.fetcher.list_documents(self.config)
        if not docs:
            self.skipTest("No emails found")
        doc = self.fetcher.fetch_document(self.config, docs[0].key)
        self.assertIsNotNone(doc.content)
        self.assertGreater(len(doc.content), 0)

    def test_integration_fetch_nonexistent(self):
        with self.assertRaises(SourceConnectionError):
            self.fetcher.fetch_document(self.config, "msg_999")

    def test_integration_authentication_failure(self):
        bad_config = self.config.copy()
        bad_config["password"] = "wrongpass"
        with self.assertRaises(AuthenticationError):
            self.fetcher.list_documents(bad_config)


if __name__ == "__main__":
    unittest.main()
