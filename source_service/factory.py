from .base import DocumentSource
from .fetchers.s3_fetcher import S3Source
from .fetchers.ftp_fetcher import FTPSource
from .fetchers.sftp_fetcher import SFTPSource
from .fetchers.smb_fetcher import SMBSource
from .fetchers.api_fetcher import APISource
from .fetchers.pop3_fetcher import POP3Source
from .fetchers.dropbox_fetcher import DropboxSource
from .fetchers.drive_fetcher import DriveSource
from .fetchers.onedrive_fetcher import OneDriveSource
from .fetchers.ftps_fetcher import FTPSSource
from .exceptions import InvalidConfigurationError


class SourceFactory:
    _registry = {
        's3': S3Source,
        'ftp': FTPSource,
        'sftp': SFTPSource,
        'smb': SMBSource,
        'api': APISource,
        'pop3': POP3Source,
        'dropbox': DropboxSource,
        'drive': DriveSource,
        'onedrive': OneDriveSource,
        'ftps': FTPSSource,
    }

    @classmethod
    def register(cls, source_type: str, source_class):
        cls._registry[source_type.lower()] = source_class

    @classmethod
    def get_source(cls, source_type: str, **kwargs) -> DocumentSource:
        source_class = cls._registry.get(source_type.lower())
        if not source_class:
            raise InvalidConfigurationError(
                f"Unsupported source type: {source_type}")
        return source_class(**kwargs)
