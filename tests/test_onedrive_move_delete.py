import unittest
from unittest.mock import Mock, patch
from source_service.fetchers.onedrive_fetcher import OneDriveSource
from source_service.exceptions import SourceConnectionError


class TestOneDriveSourceOperations(unittest.TestCase):
    def setUp(self):
        self.fetcher = OneDriveSource()
        self.config = {
            'access_token': 'test_token',
            'refresh_token': 'test_refresh',
            'client_id': 'test_client',
            'client_secret': 'test_secret',
        }
        self.file_id = '123abc'
        self.destination_folder_id = 'folder456'
        self.fake_drive_id = 'driveId'

    # ----------------------------------------------------------------------
    # DELETE tests
    # ----------------------------------------------------------------------
    @patch.object(OneDriveSource, '_get_item_url')
    @patch.object(OneDriveSource, '_request')
    def test_delete_document_success(self, mock_request, mock_get_item_url):
        """Eliminación exitosa."""
        mock_get_item_url.return_value = f'https://graph.microsoft.com/v1.0/drives/{self.fake_drive_id}/items/{self.file_id}'
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = self.fetcher.delete_document(self.config, self.file_id)

        mock_get_item_url.assert_called_once_with(self.config, self.file_id)
        mock_request.assert_called_once_with(
            'DELETE',
            f'https://graph.microsoft.com/v1.0/drives/{self.fake_drive_id}/items/{self.file_id}',
            self.config
        )
        self.assertTrue(result)

    @patch.object(OneDriveSource, '_get_item_url')
    @patch.object(OneDriveSource, '_request')
    def test_delete_document_error(self, mock_request, mock_get_item_url):
        """Si _request lanza SourceConnectionError, retorna False."""
        mock_get_item_url.return_value = f'https://graph.microsoft.com/v1.0/drives/{self.fake_drive_id}/items/{self.file_id}'
        mock_request.side_effect = SourceConnectionError("OneDrive API error")

        result = self.fetcher.delete_document(self.config, self.file_id)

        mock_get_item_url.assert_called_once()
        mock_request.assert_called_once()
        self.assertFalse(result)

    # ----------------------------------------------------------------------
    # MOVE tests
    # ----------------------------------------------------------------------
    @patch.object(OneDriveSource, '_get_item_url')
    @patch.object(OneDriveSource, '_build_item_url')
    @patch.object(OneDriveSource, '_request')
    def test_move_document_to_folder_by_id(self, mock_request, mock_build_url, mock_get_item_url):
        """Mover a una carpeta usando su ID (destination no empieza con '/')."""
        mock_get_item_url.return_value = f'https://graph.microsoft.com/v1.0/drives/{self.fake_drive_id}/items/{self.file_id}'
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_request.return_value = mock_response

        result = self.fetcher.move_document(
            self.config, self.file_id, self.destination_folder_id
        )

        mock_build_url.assert_not_called()
        mock_get_item_url.assert_called_once_with(self.config, self.file_id)
        mock_request.assert_called_once_with(
            'PATCH',
            f'https://graph.microsoft.com/v1.0/drives/{self.fake_drive_id}/items/{self.file_id}',
            self.config,
            json={"parentReference": {"id": self.destination_folder_id}}
        )
        self.assertTrue(result)

    @patch.object(OneDriveSource, '_get_item_url')
    @patch.object(OneDriveSource, '_build_item_url')
    @patch.object(OneDriveSource, '_request')
    def test_move_document_to_folder_by_path(self, mock_request, mock_build_url, mock_get_item_url):
        """Mover a una carpeta usando una ruta (destination empieza con '/')."""
        destination_path = '/Documents/Projects'
        mock_build_url.return_value = 'https://graph.microsoft.com/v1.0/drives/driveId/root:/Documents/Projects'
        mock_get_item_url.return_value = f'https://graph.microsoft.com/v1.0/drives/{self.fake_drive_id}/items/{self.file_id}'

        # Primera llamada a _request: GET al destino
        mock_response_get = Mock()
        mock_response_get.raise_for_status.return_value = None
        mock_response_get.json.return_value = {'id': 'folder456'}

        # Segunda llamada: PATCH
        mock_response_patch = Mock()
        mock_response_patch.raise_for_status.return_value = None

        mock_request.side_effect = [mock_response_get, mock_response_patch]

        result = self.fetcher.move_document(
            self.config, self.file_id, destination_path
        )

        mock_build_url.assert_called_once_with(self.config, destination_path)
        mock_get_item_url.assert_called_once_with(self.config, self.file_id)

        mock_request.assert_any_call(
            'GET',
            'https://graph.microsoft.com/v1.0/drives/driveId/root:/Documents/Projects',
            self.config
        )
        mock_request.assert_called_with(
            'PATCH',
            f'https://graph.microsoft.com/v1.0/drives/{self.fake_drive_id}/items/{self.file_id}',
            self.config,
            json={"parentReference": {"id": "folder456"}}
        )
        self.assertTrue(result)

    @patch.object(OneDriveSource, '_get_item_url')
    @patch.object(OneDriveSource, '_build_item_url')
    @patch.object(OneDriveSource, '_request')
    def test_move_document_path_does_not_exist(self, mock_request, mock_build_url, mock_get_item_url):
        """Si la ruta de destino no existe (GET falla), debe retornar False."""
        destination_path = '/Invalid/Folder'
        mock_build_url.return_value = 'https://graph.microsoft.com/v1.0/drives/driveId/root:/Invalid/Folder'
        # No debería llegar a llamar a _get_item_url si falla el GET
        mock_request.side_effect = SourceConnectionError("Item not found")

        result = self.fetcher.move_document(
            self.config, self.file_id, destination_path
        )

        mock_build_url.assert_called_once_with(self.config, destination_path)
        mock_request.assert_called_once_with(
            'GET',
            'https://graph.microsoft.com/v1.0/drives/driveId/root:/Invalid/Folder',
            self.config
        )
        mock_get_item_url.assert_not_called()
        self.assertFalse(result)

    @patch.object(OneDriveSource, '_get_item_url')
    @patch.object(OneDriveSource, '_request')
    def test_move_document_patch_error_direct_id(self, mock_request, mock_get_item_url):
        """Si el PATCH falla cuando destination es ID, retorna False."""
        mock_get_item_url.return_value = f'https://graph.microsoft.com/v1.0/drives/{self.fake_drive_id}/items/{self.file_id}'
        mock_request.side_effect = SourceConnectionError("Patch failed")

        result = self.fetcher.move_document(
            self.config, self.file_id, self.destination_folder_id
        )

        mock_get_item_url.assert_called_once_with(self.config, self.file_id)
        mock_request.assert_called_once_with(
            'PATCH',
            f'https://graph.microsoft.com/v1.0/drives/{self.fake_drive_id}/items/{self.file_id}',
            self.config,
            json={"parentReference": {"id": self.destination_folder_id}}
        )
        self.assertFalse(result)

    @patch.object(OneDriveSource, '_get_item_url')
    @patch.object(OneDriveSource, '_build_item_url')
    @patch.object(OneDriveSource, '_request')
    def test_move_document_patch_error_by_path(self, mock_request, mock_build_url, mock_get_item_url):
        """Si el PATCH falla cuando destination es ruta, retorna False."""
        destination_path = '/Documents/Projects'
        mock_build_url.return_value = 'https://graph.microsoft.com/v1.0/drives/driveId/root:/Documents/Projects'
        mock_get_item_url.return_value = f'https://graph.microsoft.com/v1.0/drives/{self.fake_drive_id}/items/{self.file_id}'

        # Primera llamada a _request: GET al destino (éxito)
        mock_response_get = Mock()
        mock_response_get.raise_for_status.return_value = None
        mock_response_get.json.return_value = {'id': 'folder456'}

        # Segunda llamada: PATCH (falla)
        mock_request.side_effect = [
            mock_response_get,
            SourceConnectionError("Patch failed")
        ]

        result = self.fetcher.move_document(
            self.config, self.file_id, destination_path
        )

        mock_build_url.assert_called_once_with(self.config, destination_path)
        mock_get_item_url.assert_called_once_with(self.config, self.file_id)

        mock_request.assert_any_call(
            'GET',
            'https://graph.microsoft.com/v1.0/drives/driveId/root:/Documents/Projects',
            self.config
        )
        mock_request.assert_called_with(
            'PATCH',
            f'https://graph.microsoft.com/v1.0/drives/{self.fake_drive_id}/items/{self.file_id}',
            self.config,
            json={"parentReference": {"id": "folder456"}}
        )
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
