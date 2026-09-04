import requests
from typing import List, Dict, Any, Optional, Tuple
from ..base import DocumentSource, Document
from ..exceptions import SourceConnectionError, InvalidConfigurationError


class APISource(DocumentSource):
    """Fetcher for REST APIs."""

    def _validate_config(self, config: Dict[str, Any]) -> None:
        if not config.get('url'):
            raise InvalidConfigurationError("Missing 'url' in API config")

    def _build_auth(self, config: Dict[str, Any], headers: Dict[str, Any]) -> Optional[Tuple[str, str]]:
        auth = config.get('auth')
        if auth and 'username' in auth and 'password' in auth:
            return (auth['username'], auth['password'])
        elif auth and 'token' in auth:
            headers['Authorization'] = f"Bearer {auth['token']}"
        return None

    def _request(self, method: str, url: str, timeout: int = 30, **kwargs) -> requests.Response:
        try:
            response = requests.request(method, url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            raise SourceConnectionError(f"API error: {e}")

    def list_documents(self, config: Dict[str, Any]) -> List[Document]:
        self._validate_config(config)
        url = config['url']
        headers = config.get('headers', {}).copy()
        params = config.get('params', {}).copy()
        timeout = config.get('timeout', 30)

        auth_tuple = self._build_auth(config, headers)
        response = self._request(
            'GET', url, headers=headers, params=params, auth=auth_tuple, timeout=timeout)

        data = response.json()
        documents = []
        for item in data:
            documents.append(Document(
                key=str(item.get('id') or item.get('key')),
                metadata=item.get('metadata', {})
            ))
        return documents

    def fetch_document(self, config: Dict[str, Any], key: str) -> Document:
        self._validate_config(config)
        url = config['url'].rstrip('/')
        doc_url = f"{url}/{key}"
        headers = config.get('headers', {}).copy()
        # Parámetros adicionales para descarga
        params = config.get('download_params', {}).copy()
        timeout = config.get('timeout', 30)

        auth_tuple = self._build_auth(config, headers)
        response = self._request(
            'GET', doc_url, headers=headers, params=params, auth=auth_tuple, timeout=timeout)

        content = response.content
        return Document(
            key=key,
            metadata={
                'size': len(content),
                'content_type': response.headers.get('Content-Type'),
            },
            content=content
        )

    def fetch_documents(self, config: Dict[str, Any], keys: Optional[List[str]] = None) -> List[Document]:
        if keys:
            return [self.fetch_document(config, key) for key in keys]
        # 🔥 CORREGIDO: descargar todos los documentos
        docs = self.list_documents(config)
        return [self.fetch_document(config, doc.key) for doc in docs]
