import unittest
from unittest.mock import Mock, patch
import os
from source_service.fetchers.dropbox_fetcher import DropboxSource
from source_service.exceptions import SourceConnectionError


class TestDropboxSourceOperations(unittest.TestCase):
    """Pruebas unitarias para move_document y delete_document de DropboxSource."""

    def setUp(self):
        self.fetcher = DropboxSource()
        self.config = {
            'access_token': 'test_token',
            'refresh_token': 'test_refresh',
            'client_id': 'test_client',
            'client_secret': 'test_secret',
        }
        self.key = 'folder/file.pdf'  # Sin slash inicial, como en list_documents
        self.destination = '/processed/'

    @patch.object(DropboxSource, '_request')
    def test_move_document_to_directory(self, mock_request):
        """Mover a directorio (destino termina en '/') debe añadir nombre de archivo."""
        # Configurar mock de respuesta (no nos importa el contenido)
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = self.fetcher.move_document(
            self.config, self.key, self.destination
        )

        # Verificar que _request fue llamado con los argumentos correctos
        expected_payload = {
            "from_path": f"/{self.key}",
            "to_path": f"/processed/{os.path.basename(self.key)}"
        }
        mock_request.assert_called_once_with(
            'POST',
            'https://api.dropboxapi.com/2/files/move_v2',
            self.config,
            json=expected_payload
        )
        self.assertTrue(result)

    @patch.object(DropboxSource, '_request')
    def test_move_document_with_full_path(self, mock_request):
        """Mover a una ruta completa (cambiar nombre)."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        destination_full = '/processed/new_name.pdf'
        result = self.fetcher.move_document(
            self.config, self.key, destination_full
        )

        expected_payload = {
            "from_path": f"/{self.key}",
            "to_path": destination_full
        }
        mock_request.assert_called_once_with(
            'POST',
            'https://api.dropboxapi.com/2/files/move_v2',
            self.config,
            json=expected_payload
        )
        self.assertTrue(result)

    @patch.object(DropboxSource, '_request')
    def test_move_document_error(self, mock_request):
        """Si _request lanza SourceConnectionError, debe retornar False."""
        mock_request.side_effect = SourceConnectionError("Dropbox API error")

        result = self.fetcher.move_document(
            self.config, self.key, self.destination
        )

        self.assertFalse(result)

    @patch.object(DropboxSource, '_request')
    def test_delete_document(self, mock_request):
        """Eliminación exitosa."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = self.fetcher.delete_document(self.config, self.key)

        expected_payload = {"path": f"/{self.key}"}
        mock_request.assert_called_once_with(
            'POST',
            'https://api.dropboxapi.com/2/files/delete_v2',
            self.config,
            json=expected_payload
        )
        self.assertTrue(result)

    @patch.object(DropboxSource, '_request')
    def test_delete_document_error(self, mock_request):
        """Si _request lanza SourceConnectionError, debe retornar False."""
        mock_request.side_effect = SourceConnectionError("Dropbox API error")

        result = self.fetcher.delete_document(self.config, self.key)

        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
