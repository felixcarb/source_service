# source_service/fetchers/dropbox_fetcher.py
import os
import requests
from typing import List, Dict, Any, Optional
from ..base import DocumentSource, Document
from ..exceptions import (
    SourceConnectionError,
    AuthenticationError,
    InvalidConfigurationError,
)


class DropboxSource(DocumentSource):
    """Fetcher for Dropbox files using the API v2."""

    def _get_headers(self, access_token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def _refresh_access_token(self, config: Dict[str, Any]) -> str:
        """Refresh the access token using refresh_token."""
        refresh_token = config.get('refresh_token')
        app_key = config.get('app_key')
        app_secret = config.get('app_secret')

        if not refresh_token or not app_key or not app_secret:
            raise AuthenticationError(
                "Missing refresh_token, app_key, or app_secret for token refresh")

        url = "https://api.dropboxapi.com/oauth2/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": app_key,
            "client_secret": app_secret,
        }

        try:
            response = requests.post(url, data=data, timeout=30)
            response.raise_for_status()
            new_token = response.json().get('access_token')
            if not new_token:
                raise AuthenticationError(
                    "No access_token in refresh response")
            return new_token
        except requests.RequestException as e:
            raise AuthenticationError(f"Failed to refresh token: {e}")

    def _ensure_valid_token(self, config: Dict[str, Any]) -> str:
        """Return a valid access token, refreshing if necessary."""
        access_token = config.get('access_token')
        if not access_token:
            raise InvalidConfigurationError(
                "Missing 'access_token' in Dropbox config")

        # If we have refresh token and a way to check expiration, we could implement logic here.
        # For simplicity, we assume the token is valid and will be refreshed if a 401 occurs.
        # The actual refresh will happen in the request wrapper.
        return access_token

    def _request(self, method: str, url: str, config: Dict[str, Any], **kwargs) -> requests.Response:
        """Make an authenticated request to Dropbox API, handling token refresh on 401."""
        access_token = config.get('access_token')
        if not access_token:
            raise InvalidConfigurationError(
                "Missing 'access_token' in Dropbox config")

        headers = self._get_headers(access_token)
        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))

        # Only add Content-Type if not explicitly set (download endpoint uses different headers)
        if 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json'

        try:
            response = requests.request(method, url, headers=headers, **kwargs)
            if response.status_code == 401:
                # Token expired, try to refresh
                try:
                    new_token = self._refresh_access_token(config)
                    # Update config with new token (in memory)
                    config['access_token'] = new_token
                    headers['Authorization'] = f"Bearer {new_token}"
                    response = requests.request(
                        method, url, headers=headers, **kwargs)
                except Exception as e:
                    raise AuthenticationError(f"Failed to refresh token: {e}")
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            raise SourceConnectionError(f"Dropbox API error: {e}")

    def list_documents(self, config: Dict[str, Any]) -> List[Document]:
        path = config.get('path', '')
        recursive = config.get('recursive', False)

        url = "https://api.dropboxapi.com/2/files/list_folder"
        payload = {
            "path": path,
            "recursive": recursive,
            "include_media_info": False,
            "include_deleted": False,
            "include_has_explicit_shared_members": False,
            "include_mounted_folders": True,
            "include_non_downloadable_files": False,
        }

        documents = []
        has_more = True
        cursor = None

        while has_more:
            if cursor:
                url_continue = "https://api.dropboxapi.com/2/files/list_folder/continue"
                payload_continue = {"cursor": cursor}
                response = self._request(
                    'POST', url_continue, config, json=payload_continue)
            else:
                response = self._request('POST', url, config, json=payload)

            data = response.json()
            entries = data.get('entries', [])
            for entry in entries:
                # Skip folders and hidden files
                if entry.get('.tag') == 'folder':
                    continue
                name = entry.get('name', '')
                if name.startswith('.'):
                    continue

                # Build key as the full path (lowercase and normalized)
                key = entry.get('path_lower', entry.get('path_display', ''))
                if key.startswith('/'):
                    key = key[1:]  # remove leading slash for consistency

                documents.append(Document(
                    key=key,
                    metadata={
                        'size': entry.get('size', 0),
                        'last_modified': entry.get('server_modified'),
                        'content_hash': entry.get('content_hash'),
                        'is_downloadable': entry.get('is_downloadable', True),
                    }
                ))

            has_more = data.get('has_more', False)
            if has_more:
                cursor = data.get('cursor')

        return documents

    def fetch_document(self, config: Dict[str, Any], key: str) -> Document:
        url = "https://content.dropboxapi.com/2/files/download"
        headers = {"Dropbox-API-Arg": f'{{"path": "/{key}"}}'}
        response = self._request('POST', url, config, headers=headers)

        # The content is in the raw response
        content = response.content
        # Headers include the metadata as JSON
        metadata_raw = response.headers.get('dropbox-api-result', '{}')
        import json
        try:
            meta = json.loads(metadata_raw)
        except:
            meta = {}

        return Document(
            key=key,
            metadata={
                'size': meta.get('size', len(content)),
                'last_modified': meta.get('server_modified'),
                'content_hash': meta.get('content_hash'),
            },
            content=content
        )

    def fetch_documents(self, config: Dict[str, Any], keys: Optional[List[str]] = None) -> List[Document]:
        if keys:
            return [self.fetch_document(config, key) for key in keys]
        docs = self.list_documents(config)
        return [self.fetch_document(config, doc.key) for doc in docs]

    def delete_document(self, config: Dict[str, Any], key: str) -> bool:
        """Delete a file from Dropbox."""
        url = "https://api.dropboxapi.com/2/files/delete_v2"
        payload = {"path": f"/{key}"}
        try:
            self._request('POST', url, config, json=payload)
            return True
        except SourceConnectionError:
            return False

    def move_document(self, config: Dict[str, Any], key: str, destination: str) -> bool:
        """Move a file within Dropbox. Destination should be a path (including filename)."""
        if not destination.startswith('/'):
            destination = '/' + destination
        # If destination is a directory, we need to append the file name
        # We'll check if destination ends with '/', if so assume directory and append basename.
        if destination.endswith('/'):
            destination += os.path.basename(key)

        url = "https://api.dropboxapi.com/2/files/move_v2"
        payload = {
            "from_path": f"/{key}",
            "to_path": destination,
        }
        try:
            self._request('POST', url, config, json=payload)
            return True
        except SourceConnectionError:
            return False
