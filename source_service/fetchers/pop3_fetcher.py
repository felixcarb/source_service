import email
import logging
import poplib
import ssl
from email.policy import default
from typing import Any, Dict, List, Optional

from ..base import DocumentSource, Document
from ..exceptions import SourceConnectionError, AuthenticationError, DocumentNotFoundError, InvalidConfigurationError

logger = logging.getLogger(__name__)
SUPPORTED_ATTACHMENT_TYPES = {"application/octet-stream", "application/pdf", "image/jpeg", "image/png"}


class POP3Source(DocumentSource):
    """Read-only POP3 source."""

    def _connect(self, config: Dict[str, Any]) -> poplib.POP3:
        host = config.get("host")
        username = config.get("username")
        password = config.get("password")
        use_ssl = bool(config.get("use_ssl", True))
        port = int(config.get("port", 995 if use_ssl else 110))
        timeout = float(config.get("timeout", 30))
        validate_cert = bool(config.get("validate_cert", True))
        missing = [k for k, v in (("host", host), ("username", username), ("password", password)) if not v]
        if missing:
            raise InvalidConfigurationError(f"Missing required POP3 configuration: {', '.join(missing)}")
        conn: Optional[poplib.POP3] = None
        try:
            if use_ssl:
                context = ssl.create_default_context()
                if not validate_cert:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                conn = poplib.POP3_SSL(host, port, timeout=timeout, context=context)
            else:
                conn = poplib.POP3(host, port, timeout=timeout)
            conn.user(str(username))
            conn.pass_(str(password))
            return conn
        except poplib.error_proto as exc:
            self._close(conn)
            raise AuthenticationError(f"POP3 authentication failed: {exc}") from exc
        except (OSError, ssl.SSLError, ValueError) as exc:
            self._close(conn)
            raise SourceConnectionError(f"POP3 connection error: {exc}") from exc
        except Exception as exc:
            self._close(conn)
            raise SourceConnectionError(f"POP3 connection error: {exc}") from exc

    @staticmethod
    def _close(conn: Optional[poplib.POP3]) -> None:
        if conn is None:
            return
        try:
            conn.quit()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    @staticmethod
    def _message_number(key: str) -> int:
        if not isinstance(key, str) or not key.startswith("msg_"):
            raise DocumentNotFoundError(f"Invalid POP3 document key: {key!r}")
        try:
            number = int(key[4:])
        except ValueError as exc:
            raise DocumentNotFoundError(f"Invalid POP3 document key: {key!r}") from exc
        if number < 1:
            raise DocumentNotFoundError(f"Invalid POP3 message number: {number}")
        return number

    def _parse_message(self, raw_message: bytes) -> Dict[str, Any]:
        msg = email.message_from_bytes(raw_message, policy=default)
        metadata = {k: msg.get(k, "") for k in ("Subject", "From", "To", "Date", "Message-ID")}
        metadata = {k.lower().replace("-", "_"): v for k, v in metadata.items()}
        attachments = []
        for part in msg.walk():
            if part.is_multipart() or not part.get_filename():
                continue
            content_type = part.get_content_type().lower()
            if content_type not in SUPPORTED_ATTACHMENT_TYPES:
                continue
            content = part.get_payload(decode=True) or b""
            attachments.append({"filename": part.get_filename(), "content": content, "content_type": content_type})
        return {"metadata": metadata, "attachments": attachments}

    def _list_headers(self, conn: poplib.POP3, number: int) -> Dict[str, Any]:
        try:
            _, lines, _ = conn.top(number, 0)
        except poplib.error_proto:
            _, lines, _ = conn.retr(number)
        msg = email.message_from_bytes(b"\r\n".join(lines), policy=default)
        return {"subject": msg.get("Subject", ""), "from": msg.get("From", ""), "to": msg.get("To", ""), "date": msg.get("Date", ""), "message_id": msg.get("Message-ID", "")}

    def list_documents(self, config: Dict[str, Any]) -> List[Document]:
        conn = self._connect(config)
        try:
            count, mailbox_size = conn.stat()
            sizes: Dict[int, int] = {}
            try:
                _, lines, _ = conn.list()
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            sizes[int(parts[0])] = int(parts[1])
                        except ValueError:
                            pass
            except poplib.error_proto:
                pass
            return [Document(key=f"msg_{i}", metadata={**self._list_headers(conn, i), "message_number": i, "size": sizes.get(i, 0), "mailbox_size": mailbox_size}) for i in range(1, count + 1)]
        except (AuthenticationError, InvalidConfigurationError, SourceConnectionError):
            raise
        except Exception as exc:
            raise SourceConnectionError(f"POP3 list error: {exc}") from exc
        finally:
            self._close(conn)

    def fetch_document(self, config: Dict[str, Any], key: str) -> Document:
        number = self._message_number(key)
        conn = self._connect(config)
        try:
            _, lines, _ = conn.retr(number)
            raw = b"\r\n".join(lines)
            parsed = self._parse_message(raw)
            if parsed["attachments"]:
                a = parsed["attachments"][0]
                return Document(key=a["filename"], metadata={**parsed["metadata"], "message_number": number, "content_type": a["content_type"], "size": len(a["content"])}, content=a["content"])
            return Document(key=f"message_{number}", metadata={**parsed["metadata"], "message_number": number, "content_type": "message/rfc822", "size": len(raw)}, content=raw)
        except (DocumentNotFoundError, AuthenticationError, InvalidConfigurationError, SourceConnectionError):
            raise
        except Exception as exc:
            raise SourceConnectionError(f"POP3 fetch error for {key!r}: {exc}") from exc
        finally:
            self._close(conn)

    def fetch_documents(self, config: Dict[str, Any], keys: Optional[List[str]] = None) -> List[Document]:
        selected = keys if keys is not None else [d.key for d in self.list_documents(config)]
        result = []
        for key in selected:
            try:
                result.append(self.fetch_document(config, key))
            except DocumentNotFoundError:
                raise
            except Exception:
                logger.exception("Failed to fetch POP3 message %s", key)
        return result

    def move_document(self, config: Dict[str, Any], key: str, destination: str) -> bool:
        return False

    def delete_document(self, config: Dict[str, Any], key: str) -> bool:
        return False
