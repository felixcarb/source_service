import unittest
from unittest.mock import patch
import os
from source_service.fetchers.smb_fetcher import SMBSource


class TestSMBSourceOperations(unittest.TestCase):
    """Pruebas unitarias para move_document y delete_document de SMBSource."""

    def setUp(self):
        self.fetcher = SMBSource()
        self.config = {
            'host': 'testserver',
            'username': 'testuser',
            'password': 'testpass',
            'share': 'documents',
            'path': '/temp'
        }
        self.key = '/temp/file.pdf'
        self.destination = '/processed/'

    @patch('source_service.fetchers.smb_fetcher.smbclient')
    @patch('source_service.fetchers.smb_fetcher.SMBSource._ensure_session')
    def test_move_document_to_directory(self, mock_ensure_session, mock_smbclient):
        """Mover a directorio (destino termina en '/') debe conservar nombre."""
        mock_ensure_session.return_value = None

        result = self.fetcher.move_document(
            self.config, self.key, self.destination
        )

        # Construir las rutas UNC esperadas usando el método real
        old_unc = self.fetcher._get_unc_path(self.config, self.key)
        new_unc = self.fetcher._get_unc_path(
            self.config, self.destination + os.path.basename(self.key)
        )

        mock_smbclient.rename.assert_called_once_with(old_unc, new_unc)
        self.assertTrue(result)

    @patch('source_service.fetchers.smb_fetcher.smbclient')
    @patch('source_service.fetchers.smb_fetcher.SMBSource._ensure_session')
    def test_move_document_with_full_path(self, mock_ensure_session, mock_smbclient):
        """Mover a una ruta completa (cambiar nombre)."""
        mock_ensure_session.return_value = None

        destination_full = '/processed/new_name.pdf'
        result = self.fetcher.move_document(
            self.config, self.key, destination_full
        )

        old_unc = self.fetcher._get_unc_path(self.config, self.key)
        new_unc = self.fetcher._get_unc_path(self.config, destination_full)

        mock_smbclient.rename.assert_called_once_with(old_unc, new_unc)
        self.assertTrue(result)

    @patch('source_service.fetchers.smb_fetcher.smbclient')
    @patch('source_service.fetchers.smb_fetcher.SMBSource._ensure_session')
    def test_move_document_error(self, mock_ensure_session, mock_smbclient):
        """Si rename lanza excepción, debe retornar False."""
        mock_ensure_session.return_value = None
        mock_smbclient.rename.side_effect = Exception("SMB rename error")

        result = self.fetcher.move_document(
            self.config, self.key, self.destination
        )

        self.assertFalse(result)

    @patch('source_service.fetchers.smb_fetcher.smbclient')
    @patch('source_service.fetchers.smb_fetcher.SMBSource._ensure_session')
    def test_delete_document(self, mock_ensure_session, mock_smbclient):
        """Eliminación exitosa."""
        mock_ensure_session.return_value = None

        result = self.fetcher.delete_document(self.config, self.key)

        expected_unc = self.fetcher._get_unc_path(self.config, self.key)
        mock_smbclient.remove.assert_called_once_with(expected_unc)
        self.assertTrue(result)

    @patch('source_service.fetchers.smb_fetcher.smbclient')
    @patch('source_service.fetchers.smb_fetcher.SMBSource._ensure_session')
    def test_delete_document_error(self, mock_ensure_session, mock_smbclient):
        """Si remove lanza excepción, debe retornar False."""
        mock_ensure_session.return_value = None
        mock_smbclient.remove.side_effect = Exception("SMB remove error")

        result = self.fetcher.delete_document(self.config, self.key)

        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
