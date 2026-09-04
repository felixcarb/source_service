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
    _alias_map = {}

    @classmethod
    def register(cls, source_class, *aliases):
        """
        Register a source class with one or more aliases.
        Aliases are normalized: lowercase, spaces and hyphens removed.
        Example: register(S3Source, 's3', 'S3', 'Amazon S3')
        """
        for alias in aliases:
            normalized = cls._normalize(alias)
            cls._alias_map[normalized] = source_class

    @classmethod
    def _normalize(cls, name: str) -> str:
        # Convert to lowercase, remove spaces, hyphens, underscores
        return name.lower().replace(' ', '').replace('-', '').replace('_', '')

    @classmethod
    def get_source(cls, source_type: str, **kwargs) -> DocumentSource:
        normalized = cls._normalize(source_type)
        source_class = cls._alias_map.get(normalized)
        if not source_class:
            raise InvalidConfigurationError(
                f"Unsupported source type: {source_type}")
        return source_class(**kwargs)


# Register built-in sources with their aliases after removing spaces, hyphens and underscores
SourceFactory.register(S3Source, 's3')
SourceFactory.register(FTPSource, 'ftp')
SourceFactory.register(SFTPSource, 'sftp')
SourceFactory.register(SMBSource, 'smb')
SourceFactory.register(APISource, 'api', 'thirdpartyapi')
SourceFactory.register(POP3Source, 'pop3')
SourceFactory.register(DropboxSource, 'dropbox')
SourceFactory.register(DriveSource, 'drive',
                       'googledrive')
SourceFactory.register(OneDriveSource, 'onedrive', 'microsoftonedrive')
SourceFactory.register(FTPSSource, 'ftps')
