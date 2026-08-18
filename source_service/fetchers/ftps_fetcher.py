from ftplib import FTP_TLS, error_perm
import os
import ssl
from typing import List, Dict, Any, Optional
from io import BytesIO
from ..base import DocumentSource, Document
from ..exceptions import (
    SourceConnectionError,
    AuthenticationError,
    DocumentNotFoundError,
    InvalidConfigurationError,
)


class FTPSSource(DocumentSource):
    """Fetcher for FTPS (FTP over SSL/TLS) servers."""

    def _connect(self, config: Dict[str, Any]) -> FTP_TLS:
        host = config.get('host')
        port = config.get('port', 990 if config.get('implicit', False) else 21)
        username = config.get('username', 'anonymous')
        password = config.get('password', '')
        timeout = config.get('timeout', 30)
        passive = config.get('passive', True)
        implicit = config.get('implicit', False)
        validate_cert = config.get('validate_cert', True)

        if not host:
            raise InvalidConfigurationError("Missing 'host' in FTPS config")

        try:
            ftp = FTP_TLS()
            ftp.connect(host, port, timeout=timeout)

            if implicit:
                # For implicit FTPS, the socket is already SSL-wrapped.
                # Use modern SSL context API
                context = ssl.create_default_context()
                if not validate_cert:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                ftp.sock = context.wrap_socket(ftp.sock, server_hostname=host)
            else:
                # Explicit: start TLS negotiation
                ftp.auth()

            ftp.login(username, password)

            if passive:
                ftp.set_pasv(True)

            if not implicit and not validate_cert:
                # Disable certificate verification (use with caution)
                ftp.ssl_version = ssl.PROTOCOL_TLS
                ftp.context = ssl.create_unverified_context()

            if not implicit:
                # Secure data connection
                ftp.prot_p()

            return ftp
        except error_perm as e:
            raise AuthenticationError(f"FTPS authentication failed: {e}")
        except Exception as e:
            raise SourceConnectionError(f"FTPS connection error: {e}")

    def _parse_list_line(self, line: str, base_path: str) -> Optional[Document]:
        """Parse a line from FTP LIST command (Unix format)."""
        parts = line.split()
        if len(parts) < 9:
            return None
        if line.startswith('d'):
            return None
        filename = ' '.join(parts[8:])
        if filename.startswith('.'):
            return None
        try:
            size = int(parts[4])
        except ValueError:
            size = 0
        return Document(
            key=f"{base_path}/{filename}".replace('//', '/'),
            metadata={
                'size': size,
                'permissions': parts[0],
                'owner': parts[2],
                'group': parts[3],
                'last_modified': f"{parts[5]} {parts[6]} {parts[7]}",
            }
        )

    def list_documents(self, config: Dict[str, Any]) -> List[Document]:
        ftp = self._connect(config)
        path = config.get('path', '/')
        try:
            ftp.cwd(path)
            lines = []
            ftp.retrlines('LIST', lines.append)
        except Exception as e:
            raise SourceConnectionError(f"FTPS list error: {e}")
        finally:
            ftp.quit()

        documents = []
        for line in lines:
            doc = self._parse_list_line(line, path)
            if doc:
                documents.append(doc)
        return documents

    def fetch_document(self, config: Dict[str, Any], key: str) -> Document:
        ftp = self._connect(config)
        try:
            if '/' in key:
                dir_path, filename = key.rsplit('/', 1)
                ftp.cwd(dir_path)
            else:
                filename = key

            buffer = BytesIO()
            ftp.retrbinary(f'RETR {filename}', buffer.write)
            content = buffer.getvalue()

            try:
                size = int(ftp.size(filename))
            except Exception:
                size = len(content)

            return Document(
                key=key,
                metadata={'size': size},
                content=content
            )
        except error_perm as e:
            if '550' in str(e) or 'No such file' in str(e):
                raise DocumentNotFoundError(
                    f"File '{key}' not found on FTPS server")
            raise SourceConnectionError(f"FTPS fetch error: {e}")
        except Exception as e:
            raise SourceConnectionError(f"FTPS fetch error: {e}")
        finally:
            ftp.quit()

    def fetch_documents(self, config: Dict[str, Any], keys: Optional[List[str]] = None) -> List[Document]:
        if keys is not None:
            return [self.fetch_document(config, key) for key in keys]
        docs = self.list_documents(config)
        return [self.fetch_document(config, doc.key) for doc in docs]

    def move_document(self, config: Dict[str, Any], key: str, destination: str) -> bool:
        ftp = self._connect(config)
        try:
            if destination.endswith('/'):
                filename = os.path.basename(key)
                new_path = destination + filename
            else:
                new_path = destination
            ftp.rename(key, new_path)
            return True
        except Exception as e:
            print(f"FTPS move error: {e}")
            return False
        finally:
            ftp.quit()

    def delete_document(self, config: Dict[str, Any], key: str) -> bool:
        ftp = self._connect(config)
        try:
            ftp.delete(key)
            return True
        except Exception as e:
            print(f"FTPS delete error: {e}")
            return False
        finally:
            ftp.quit()
