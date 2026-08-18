import unittest
from unittest.mock import Mock, patch
from source_service.fetchers.drive_fetcher import DriveSource
from source_service.exceptions import SourceConnectionError


class TestDriveSourceOperations(unittest.TestCase):
    """Pruebas unitarias para move_document y delete_document de DriveSource."""

    def setUp(self):
        self.fetcher = DriveSource()
        self.config = {
            'access_token': 'test_token',
            'refresh_token': 'test_refresh',
            'client_id': 'test_client',
            'client_secret': 'test_secret',
        }
        self.file_id = '1abc123def456'
        self.folder_id = '1destinationFolder'

    @patch.object(DriveSource, '_request')
    def test_delete_document(self, mock_request):
        """Eliminación (mover a papelera) exitosa."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = self.fetcher.delete_document(self.config, self.file_id)

        expected_payload = {"trashed": True}
        mock_request.assert_called_once_with(
            'PATCH',
            f'https://www.googleapis.com/drive/v3/files/{self.file_id}',
            self.config,
            json=expected_payload
        )
        self.assertTrue(result)

    @patch.object(DriveSource, '_request')
    def test_delete_document_error(self, mock_request):
        """Si _request lanza SourceConnectionError, debe retornar False."""
        mock_request.side_effect = SourceConnectionError("Drive API error")

        result = self.fetcher.delete_document(self.config, self.file_id)

        self.assertFalse(result)

    @patch.object(DriveSource, '_request')
    def test_move_document_to_folder(self, mock_request):
        """Mover a una carpeta (solo folder_id)."""
        # Primera llamada: obtener parents actuales
        mock_response_parents = Mock()
        mock_response_parents.raise_for_status.return_value = None
        mock_response_parents.json.return_value = {
            'parents': ['old_parent1', 'old_parent2']
        }

        # Segunda llamada: PATCH para mover
        mock_response_move = Mock()
        mock_response_move.raise_for_status.return_value = None

        # Configurar side_effect para que devuelva primero una respuesta y luego otra
        mock_request.side_effect = [mock_response_parents, mock_response_move]

        result = self.fetcher.move_document(
            self.config, self.file_id, self.folder_id
        )

        # Verificar la primera llamada (GET para obtener parents)
        mock_request.assert_any_call(
            'GET',
            f'https://www.googleapis.com/drive/v3/files/{self.file_id}',
            self.config,
            params={"fields": "parents"}
        )

        # Verificar la segunda llamada (PATCH para mover)
        expected_params = {
            "removeParents": "old_parent1,old_parent2",
            "addParents": self.folder_id
        }
        mock_request.assert_called_with(
            'PATCH',
            f'https://www.googleapis.com/drive/v3/files/{self.file_id}',
            self.config,
            params=expected_params,
            json={}
        )

        self.assertTrue(result)

    @patch.object(DriveSource, '_request')
    def test_move_document_with_rename(self, mock_request):
        """Mover a una carpeta y renombrar (formato 'folder_id:new_name')."""
        # Primera llamada: obtener parents
        mock_response_parents = Mock()
        mock_response_parents.raise_for_status.return_value = None
        mock_response_parents.json.return_value = {'parents': ['old_parent']}

        # Segunda llamada: PATCH para mover (sin renombrar, porque la implementación actual solo mueve)
        # Nota: el código actual de move_document, cuando encuentra ':', solo llama a _move_to_folder,
        # ignorando el nuevo nombre. El test refleja ese comportamiento.
        mock_response_move = Mock()
        mock_response_move.raise_for_status.return_value = None

        mock_request.side_effect = [mock_response_parents, mock_response_move]

        destination = f"{self.folder_id}:new_name.pdf"
        result = self.fetcher.move_document(
            self.config, self.file_id, destination
        )

        # Verificar que se llamó a _move_to_folder con solo el folder_id
        # (es decir, no se pasó el nombre)
        mock_request.assert_any_call(
            'GET',
            f'https://www.googleapis.com/drive/v3/files/{self.file_id}',
            self.config,
            params={"fields": "parents"}
        )
        expected_params = {
            "removeParents": "old_parent",
            "addParents": self.folder_id
        }
        mock_request.assert_called_with(
            'PATCH',
            f'https://www.googleapis.com/drive/v3/files/{self.file_id}',
            self.config,
            params=expected_params,
            json={}
        )

        self.assertTrue(result)

    @patch.object(DriveSource, '_request')
    def test_move_document_no_parents(self, mock_request):
        """Mover cuando el archivo no tiene parents (raíz)."""
        mock_response_parents = Mock()
        mock_response_parents.raise_for_status.return_value = None
        mock_response_parents.json.return_value = {'parents': []}

        mock_response_move = Mock()
        mock_response_move.raise_for_status.return_value = None

        mock_request.side_effect = [mock_response_parents, mock_response_move]

        result = self.fetcher.move_document(
            self.config, self.file_id, self.folder_id
        )

        # removeParents debe ser None (o no incluirse)
        mock_request.assert_any_call(
            'GET',
            f'https://www.googleapis.com/drive/v3/files/{self.file_id}',
            self.config,
            params={"fields": "parents"}
        )

        # La segunda llamada solo debe tener addParents
        mock_request.assert_called_with(
            'PATCH',
            f'https://www.googleapis.com/drive/v3/files/{self.file_id}',
            self.config,
            params={"addParents": self.folder_id},  # removeParents no está
            json={}
        )

        self.assertTrue(result)

    @patch.object(DriveSource, '_request')
    def test_move_document_error(self, mock_request):
        """Si la primera llamada (GET parents) falla, debe retornar False."""
        mock_request.side_effect = SourceConnectionError("Drive API error")

        result = self.fetcher.move_document(
            self.config, self.file_id, self.folder_id
        )

        self.assertFalse(result)

    @patch.object(DriveSource, '_request')
    def test_move_document_empty_destination(self, mock_request):
        """Si destination está vacío, debe retornar False sin hacer llamadas."""
        result = self.fetcher.move_document(self.config, self.file_id, '')

        mock_request.assert_not_called()
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
