# source_service/fetchers/onedrive_fetcher.py
import requests
from typing import List, Dict, Any, Optional
from ..base import DocumentSource, Document
from ..exceptions import (
    SourceConnectionError,
    AuthenticationError,
    InvalidConfigurationError,
)


class OneDriveSource(DocumentSource):
    """
    Fetcher for Microsoft OneDrive using the Graph API v1.0.
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
                "Missing refresh_token, client_id, or client_secret for token refresh"
            )

        url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/Files.ReadWrite offline_access",
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
        """Make an authenticated request to Microsoft Graph API, handling token refresh on 401."""
        access_token = config.get('access_token')
        if not access_token:
            raise InvalidConfigurationError(
                "Missing 'access_token' in OneDrive config")

        headers = self._get_headers(access_token)
        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))

        if 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json'

        try:
            response = requests.request(method, url, headers=headers, **kwargs)
            if response.status_code == 401:
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
            raise SourceConnectionError(f"OneDrive API error: {e}")

    def _get_drive_id(self, config: Dict[str, Any]) -> str:
        """Get the drive ID from config or fetch the default drive."""
        drive_id = config.get('drive_id')
        if drive_id:
            return drive_id
        # Get default drive (user's OneDrive)
        url = "https://graph.microsoft.com/v1.0/me/drive"
        response = self._request('GET', url, config)
        return response.json().get('id')

    def _build_item_url(self, config: Dict[str, Any], path: str = "", item_id: Optional[str] = None) -> str:
        """Build URL for a specific item or folder."""
        base = "https://graph.microsoft.com/v1.0"
        drive_id = self._get_drive_id(config)
        if item_id:
            return f"{base}/drives/{drive_id}/items/{item_id}"
        # If path is provided, use the path-based navigation
        path = path.lstrip('/')
        if path:
            # URL encode the path
            import urllib.parse
            encoded_path = urllib.parse.quote(path)
            return f"{base}/drives/{drive_id}/root:/{encoded_path}"
        else:
            return f"{base}/drives/{drive_id}/root"

    def list_documents(self, config: Dict[str, Any]) -> List[Document]:
        path = config.get('path', '')
        root_url = self._build_item_url(config, path)
        url = f"{root_url}/children"
        params = {
            "$select": "id,name,size,lastModifiedDateTime,file,folder,deleted",
            "$orderby": "name",
        }

        documents = []
        while url:
            response = self._request('GET', url, config, params=params)
            data = response.json()
            for item in data.get('value', []):
                # Skip folders and deleted items
                if item.get('folder') or item.get('deleted'):
                    continue
                documents.append(Document(
                    key=item['id'],
                    metadata={
                        'name': item.get('name', ''),
                        'size': item.get('size', 0),
                        'last_modified': item.get('lastModifiedDateTime'),
                        'id': item['id'],
                    }
                ))
            url = data.get('@odata.nextLink')
            params = None  # nextLink already includes params

        return documents

    def fetch_document(self, config: Dict[str, Any], key: str) -> Document:
        # key is the item ID
        content_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{key}/content"
        response = self._request('GET', content_url, config)
        content = response.content

        # Get metadata
        metadata_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{key}"
        meta_resp = self._request('GET', metadata_url, config)
        meta = meta_resp.json()

        return Document(
            key=key,
            metadata={
                'name': meta.get('name', ''),
                'size': meta.get('size', len(content)),
                'last_modified': meta.get('lastModifiedDateTime'),
                'id': key,
            },
            content=content
        )

    def fetch_documents(self, config: Dict[str, Any], keys: Optional[List[str]] = None) -> List[Document]:
        if keys:
            return [self.fetch_document(config, key) for key in keys]
        docs = self.list_documents(config)
        return [self.fetch_document(config, doc.key) for doc in docs]

    def delete_document(self, config: Dict[str, Any], key: str) -> bool:
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{key}"
        try:
            self._request('DELETE', url, config)
            return True
        except SourceConnectionError:
            return False

    def move_document(self, config: Dict[str, Any], key: str, destination: str) -> bool:
        """
        Move a file to a different folder.
        destination can be a folder ID or a path (e.g., '/folder/subfolder').
        """
        # Determine destination ID or path
        if destination.startswith('/'):
            # It's a path, get the folder ID first
            dest_url = self._build_item_url(config, destination)
            try:
                resp = self._request('GET', dest_url, config)
                dest_item = resp.json()
                dest_id = dest_item.get('id')
                if not dest_id:
                    return False
            except Exception:
                return False
        else:
            dest_id = destination

        move_url = f"https://graph.microsoft.com/v1.0/me/drive/items/{key}"
        payload = {
            "parentReference": {"id": dest_id}
        }
        try:
            self._request('PATCH', move_url, config, json=payload)
            return True
        except SourceConnectionError:
            return False
