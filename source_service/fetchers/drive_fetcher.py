# source_service/fetchers/drive_fetcher.py
import requests
from typing import List, Dict, Any, Optional
from ..base import DocumentSource, Document
from ..exceptions import (
    SourceConnectionError,
    AuthenticationError,
    InvalidConfigurationError,
)


class DriveSource(DocumentSource):
    """
    Fetcher for Google Drive files using the API v3.
    """

    def _get_headers(self, access_token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def _refresh_access_token(self, config: Dict[str, Any]) -> str:
        """Refresh the access token using refresh_token."""
        refresh_token = config.get('refresh_token')
        client_id = config.get('client_id')
        client_secret = config.get('client_secret')

        if not refresh_token or not client_id or not client_secret:
            raise AuthenticationError(
                "Missing refresh_token, client_id, or client_secret for token refresh")

        url = "https://oauth2.googleapis.com/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
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

    def _request(self, method: str, url: str, config: Dict[str, Any], **kwargs) -> requests.Response:
        """Make an authenticated request to Google Drive API, handling token refresh on 401."""
        access_token = config.get('access_token')
        if not access_token:
            raise InvalidConfigurationError(
                "Missing 'access_token' in Drive config")

        headers = self._get_headers(access_token)
        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))

        if 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json'

        try:
            response = requests.request(method, url, headers=headers, **kwargs)
            if response.status_code == 401:
                # Token expired, try to refresh
                try:
                    new_token = self._refresh_access_token(config)
                    config['access_token'] = new_token
                    headers['Authorization'] = f"Bearer {new_token}"
                    response = requests.request(
                        method, url, headers=headers, **kwargs)
                except Exception as e:
                    raise AuthenticationError(f"Failed to refresh token: {e}")
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            raise SourceConnectionError(f"Google Drive API error: {e}")

    def list_documents(self, config: Dict[str, Any]) -> List[Document]:
        """
        List files in Google Drive.
        Filters: not trashed, not folders, and optionally by mime_type or query.
        """
        mime_type = config.get('mime_type')
        query = config.get('query', "")
        page_size = config.get('page_size', 100)
        fields = config.get(
            'fields', "files(id, name, mimeType, size, modifiedTime, webViewLink, parents), nextPageToken")

        # Build query
        q_parts = ["trashed = false",
                   "mimeType != 'application/vnd.google-apps.folder'"]
        if mime_type:
            q_parts.append(f"mimeType = '{mime_type}'")
        if query:
            q_parts.append(f"({query})")
        q = " and ".join(q_parts)

        url = "https://www.googleapis.com/drive/v3/files"
        params = {
            "q": q,
            "pageSize": page_size,
            "fields": fields,
            "orderBy": "modifiedTime desc",
        }

        documents = []
        page_token = None

        while True:
            if page_token:
                params["pageToken"] = page_token

            response = self._request('GET', url, config, params=params)
            data = response.json()

            for file_info in data.get('files', []):
                # Skip Google Workspace files that can't be exported
                mime = file_info.get('mimeType', '')
                if mime.startswith('application/vnd.google-apps.'):
                    # Check if export is supported
                    export_mime = config.get('export_mime', 'application/pdf')
                    # We'll handle export in fetch_document
                    pass

                documents.append(Document(
                    key=file_info['id'],
                    metadata={
                        'name': file_info.get('name', ''),
                        'mime_type': mime,
                        'size': int(file_info.get('size', 0)),
                        'last_modified': file_info.get('modifiedTime'),
                        'web_view_link': file_info.get('webViewLink'),
                        'parents': file_info.get('parents', []),
                    }
                ))

            page_token = data.get('nextPageToken')
            if not page_token:
                break

        return documents

    def fetch_document(self, config: Dict[str, Any], key: str) -> Document:
        """
        Fetch a single file by its ID.
        Handles Google Workspace files by exporting them.
        """
        # First, get file metadata to check mime type
        url = f"https://www.googleapis.com/drive/v3/files/{key}"
        params = {"fields": "id, name, mimeType, size, modifiedTime"}
        response = self._request('GET', url, config, params=params)
        meta = response.json()

        mime_type = meta.get('mimeType', '')
        file_name = meta.get('name', key)

        # Determine export/access URL
        if mime_type.startswith('application/vnd.google-apps.'):
            # Google Workspace file: need to export
            export_mime = config.get('export_mime', 'application/pdf')
            download_url = f"https://www.googleapis.com/drive/v3/files/{key}/export"
            params = {"mimeType": export_mime}
            headers = {"Accept": export_mime}
            response = self._request(
                'GET', download_url, config, params=params, headers=headers)
            content = response.content
            # Update mime type to exported one
            mime_type = export_mime
        else:
            # Regular file: download binary
            download_url = f"https://www.googleapis.com/drive/v3/files/{key}?alt=media"
            response = self._request('GET', download_url, config)
            content = response.content

        return Document(
            key=key,
            metadata={
                'name': file_name,
                'mime_type': mime_type,
                'size': len(content) if 'size' not in meta else int(meta.get('size', len(content))),
                'last_modified': meta.get('modifiedTime'),
            },
            content=content
        )

    def fetch_documents(self, config: Dict[str, Any], keys: Optional[List[str]] = None) -> List[Document]:
        if keys:
            return [self.fetch_document(config, key) for key in keys]
        docs = self.list_documents(config)
        return [self.fetch_document(config, doc.key) for doc in docs]

    def delete_document(self, config: Dict[str, Any], key: str) -> bool:
        """Move a file to trash (Google Drive doesn't have permanent delete via API easily)."""
        url = f"https://www.googleapis.com/drive/v3/files/{key}"
        # To trash: update with trashed=true
        payload = {"trashed": True}
        try:
            self._request('PATCH', url, config, json=payload)
            return True
        except SourceConnectionError:
            return False

    def move_document(self, config: Dict[str, Any], key: str, destination: str) -> bool:
        """
        Move a file to a different folder or rename it.
        destination can be:
        - A folder ID (to move)
        - A new name (to rename)
        - Both: "folder_id:new_name"
        """
        # For simplicity, we implement only moving to a folder
        # If we want to rename, we'd need separate logic
        if not destination:
            return False

        # If destination contains ':', assume format "folder_id:new_name"
        if ':' in destination:
            folder_id, new_name = destination.split(':', 1)
            # Update name and parents
            payload = {"name": new_name}
            # To change parent, need to use addParents and removeParents
            # This is more complex, so we'll handle separately.
            # For now, we only support moving to a folder without renaming.
            # Let's just move to a new folder:
            return self._move_to_folder(config, key, folder_id)
        else:
            # Assume it's a folder ID
            return self._move_to_folder(config, key, destination)

    def _move_to_folder(self, config: Dict[str, Any], file_id: str, folder_id: str) -> bool:
        """Move a file to a different folder."""
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
        # First, get current parents
        response = self._request('GET', url, config, params={
                                 "fields": "parents"})
        parents = response.json().get('parents', [])
        remove_parents = ','.join(parents) if parents else None
        add_parents = folder_id

        params = {}
        if remove_parents:
            params["removeParents"] = remove_parents
        params["addParents"] = add_parents

        # Empty body, just update parents
        try:
            self._request('PATCH', url, config, params=params, json={})
            return True
        except SourceConnectionError:
            return False
