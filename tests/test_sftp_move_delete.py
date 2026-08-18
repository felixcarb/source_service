import unittest
from unittest.mock import Mock, patch
from source_service.fetchers.sftp_fetcher import SFTPSource


class TestSFTPSourceOperations(unittest.TestCase):
    """Pruebas unitarias para move_document y delete_document de SFTPSource."""

    def setUp(self):
        self.fetcher = SFTPSource()
        self.config = {
            'host': 'testhost',
            'username': 'testuser',
            'password': 'testpass',
            'path': '/temp'
        }
        self.key = '/temp/file.pdf'
        self.destination = '/processed/'

    @patch('source_service.fetchers.sftp_fetcher.SFTPSource._connect')
    def test_move_document_to_directory(self, mock_connect):
        """Mover a directorio (destino termina en '/') debe conservar nombre."""
        # Crear un mock del cliente SFTP
        mock_sftp = Mock()
        mock_connect.return_value = mock_sftp

        result = self.fetcher.move_document(
            self.config, self.key, self.destination
        )

        # Verificar que se llamó a rename con la ruta correcta
        # /processed/ + basename(file.pdf)
        expected_new_path = '/processed/file.pdf'
        mock_sftp.rename.assert_called_once_with(self.key, expected_new_path)
        self.assertTrue(result)

    @patch('source_service.fetchers.sftp_fetcher.SFTPSource._connect')
    def test_move_document_with_full_path(self, mock_connect):
        """Mover a una ruta completa (cambiar nombre)."""
        mock_sftp = Mock()
        mock_connect.return_value = mock_sftp

        destination_full = '/processed/new_name.pdf'
        result = self.fetcher.move_document(
            self.config, self.key, destination_full
        )

        mock_sftp.rename.assert_called_once_with(self.key, destination_full)
        self.assertTrue(result)

    @patch('source_service.fetchers.sftp_fetcher.SFTPSource._connect')
    def test_move_document_error(self, mock_connect):
        """Si rename lanza excepción, debe retornar False."""
        mock_sftp = Mock()
        mock_sftp.rename.side_effect = Exception("SFTP error")
        mock_connect.return_value = mock_sftp

        result = self.fetcher.move_document(
            self.config, self.key, self.destination
        )

        self.assertFalse(result)

    @patch('source_service.fetchers.sftp_fetcher.SFTPSource._connect')
    def test_delete_document(self, mock_connect):
        """Eliminación exitosa."""
        mock_sftp = Mock()
        mock_connect.return_value = mock_sftp

        result = self.fetcher.delete_document(self.config, self.key)

        mock_sftp.remove.assert_called_once_with(self.key)
        self.assertTrue(result)

    @patch('source_service.fetchers.sftp_fetcher.SFTPSource._connect')
    def test_delete_document_error(self, mock_connect):
        """Si remove lanza excepción, debe retornar False."""
        mock_sftp = Mock()
        mock_sftp.remove.side_effect = Exception("SFTP delete error")
        mock_connect.return_value = mock_sftp

        result = self.fetcher.delete_document(self.config, self.key)

        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
