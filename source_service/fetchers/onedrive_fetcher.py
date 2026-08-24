# source_service/fetchers/onedrive_fetcher.py
import logging
import requests
from typing import List, Dict, Any, Optional, Callable
from ..base import DocumentSource, Document
from ..exceptions import (
    SourceConnectionError,
    AuthenticationError,
    InvalidConfigurationError,
)

logger = logging.getLogger(__name__)


class OneDriveSource(DocumentSource):
    """
    Fetcher for Microsoft OneDrive using the Graph API v1.0.
    """

    def __init__(self, on_token_refresh: Optional[Callable[[Dict[str, Any]], None]] = None):
        """
        :param on_token_refresh: Optional callback that receives the updated config dict
                                 after a token refresh. Useful for persisting the new token.
        """
        self.on_token_refresh = on_token_refresh

    def _get_headers(self, access_token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def _refresh_access_token(self, config: Dict[str, Any]) -> str:
        refresh_token = config.get("refresh_token")
        client_id = config.get("client_id")
        client_secret = config.get("client_secret")
        tenant = config.get("tenant_id", "consumers")

        if not refresh_token or not client_id:
            raise AuthenticationError(
                "Missing refresh_token or client_id for token refresh"
            )

        url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

        data = {
            "client_id": client_id,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        if client_secret:
            data["client_secret"] = client_secret

        logger.debug(
            "Refreshing OneDrive token: tenant=%s client_id=%s",
            tenant,
            client_id,
        )

        try:
            response = requests.post(url, data=data, timeout=30)
            response.raise_for_status()
            token_data = response.json()
        except requests.RequestException as exc:
            body = (
                exc.response.text
                if getattr(exc, "response", None) is not None
                else None
            )
            logger.error(
                "OneDrive refresh failed: status=%s body=%s",
                getattr(exc.response, "status_code", None),
                body,
            )
            raise AuthenticationError(
                "Failed to refresh OneDrive token"
            ) from exc

        access_token = token_data.get("access_token")
        if not access_token:
            raise AuthenticationError(
                "OneDrive did not return an access_token"
            )

        config["access_token"] = access_token

        # Obligatorio persistirlo cuando Microsoft entregue uno nuevo.
        if new_refresh_token := token_data.get("refresh_token"):
            config["refresh_token"] = new_refresh_token

        if self.on_token_refresh:
            try:
                self.on_token_refresh(config)
            except Exception as exc:
                logger.exception(
                    "The OneDrive token was refreshed but could not be persisted"
                )
                raise AuthenticationError(
                    "Refreshed OneDrive token could not be persisted"
                ) from exc

        logger.info("OneDrive token refreshed successfully")
        return access_token

    def _request(self, method: str, url: str, config: Dict[str, Any], **kwargs) -> requests.Response:
        """Make an authenticated request, refreshing token on 401/403/400."""
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

            # If the response indicates an authentication issue, try to refresh
            if response.status_code in (401, 403, 400):
                logger.info(
                    f"OneDrive responded with {response.status_code}, attempting token refresh...")
                try:
                    new_token = self._refresh_access_token(config)
                    headers['Authorization'] = f"Bearer {new_token}"
                    response = requests.request(
                        method, url, headers=headers, **kwargs)
                    response.raise_for_status()
                    return response
                except Exception as e:
                    logger.error(f"OneDrive token refresh failed: {e}")
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

    def _get_item_url(self, config: Dict[str, Any], item_id: str) -> str:
        drive_id = self._get_drive_id(config)
        return f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}"

    def list_documents(self, config: Dict[str, Any]) -> List[Document]:
        folder_id = config.get('folder_id')
        if folder_id:
            logger.debug(f"Listing OneDrive folder by folder_id: {folder_id}")
            drive_id = self._get_drive_id(config)
            root_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{folder_id}"
        else:
            logger.debug("Listing OneDrive root folder")
            root_url = self._build_item_url(config, config.get('path', ''))

        url = f"{root_url}/children"
        params = {
            "$select": "id,name,size,lastModifiedDateTime,file,folder,deleted,remoteItem",
            "$orderby": "name",
        }

        documents = []
        while url:
            response = self._request('GET', url, config, params=params)
            data = response.json()
            for item in data.get('value', []):
                # Saltar carpetas, elementos remotos y cualquier cosa que no sea un archivo
                if (item.get('folder') or item.get('remoteItem') or 'file' not in item):
                    continue

                # Solo archivos descargables
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
            params = None

        return documents

    def fetch_document(self, config: Dict[str, Any], key: str) -> Document:
        # key is the item ID
        item_url = self._get_item_url(config, key)
        content_url = f"{item_url}/content"
        response = self._request('GET', content_url, config)
        content = response.content

        # Get metadata
        meta_resp = self._request('GET', item_url, config)
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
        try:
            url = self._get_item_url(config, key)
            self._request('DELETE', url, config)
            return True
        except SourceConnectionError:
            return False

    def move_document(self, config: Dict[str, Any], key: str, destination: str) -> bool:
        try:
            # Determine destination ID
            if destination.startswith('/'):
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

            move_url = self._get_item_url(config, key)
            payload = {"parentReference": {"id": dest_id}}
            self._request('PATCH', move_url, config, json=payload)
            return True
        except SourceConnectionError:
            return False
