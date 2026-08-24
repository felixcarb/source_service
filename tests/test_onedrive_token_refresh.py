import unittest
from unittest.mock import Mock, patch
import requests
from source_service.fetchers.onedrive_fetcher import OneDriveSource
from source_service.exceptions import AuthenticationError, SourceConnectionError


class TestOneDriveTokenRefresh(unittest.TestCase):
    """Pruebas unitarias para el refresco de token en OneDriveSource."""

    def setUp(self):
        self.config = {
            'access_token': 'old_token',
            'refresh_token': 'refresh_123',
            'client_id': 'client_123',
            'client_secret': 'secret_123',
        }
        self.callback = Mock()
        self.fetcher = OneDriveSource(on_token_refresh=self.callback)

    @patch('source_service.fetchers.onedrive_fetcher.requests.post')
    def test_refresh_access_token_success(self, mock_post):
        """Verifica que _refresh_access_token obtiene un nuevo token y llama al callback."""
        # Simular respuesta exitosa de refresh
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'access_token': 'new_token_123'}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        new_token = self.fetcher._refresh_access_token(self.config)

        self.assertEqual(new_token, 'new_token_123')
        self.assertEqual(self.config['access_token'], 'new_token_123')
        self.callback.assert_called_once_with(self.config)

    @patch('source_service.fetchers.onedrive_fetcher.requests.post')
    def test_refresh_access_token_failure(self, mock_post):
        """Simula que el refresco falla (400) y debe lanzar AuthenticationError."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "Bad Request")
        mock_post.return_value = mock_response

        with self.assertRaises(AuthenticationError) as context:
            self.fetcher._refresh_access_token(self.config)

        self.assertIn("Failed to refresh token", str(context.exception))
        self.callback.assert_not_called()

    @patch('source_service.fetchers.onedrive_fetcher.requests.request')
    def test_request_triggers_refresh_on_401(self, mock_request):
        """Verifica que _request intenta refrescar ante un 401 y reintenta con éxito."""
        response_401 = Mock()
        response_401.status_code = 401
        response_200 = Mock()
        response_200.status_code = 200
        mock_request.side_effect = [response_401, response_200]

        # Simular _refresh_access_token: actualiza config y devuelve nuevo token
        def refresh_side_effect(config):
            config['access_token'] = 'new_token'
            return 'new_token'

        with patch.object(self.fetcher, '_refresh_access_token', side_effect=refresh_side_effect) as mock_refresh:
            result = self.fetcher._request(
                'GET', 'https://graph.microsoft.com/v1.0/me/drive', self.config)

            # 1. Verificar que se llamó a _refresh_access_token una vez
            mock_refresh.assert_called_once_with(self.config)

            # 2. Verificar que se hicieron dos llamadas a requests.request
            self.assertEqual(mock_request.call_count, 2)

            # 3. Verificar que la segunda llamada usa el nuevo token
            second_headers = mock_request.call_args_list[1][1]['headers']
            self.assertEqual(second_headers['Authorization'], 'Bearer new_token')

            # 4. Verificar que config fue actualizado
            self.assertEqual(self.config['access_token'], 'new_token')

            # 5. Verificar que se devuelve la respuesta exitosa
            self.assertEqual(result, response_200)

    @patch('source_service.fetchers.onedrive_fetcher.requests.request')
    def test_request_triggers_refresh_on_403(self, mock_request):
        """Verifica que _request intenta refrescar ante un 403."""
        response_403 = Mock()
        response_403.status_code = 403
        response_200 = Mock()
        response_200.status_code = 200
        mock_request.side_effect = [response_403, response_200]

        with patch.object(self.fetcher, '_refresh_access_token', return_value='new_token') as mock_refresh:
            self.fetcher._request(
                'GET', 'https://graph.microsoft.com/v1.0/me/drive', self.config)
            mock_refresh.assert_called_once()

    @patch('source_service.fetchers.onedrive_fetcher.requests.request')
    def test_request_triggers_refresh_on_400(self, mock_request):
        """Verifica que _request intenta refrescar ante un 400 (por si acaso)."""
        response_400 = Mock()
        response_400.status_code = 400
        response_200 = Mock()
        response_200.status_code = 200
        mock_request.side_effect = [response_400, response_200]

        with patch.object(self.fetcher, '_refresh_access_token', return_value='new_token') as mock_refresh:
            self.fetcher._request(
                'GET', 'https://graph.microsoft.com/v1.0/me/drive', self.config)
            mock_refresh.assert_called_once()

    @patch('source_service.fetchers.onedrive_fetcher.requests.request')
    def test_request_refresh_failure_raises_exception(self, mock_request):
        """Si el refresco falla, _request debe lanzar AuthenticationError."""
        response_401 = Mock()
        response_401.status_code = 401
        mock_request.return_value = response_401

        with patch.object(self.fetcher, '_refresh_access_token', side_effect=AuthenticationError("Refresh failed")):
            with self.assertRaises(AuthenticationError):
                self.fetcher._request(
                    'GET', 'https://graph.microsoft.com/v1.0/me/drive', self.config)

    @patch('source_service.fetchers.onedrive_fetcher.requests.request')
    def test_request_other_error_propagates(self, mock_request):
        """Si la respuesta es un error no relacionado con autenticación (ej. 500), se lanza SourceConnectionError."""
        response_500 = Mock()
        response_500.status_code = 500
        response_500.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "Server Error")
        mock_request.return_value = response_500

        with self.assertRaises(SourceConnectionError):
            self.fetcher._request(
                'GET', 'https://graph.microsoft.com/v1.0/me/drive', self.config)


if __name__ == '__main__':
    unittest.main()
