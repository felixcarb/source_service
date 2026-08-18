import os
import smbclient
from typing import List, Dict, Any, Optional

from ..base import DocumentSource, Document
from ..exceptions import SourceConnectionError, InvalidConfigurationError, DocumentNotFoundError


class SMBSource(DocumentSource):
    """Fetcher for SMB/CIFS shares using smbclient (high-level API)."""

    def _get_unc_path(self, config: Dict[str, Any], rel_path: str = '') -> str:
        """Build UNC path like \\\\host\\share\\rel_path."""
        host = config.get('host')
        share = config.get('share')
        # Normalize paths: remove leading/trailing slashes
        share = share.strip('/')
        rel_path = rel_path.strip('/')
        if rel_path:
            return f"\\\\{host}\\{share}\\{rel_path}"
        else:
            return f"\\\\{host}\\{share}"

    def _ensure_session(self, config: Dict[str, Any]) -> None:
        """Register SMB session if not already registered."""
        host = config.get('host')
        username = config.get('username')
        password = config.get('password')
        # smbclient handles session caching, we just register once per host
        try:
            smbclient.register_session(
                host, username=username, password=password)
        except Exception as e:
            raise SourceConnectionError(f"Failed to register SMB session: {e}")

    def list_documents(self, config: Dict[str, Any]) -> List[Document]:
        host = config.get('host')
        username = config.get('username')
        password = config.get('password')

        if not host or not username:
            raise InvalidConfigurationError(
                "Missing 'host' or 'username' in SMB config")
        if not config.get('share'):
            raise InvalidConfigurationError("Missing 'share' in SMB config")

        self._ensure_session(config)

        path = config.get('path', '').strip()
        # If path is '/', treat as empty
        if path == '/':
            path = ''
        unc_path = self._get_unc_path(config, path)

        try:
            entries = smbclient.listdir(unc_path)
            documents = []
            for entry in entries:
                if entry not in ('.', '..') and not entry.startswith('.'):
                    # Build full key with path prefix
                    key = f"{path}/{entry}".replace('//', '/')
                    if key.startswith('/'):
                        key = key[1:]
                    try:
                        stat_info = smbclient.stat(f"{unc_path}/{entry}")
                        documents.append(Document(
                            key=key,
                            metadata={
                                'size': stat_info.st_size,
                                'is_directory': bool(stat_info.st_mode & 0x4000),
                                'filename': entry,
                            }
                        ))
                    except Exception:
                        # If stat fails, still include the file without size
                        documents.append(Document(
                            key=key,
                            metadata={'filename': entry}
                        ))
            return documents
        except Exception as e:
            raise SourceConnectionError(f"SMB list error: {e}")

    def fetch_document(self, config: Dict[str, Any], key: str) -> Document:
        host = config.get('host')
        username = config.get('username')
        password = config.get('password')

        if not host or not username:
            raise InvalidConfigurationError(
                "Missing 'host' or 'username' in SMB config")
        if not config.get('share'):
            raise InvalidConfigurationError("Missing 'share' in SMB config")

        self._ensure_session(config)

        # key already contains the full path (including any path prefix)
        unc_path = self._get_unc_path(config, key)

        try:
            with smbclient.open_file(unc_path, mode='rb') as fd:
                content = fd.read()
            return Document(
                key=key,
                metadata={'size': len(content)},
                content=content
            )
        except FileNotFoundError:
            raise DocumentNotFoundError(f"File '{key}' not found on SMB share")
        except Exception as e:
            raise SourceConnectionError(f"SMB fetch error: {e}")

    def fetch_documents(self, config: Dict[str, Any], keys: Optional[List[str]] = None) -> List[Document]:
        if keys is not None:
            return [self.fetch_document(config, key) for key in keys]
        docs = self.list_documents(config)
        return [self.fetch_document(config, doc.key) for doc in docs]

    def delete_document(self, config: Dict[str, Any], key: str) -> bool:
        """Elimina un archivo del recurso SMB."""
        self._ensure_session(config)
        unc_path = self._get_unc_path(config, key)
        try:
            smbclient.remove(unc_path)
            return True
        except Exception as e:
            print(f"SMB delete error: {e}")
            return False

    def move_document(self, config: Dict[str, Any], key: str, destination: str) -> bool:
        """Mueve/renombra un archivo en SMB."""
        self._ensure_session(config)
        old_unc = self._get_unc_path(config, key)
        if destination.endswith('/'):
            filename = os.path.basename(key)
            # destination es relativo al share, construimos UNC
            new_unc = self._get_unc_path(config, destination + filename)
        else:
            new_unc = self._get_unc_path(config, destination)
        try:
            smbclient.rename(old_unc, new_unc)
            return True
        except Exception as e:
            print(f"SMB move error: {e}")
            return False
