import unittest
from unittest.mock import Mock, patch
from source_service.fetchers.ftp_fetcher import FTPSource


class TestFTPSourceOperations(unittest.TestCase):
    """Pruebas unitarias para move_document y delete_document de FTPSource."""

    def setUp(self):
        self.fetcher = FTPSource()
        self.config = {
            'host': 'testhost',
            'username': 'testuser',
            'password': 'testpass',
            'path': '/temp'
        }
        self.key = '/temp/file.pdf'
        self.destination = '/processed/'

    @patch('source_service.fetchers.ftp_fetcher.FTPSource._connect')
    def test_move_document_to_directory(self, mock_connect):
        """Mover a directorio (destino termina en '/') debe conservar nombre."""
        mock_ftp = Mock()
        mock_connect.return_value = mock_ftp

        result = self.fetcher.move_document(
            self.config, self.key, self.destination
        )

        # Se espera que llame a ftp.rename con /processed/file.pdf
        expected_new_path = '/processed/file.pdf'
        mock_ftp.rename.assert_called_once_with(self.key, expected_new_path)
        self.assertTrue(result)

    @patch('source_service.fetchers.ftp_fetcher.FTPSource._connect')
    def test_move_document_with_full_path(self, mock_connect):
        """Mover a una ruta completa (cambiar nombre)."""
        mock_ftp = Mock()
        mock_connect.return_value = mock_ftp

        destination_full = '/processed/new_name.pdf'
        result = self.fetcher.move_document(
            self.config, self.key, destination_full
        )

        mock_ftp.rename.assert_called_once_with(self.key, destination_full)
        self.assertTrue(result)

    @patch('source_service.fetchers.ftp_fetcher.FTPSource._connect')
    def test_move_document_error(self, mock_connect):
        """Si rename lanza excepción, debe retornar False."""
        mock_ftp = Mock()
        mock_ftp.rename.side_effect = Exception("FTP rename error")
        mock_connect.return_value = mock_ftp

        result = self.fetcher.move_document(
            self.config, self.key, self.destination
        )

        self.assertFalse(result)

    @patch('source_service.fetchers.ftp_fetcher.FTPSource._connect')
    def test_delete_document(self, mock_connect):
        """Eliminación exitosa."""
        mock_ftp = Mock()
        mock_connect.return_value = mock_ftp

        result = self.fetcher.delete_document(self.config, self.key)

        mock_ftp.delete.assert_called_once_with(self.key)
        self.assertTrue(result)

    @patch('source_service.fetchers.ftp_fetcher.FTPSource._connect')
    def test_delete_document_error(self, mock_connect):
        """Si delete lanza excepción, debe retornar False."""
        mock_ftp = Mock()
        mock_ftp.delete.side_effect = Exception("FTP delete error")
        mock_connect.return_value = mock_ftp

        result = self.fetcher.delete_document(self.config, self.key)

        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
