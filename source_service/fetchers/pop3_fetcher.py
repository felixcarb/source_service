# source_service/fetchers/pop3.py
import poplib
import ssl
import email
from email.policy import default
from typing import List, Dict, Any, Optional

from ..base import DocumentSource, Document
from ..exceptions import SourceConnectionError, AuthenticationError, DocumentNotFoundError, InvalidConfigurationError


class POP3Source(DocumentSource):
    """Fetcher para servidores POP3 (correo electrónico)."""

    def _connect(self, config: Dict[str, Any]) -> poplib.POP3:
        """Establece conexión POP3 (con o sin SSL)."""
        host = config.get('host')
        port = config.get('port', 995 if config.get('use_ssl', True) else 110)
        username = config.get('username')
        password = config.get('password')
        use_ssl = config.get('use_ssl', True)
        timeout = config.get('timeout', 30)

        if not host or not username:
            raise InvalidConfigurationError(
                "Missing 'host' or 'username' in POP3 config")

        try:
            if use_ssl:
                # Conexión SSL
                context = ssl.create_default_context()
                if config.get('validate_cert', True) is False:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                conn = poplib.POP3_SSL(
                    host, port, timeout=timeout, context=context)
            else:
                conn = poplib.POP3(host, port, timeout=timeout)
            conn.user(username)
            conn.pass_(password)
            return conn
        except poplib.error_proto as e:
            raise AuthenticationError(f"POP3 authentication failed: {e}")
        except Exception as e:
            raise SourceConnectionError(f"POP3 connection error: {e}")

    def _parse_message(self, raw_message: bytes) -> Dict[str, Any]:
        """Parsea un mensaje crudo y devuelve metadatos y adjuntos."""
        msg = email.message_from_bytes(raw_message, policy=default)
        metadata = {
            'subject': msg.get('Subject', ''),
            'from': msg.get('From', ''),
            'date': msg.get('Date', ''),
            'message_id': msg.get('Message-ID', ''),
        }
        attachments = []
        for part in msg.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            if part.get_content_type() in ('application/octet-stream', 'application/pdf', 'image/jpeg', 'image/png', 'text/plain'):
                filename = part.get_filename()
                if filename:
                    content = part.get_payload(decode=True)
                    attachments.append({
                        'filename': filename,
                        'content': content,
                        'content_type': part.get_content_type(),
                    })
        return {
            'metadata': metadata,
            'attachments': attachments,
        }

    def list_documents(self, config: Dict[str, Any]) -> List[Document]:
        """Lista los mensajes disponibles (solo metadatos, sin adjuntos)."""
        conn = self._connect(config)
        try:
            # Obtener lista de mensajes (stat devuelve (num_messages, total_size))
            num_messages, _ = conn.stat()
            documents = []
            for i in range(1, num_messages + 1):
                # Obtener solo cabeceras para metadatos (TOP 0)
                resp, lines, _ = conn.top(i, 0)
                raw_headers = b'\n'.join(lines)
                msg = email.message_from_bytes(raw_headers, policy=default)
                documents.append(Document(
                    key=f"msg_{i}",
                    metadata={
                        'subject': msg.get('Subject', ''),
                        'from': msg.get('From', ''),
                        'date': msg.get('Date', ''),
                        'message_id': msg.get('Message-ID', ''),
                        'size': 0,  # no calculamos tamaño real aquí
                    }
                ))
            return documents
        except Exception as e:
            raise SourceConnectionError(f"POP3 list error: {e}")
        finally:
            conn.quit()

    def fetch_document(self, config: Dict[str, Any], key: str) -> Document:
        """Descarga un mensaje y extrae sus adjuntos como documentos individuales.
        Si el mensaje tiene múltiples adjuntos, devolvemos el primero como documento.
        """
        if not key.startswith('msg_'):
            raise DocumentNotFoundError(f"Invalid key format: {key}")
        msg_num = int(key.split('_')[1])

        conn = self._connect(config)
        try:
            resp, lines, _ = conn.retr(msg_num)
            raw_message = b'\n'.join(lines)
            parsed = self._parse_message(raw_message)
            if parsed['attachments']:
                # Tomar el primer adjunto como documento
                attach = parsed['attachments'][0]
                return Document(
                    key=attach['filename'],
                    metadata={
                        'subject': parsed['metadata']['subject'],
                        'from': parsed['metadata']['from'],
                        'date': parsed['metadata']['date'],
                        'content_type': attach['content_type'],
                        'size': len(attach['content']),
                    },
                    content=attach['content']
                )
            else:
                # Si no hay adjuntos, devolver el mensaje como texto
                return Document(
                    key=f"message_{msg_num}",
                    metadata=parsed['metadata'],
                    content=raw_message,
                )
        except Exception as e:
            raise SourceConnectionError(f"POP3 fetch error: {e}")
        finally:
            conn.quit()

    def fetch_documents(self, config: Dict[str, Any], keys: Optional[List[str]] = None) -> List[Document]:
        """Descarga todos los adjuntos de todos los mensajes, o solo los especificados."""
        if keys:
            return [self.fetch_document(config, key) for key in keys]
        else:
            docs = self.list_documents(config)
            all_docs = []
            for doc in docs:
                try:
                    fetched = self.fetch_document(config, doc.key)
                    all_docs.append(fetched)
                except Exception as e:
                    # Loggear error pero continuar con los demás
                    print(f"Error fetching {doc.key}: {e}")
            return all_docs
