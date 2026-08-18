import paramiko
import os
from typing import List, Dict, Any, Optional
from ..base import DocumentSource, Document
from ..exceptions import (
    SourceConnectionError,
    AuthenticationError,
    DocumentNotFoundError,
    InvalidConfigurationError,
)


class SFTPSource(DocumentSource):
    """Fetcher for SFTP (SSH File Transfer Protocol) servers."""

    def _connect(self, config: Dict[str, Any]) -> paramiko.SFTPClient:
        host = config.get('host')
        port = config.get('port', 22)
        username = config.get('username')
        password = config.get('password')
        ssh_key_path = config.get('ssh_key_path')
        timeout = config.get('timeout', 30)

        if not host or not username:
            raise InvalidConfigurationError(
                "Missing 'host' or 'username' in SFTP config")

        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((host, port))
            transport = paramiko.Transport(sock)
            transport.connect(username=username, password=password)

            if ssh_key_path:
                key = paramiko.RSAKey.from_private_key_file(ssh_key_path)
                transport.auth_publickey(username, key)

            sftp = paramiko.SFTPClient.from_transport(transport)
            return sftp
        except socket.timeout:
            raise SourceConnectionError(
                f"SFTP connection timeout after {timeout}s")
        except paramiko.AuthenticationException as e:
            raise AuthenticationError(f"SFTP authentication failed: {e}")
        except Exception as e:
            raise SourceConnectionError(f"SFTP connection error: {e}")

    def list_documents(self, config: Dict[str, Any]) -> List[Document]:
        sftp = self._connect(config)
        path = config.get('path', '/')
        try:
            files = sftp.listdir_attr(path)
            documents = []
            for f in files:
                if not f.filename.startswith('.') and not (f.st_mode & 0o40000):
                    documents.append(Document(
                        key=f"{path}/{f.filename}".replace('//', '/'),
                        metadata={
                            'size': f.st_size,
                            'last_modified': f.st_mtime,
                            'permissions': f.st_mode,
                            'uid': f.st_uid,
                            'gid': f.st_gid,
                        }
                    ))
            return documents
        except FileNotFoundError:
            raise SourceConnectionError(f"SFTP path not found: {path}")
        except Exception as e:
            raise SourceConnectionError(f"SFTP list error: {e}")
        finally:
            sftp.close()

    def fetch_document(self, config: Dict[str, Any], key: str) -> Document:
        sftp = self._connect(config)
        try:
            with sftp.open(key, 'rb') as f:
                content = f.read()
            attrs = sftp.stat(key)
            return Document(
                key=key,
                metadata={
                    'size': attrs.st_size,
                    'last_modified': attrs.st_mtime,
                    'permissions': attrs.st_mode,
                },
                content=content
            )
        except FileNotFoundError:
            raise DocumentNotFoundError(
                f"File '{key}' not found on SFTP server")
        except Exception as e:
            raise SourceConnectionError(f"SFTP fetch error: {e}")
        finally:
            sftp.close()

    def fetch_documents(self, config: Dict[str, Any], keys: Optional[List[str]] = None) -> List[Document]:
        if keys is not None:
            return [self.fetch_document(config, key) for key in keys]
        docs = self.list_documents(config)
        return [self.fetch_document(config, doc.key) for doc in docs]

    def move_document(self, config: Dict[str, Any], key: str, destination: str) -> bool:
        """Move/rename a file en SFTP."""
        sftp = self._connect(config)
        try:
            if destination.endswith('/'):
                # if destiny is a directory: keep name
                filename = os.path.basename(key)
                new_path = os.path.join(destination, filename)
            else:
                new_path = destination
            sftp.rename(key, new_path)
            return True
        except Exception as e:
            print(f"SFTP move error: {e}")
            return False
        finally:
            sftp.close()

    def delete_document(self, config: Dict[str, Any], key: str) -> bool:
        """Removes a file from SFTP."""
        sftp = self._connect(config)
        try:
            sftp.remove(key)
            return True
        except Exception as e:
            print(f"SFTP delete error: {e}")
            return False
        finally:
            sftp.close()
