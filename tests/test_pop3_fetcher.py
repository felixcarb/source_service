"""
Tests con mocks para POP3Source.

A diferencia de test_pop3_fetcher_dovecot.py (que requiere un servidor
Dovecot real en localhost:1110), estos tests mockean poplib.POP3 /
poplib.POP3_SSL para poder correr en CI sin infraestructura externa,
y cubren casos límite que el test contra Dovecot no ejercita:
autenticación fallida, errores de red, mailbox vacío, mensajes sin
adjuntos, tipos de adjunto no soportados, fallback TOP->RETR, claves
inválidas, fallos parciales en fetch_documents y el cierre de conexión.
"""

import email.policy
import poplib
import unittest
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

from source_service.exceptions import (
    AuthenticationError,
    DocumentNotFoundError,
    InvalidConfigurationError,
    SourceConnectionError,
)
from source_service.fetchers.pop3_fetcher import POP3Source


def make_config(**overrides):
    config = {
        "host": "localhost",
        "port": 1110,
        "username": "testuser",
        "password": "testpass",
        "use_ssl": False,
        "timeout": 10,
    }
    config.update(overrides)
    return config


def build_message(
    subject="Test subject",
    from_addr="sender@example.com",
    to_addr="receiver@example.com",
    body="Hello world",
    attachment=None,
):
    """attachment: optional (filename, content_bytes, content_type) tuple."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Date"] = "Mon, 01 Jan 2024 00:00:00 +0000"
    msg["Message-ID"] = "<abc123@example.com>"
    msg.set_content(body)
    if attachment:
        filename, content, content_type = attachment
        maintype, subtype = content_type.split("/", 1)
        msg.add_attachment(content, maintype=maintype,
                           subtype=subtype, filename=filename)
    return msg


def message_lines(msg):
    """Convert an EmailMessage into the list-of-bytes-lines shape poplib returns."""
    raw = msg.as_bytes(policy=email.policy.default)
    return raw.split(b"\r\n")


class TestPOP3SourceConnection(unittest.TestCase):
    def setUp(self):
        self.fetcher = POP3Source()

    def test_missing_host_raises_invalid_configuration(self):
        config = make_config()
        del config["host"]
        with self.assertRaises(InvalidConfigurationError):
            self.fetcher.list_documents(config)

    def test_missing_multiple_fields_lists_all_in_message(self):
        config = make_config()
        del config["username"]
        del config["password"]
        with self.assertRaises(InvalidConfigurationError) as ctx:
            self.fetcher.list_documents(config)
        self.assertIn("username", str(ctx.exception))
        self.assertIn("password", str(ctx.exception))

    @patch("poplib.POP3")
    def test_authentication_failure_raises_authentication_error(self, mock_pop3_cls):
        mock_conn = MagicMock()
        mock_conn.pass_.side_effect = poplib.error_proto(
            "-ERR authentication failed")
        mock_pop3_cls.return_value = mock_conn

        with self.assertRaises(AuthenticationError):
            self.fetcher.list_documents(make_config())

        # Even on auth failure we should attempt to close the connection.
        self.assertTrue(mock_conn.quit.called or mock_conn.close.called)

    @patch("poplib.POP3")
    def test_connection_refused_raises_source_connection_error(self, mock_pop3_cls):
        mock_pop3_cls.side_effect = ConnectionRefusedError("refused")
        with self.assertRaises(SourceConnectionError):
            self.fetcher.list_documents(make_config())

    @patch("poplib.POP3")
    def test_timeout_raises_source_connection_error(self, mock_pop3_cls):
        mock_pop3_cls.side_effect = TimeoutError("timed out")
        with self.assertRaises(SourceConnectionError):
            self.fetcher.list_documents(make_config())

    @patch("poplib.POP3_SSL")
    def test_ssl_used_when_use_ssl_true(self, mock_pop3_ssl_cls):
        mock_conn = MagicMock()
        mock_conn.stat.return_value = (0, 0)
        mock_conn.list.return_value = ("+OK", [], 0)
        mock_pop3_ssl_cls.return_value = mock_conn

        config = make_config(use_ssl=True, port=995)
        self.fetcher.list_documents(config)

        mock_pop3_ssl_cls.assert_called_once()
        _, kwargs = mock_pop3_ssl_cls.call_args
        self.assertIn("context", kwargs)

    @patch("poplib.POP3_SSL")
    def test_validate_cert_false_disables_verification(self, mock_pop3_ssl_cls):
        mock_conn = MagicMock()
        mock_conn.stat.return_value = (0, 0)
        mock_conn.list.return_value = ("+OK", [], 0)
        mock_pop3_ssl_cls.return_value = mock_conn

        config = make_config(use_ssl=True, validate_cert=False)
        self.fetcher.list_documents(config)

        _, kwargs = mock_pop3_ssl_cls.call_args
        context = kwargs["context"]
        self.assertFalse(context.check_hostname)

    @patch("poplib.POP3")
    def test_default_port_used_when_not_specified(self, mock_pop3_cls):
        mock_conn = MagicMock()
        mock_conn.stat.return_value = (0, 0)
        mock_conn.list.return_value = ("+OK", [], 0)
        mock_pop3_cls.return_value = mock_conn

        config = make_config(use_ssl=False)
        del config["port"]
        self.fetcher.list_documents(config)

        args, _ = mock_pop3_cls.call_args
        self.assertEqual(args[1], 110)

    @patch("poplib.POP3")
    def test_connection_closed_via_quit_after_success(self, mock_pop3_cls):
        mock_conn = MagicMock()
        mock_conn.stat.return_value = (0, 0)
        mock_conn.list.return_value = ("+OK", [], 0)
        mock_pop3_cls.return_value = mock_conn

        self.fetcher.list_documents(make_config())
        mock_conn.quit.assert_called_once()

    @patch("poplib.POP3")
    def test_close_falls_back_when_quit_fails(self, mock_pop3_cls):
        mock_conn = MagicMock()
        mock_conn.stat.return_value = (0, 0)
        mock_conn.list.return_value = ("+OK", [], 0)
        mock_conn.quit.side_effect = OSError("broken pipe")
        mock_pop3_cls.return_value = mock_conn

        # Should not raise even though quit() fails.
        self.fetcher.list_documents(make_config())
        mock_conn.close.assert_called_once()


class TestPOP3SourceListDocuments(unittest.TestCase):
    def setUp(self):
        self.fetcher = POP3Source()

    @patch("poplib.POP3")
    def test_empty_mailbox_returns_empty_list(self, mock_pop3_cls):
        mock_conn = MagicMock()
        mock_conn.stat.return_value = (0, 0)
        mock_conn.list.return_value = ("+OK", [], 0)
        mock_pop3_cls.return_value = mock_conn

        docs = self.fetcher.list_documents(make_config())
        self.assertEqual(docs, [])

    @patch("poplib.POP3")
    def test_multiple_messages_produce_sequential_keys(self, mock_pop3_cls):
        mock_conn = MagicMock()
        mock_conn.stat.return_value = (3, 6000)
        mock_conn.list.return_value = (
            "+OK", [b"1 1000", b"2 2000", b"3 3000"], 0)

        msg = build_message(subject="Hi")
        lines = message_lines(msg)
        mock_conn.top.return_value = ("+OK", lines, 0)
        mock_pop3_cls.return_value = mock_conn

        docs = self.fetcher.list_documents(make_config())

        self.assertEqual([d.key for d in docs], ["msg_1", "msg_2", "msg_3"])
        self.assertEqual(docs[0].metadata["size"], 1000)
        self.assertEqual(docs[0].metadata["mailbox_size"], 6000)
        self.assertEqual(docs[0].metadata["subject"], "Hi")

    @patch("poplib.POP3")
    def test_top_unsupported_falls_back_to_retr(self, mock_pop3_cls):
        mock_conn = MagicMock()
        mock_conn.stat.return_value = (1, 500)
        mock_conn.list.return_value = ("+OK", [b"1 500"], 0)
        mock_conn.top.side_effect = poplib.error_proto(
            "-ERR TOP not supported")

        msg = build_message(subject="Fallback works")
        lines = message_lines(msg)
        mock_conn.retr.return_value = ("+OK", lines, 0)
        mock_pop3_cls.return_value = mock_conn

        docs = self.fetcher.list_documents(make_config())

        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].metadata["subject"], "Fallback works")
        mock_conn.retr.assert_called()

    @patch("poplib.POP3")
    def test_list_command_failure_is_tolerated(self, mock_pop3_cls):
        """If LIST fails, sizes should just default to 0 rather than raising."""
        mock_conn = MagicMock()
        mock_conn.stat.return_value = (1, 100)
        mock_conn.list.side_effect = poplib.error_proto("-ERR")

        msg = build_message()
        mock_conn.top.return_value = ("+OK", message_lines(msg), 0)
        mock_pop3_cls.return_value = mock_conn

        docs = self.fetcher.list_documents(make_config())
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].metadata["size"], 0)

    @patch("poplib.POP3")
    def test_malformed_list_line_is_ignored(self, mock_pop3_cls):
        mock_conn = MagicMock()
        mock_conn.stat.return_value = (1, 100)
        mock_conn.list.return_value = ("+OK", [b"garbled-line"], 0)

        msg = build_message()
        mock_conn.top.return_value = ("+OK", message_lines(msg), 0)
        mock_pop3_cls.return_value = mock_conn

        docs = self.fetcher.list_documents(make_config())
        self.assertEqual(docs[0].metadata["size"], 0)


class TestPOP3SourceFetchDocument(unittest.TestCase):
    def setUp(self):
        self.fetcher = POP3Source()

    def test_invalid_key_format_raises_document_not_found(self):
        with self.assertRaises(DocumentNotFoundError):
            self.fetcher.fetch_document(make_config(), "not_a_valid_key")

    def test_non_numeric_suffix_raises_document_not_found(self):
        with self.assertRaises(DocumentNotFoundError):
            self.fetcher.fetch_document(make_config(), "msg_abc")

    def test_zero_or_negative_message_number_raises_document_not_found(self):
        with self.assertRaises(DocumentNotFoundError):
            self.fetcher.fetch_document(make_config(), "msg_0")

    @patch("poplib.POP3")
    def test_fetch_message_with_supported_attachment(self, mock_pop3_cls):
        mock_conn = MagicMock()
        msg = build_message(attachment=(
            "test.pdf", b"%PDF-1.4 fake content", "application/pdf"))
        mock_conn.retr.return_value = ("+OK", message_lines(msg), 0)
        mock_pop3_cls.return_value = mock_conn

        doc = self.fetcher.fetch_document(make_config(), "msg_1")

        self.assertEqual(doc.key, "test.pdf")
        self.assertEqual(doc.metadata["content_type"], "application/pdf")
        self.assertIn(b"fake content", doc.content)

    @patch("poplib.POP3")
    def test_fetch_message_without_attachment_returns_raw_message(self, mock_pop3_cls):
        mock_conn = MagicMock()
        msg = build_message(subject="No attachment here")
        mock_conn.retr.return_value = ("+OK", message_lines(msg), 0)
        mock_pop3_cls.return_value = mock_conn

        doc = self.fetcher.fetch_document(make_config(), "msg_5")

        self.assertEqual(doc.key, "message_5")
        self.assertEqual(doc.metadata["content_type"], "message/rfc822")
        self.assertIn(b"No attachment here", doc.content)

    @patch("poplib.POP3")
    def test_unsupported_attachment_type_is_skipped(self, mock_pop3_cls):
        mock_conn = MagicMock()
        # text/plain attachment is not in SUPPORTED_ATTACHMENT_TYPES.
        msg = build_message(attachment=(
            "notes.txt", b"plain text notes", "text/plain"))
        mock_conn.retr.return_value = ("+OK", message_lines(msg), 0)
        mock_pop3_cls.return_value = mock_conn

        doc = self.fetcher.fetch_document(make_config(), "msg_2")

        # Falls back to returning the whole raw message since no supported
        # attachment was found.
        self.assertEqual(doc.key, "message_2")
        self.assertEqual(doc.metadata["content_type"], "message/rfc822")

    @patch("poplib.POP3")
    def test_first_supported_attachment_wins_when_multiple(self, mock_pop3_cls):
        mock_conn = MagicMock()
        msg = EmailMessage()
        msg["Subject"] = "Multi attachment"
        msg["From"] = "sender@example.com"
        msg["To"] = "receiver@example.com"
        msg.set_content("body")
        msg.add_attachment(b"image-bytes", maintype="image",
                           subtype="png", filename="pic.png")
        msg.add_attachment(b"pdf-bytes", maintype="application",
                           subtype="pdf", filename="doc.pdf")
        mock_conn.retr.return_value = ("+OK", message_lines(msg), 0)
        mock_pop3_cls.return_value = mock_conn

        doc = self.fetcher.fetch_document(make_config(), "msg_9")

        self.assertEqual(doc.key, "pic.png")
        self.assertEqual(doc.metadata["content_type"], "image/png")

    @patch("poplib.POP3")
    def test_retr_error_for_missing_message_raises_source_connection_error(self, mock_pop3_cls):
        mock_conn = MagicMock()
        mock_conn.retr.side_effect = poplib.error_proto("-ERR no such message")
        mock_pop3_cls.return_value = mock_conn

        with self.assertRaises(SourceConnectionError):
            self.fetcher.fetch_document(make_config(), "msg_999")

    @patch("poplib.POP3")
    def test_connection_is_closed_after_fetch_even_on_error(self, mock_pop3_cls):
        mock_conn = MagicMock()
        mock_conn.retr.side_effect = poplib.error_proto("-ERR")
        mock_pop3_cls.return_value = mock_conn

        with self.assertRaises(SourceConnectionError):
            self.fetcher.fetch_document(make_config(), "msg_1")

        mock_conn.quit.assert_called_once()


class TestPOP3SourceFetchDocuments(unittest.TestCase):
    def setUp(self):
        self.fetcher = POP3Source()

    @patch("poplib.POP3")
    def test_fetch_documents_with_explicit_keys(self, mock_pop3_cls):
        mock_conn = MagicMock()
        msg = build_message(attachment=(
            "a.pdf", b"content-a", "application/pdf"))
        mock_conn.retr.return_value = ("+OK", message_lines(msg), 0)
        mock_pop3_cls.return_value = mock_conn

        docs = self.fetcher.fetch_documents(make_config(), keys=["msg_1"])

        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].key, "a.pdf")

    @patch("poplib.POP3")
    def test_fetch_documents_skips_individual_failures(self, mock_pop3_cls):
        mock_conn = MagicMock()
        good_msg = build_message(attachment=(
            "ok.pdf", b"ok-content", "application/pdf"))

        def retr_side_effect(number):
            if number == 2:
                raise poplib.error_proto("-ERR broken message")
            return ("+OK", message_lines(good_msg), 0)

        mock_conn.retr.side_effect = retr_side_effect
        mock_pop3_cls.return_value = mock_conn

        docs = self.fetcher.fetch_documents(
            make_config(), keys=["msg_1", "msg_2", "msg_3"])

        # msg_2 fails and is skipped; msg_1 and msg_3 succeed.
        self.assertEqual(len(docs), 2)
        self.assertTrue(all(d.key == "ok.pdf" for d in docs))

    def test_fetch_documents_propagates_invalid_key(self):
        with self.assertRaises(DocumentNotFoundError):
            self.fetcher.fetch_documents(
                make_config(), keys=["totally_invalid"])

    @patch("poplib.POP3")
    def test_fetch_documents_defaults_to_listing_when_keys_none(self, mock_pop3_cls):
        mock_conn = MagicMock()
        mock_conn.stat.return_value = (1, 100)
        mock_conn.list.return_value = ("+OK", [b"1 100"], 0)
        msg = build_message(attachment=(
            "only.pdf", b"only-content", "application/pdf"))
        lines = message_lines(msg)
        mock_conn.top.return_value = ("+OK", lines, 0)
        mock_conn.retr.return_value = ("+OK", lines, 0)
        mock_pop3_cls.return_value = mock_conn

        docs = self.fetcher.fetch_documents(make_config())

        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].key, "only.pdf")


class TestPOP3SourceReadOnlyOperations(unittest.TestCase):
    def setUp(self):
        self.fetcher = POP3Source()

    def test_move_document_returns_false(self):
        self.assertFalse(self.fetcher.move_document(
            make_config(), "msg_1", "Archive"))

    def test_delete_document_returns_false(self):
        self.assertFalse(self.fetcher.delete_document(make_config(), "msg_1"))


if __name__ == "__main__":
    unittest.main()
