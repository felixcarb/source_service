from ftplib import FTP, error_perm
from typing import List, Dict, Any, Optional
from io import BytesIO
from ..base import DocumentSource, Document
from ..exceptions import (
    SourceConnectionError,
    AuthenticationError,
    DocumentNotFoundError,
    InvalidConfigurationError,
)


class FTPSource(DocumentSource):
    """Fetcher for FTP servers."""

    def _connect(self, config: Dict[str, Any]) -> FTP:
        """Establish FTP connection and login."""
        host = config.get('host')
        port = config.get('port', 21)
        username = config.get('username', 'anonymous')
        password = config.get('password', '')
        timeout = config.get('timeout', 30)

        if not host:
            raise InvalidConfigurationError("Missing 'host' in FTP config")

        try:
            ftp = FTP()
            ftp.connect(host, port, timeout=timeout)  # ✅ timeout incluido
            ftp.login(username, password)
            return ftp
        except error_perm as e:
            raise AuthenticationError(f"FTP authentication failed: {e}")
        except Exception as e:
            raise SourceConnectionError(f"FTP connection error: {e}")

    def _parse_list_line(self, line: str, base_path: str) -> Optional[Document]:
        parts = line.split()
        if len(parts) < 9:
            return None
        # Si la línea comienza con 'd', es un directorio, lo ignoramos
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
            raise SourceConnectionError(f"FTP list error: {e}")
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
                    f"File '{key}' not found on FTP server")
            raise SourceConnectionError(f"FTP fetch error: {e}")
        except Exception as e:
            raise SourceConnectionError(f"FTP fetch error: {e}")
        finally:
            ftp.quit()

    def fetch_documents(self, config: Dict[str, Any], keys: Optional[List[str]] = None) -> List[Document]:
        if keys is not None:
            return [self.fetch_document(config, key) for key in keys]
        docs = self.list_documents(config)
        return [self.fetch_document(config, doc.key) for doc in docs]
