import unittest
from unittest.mock import Mock, patch
from source_service.fetchers.s3_fetcher import S3Source


class TestS3SourceOperations(unittest.TestCase):
    """Pruebas unitarias para move_document y delete_document de S3Source."""

    def setUp(self):
        self.fetcher = S3Source()
        self.config = {
            'bucket_name': 'test-bucket',
            'access_key_id': 'fake-key',
            'secret_access_key': 'fake-secret',
            'region': 'us-east-1',
        }
        self.key = 'folder/file.pdf'
        self.destination = 'processed/'

    @patch('source_service.fetchers.s3_fetcher.S3Source._get_client')
    def test_move_document_to_directory(self, mock_get_client):
        """Mover a un prefijo que termina en '/' debe conservar el nombre."""
        mock_s3 = Mock()
        mock_get_client.return_value = mock_s3

        result = self.fetcher.move_document(
            self.config, self.key, self.destination
        )

        # Se espera que el destino sea 'processed/file.pdf'
        expected_dest_key = 'processed/file.pdf'
        mock_s3.copy_object.assert_called_once_with(
            CopySource={'Bucket': 'test-bucket', 'Key': self.key},
            Bucket='test-bucket',
            Key=expected_dest_key
        )
        mock_s3.delete_object.assert_called_once_with(
            Bucket='test-bucket', Key=self.key
        )
        self.assertTrue(result)

    @patch('source_service.fetchers.s3_fetcher.S3Source._get_client')
    def test_move_document_with_full_key(self, mock_get_client):
        """Mover a un key completo (cambiar nombre y/o ruta)."""
        mock_s3 = Mock()
        mock_get_client.return_value = mock_s3

        destination_full = 'archive/2024/file.pdf'
        result = self.fetcher.move_document(
            self.config, self.key, destination_full
        )

        mock_s3.copy_object.assert_called_once_with(
            CopySource={'Bucket': 'test-bucket', 'Key': self.key},
            Bucket='test-bucket',
            Key=destination_full
        )
        mock_s3.delete_object.assert_called_once_with(
            Bucket='test-bucket', Key=self.key
        )
        self.assertTrue(result)

    @patch('source_service.fetchers.s3_fetcher.S3Source._get_client')
    def test_move_document_error_on_copy(self, mock_get_client):
        """Si copy_object falla, debe retornar False (el original no se elimina)."""
        mock_s3 = Mock()
        mock_s3.copy_object.side_effect = Exception("S3 copy error")
        mock_get_client.return_value = mock_s3

        result = self.fetcher.move_document(
            self.config, self.key, self.destination
        )

        # No debe llamar a delete_object si falla la copia
        mock_s3.delete_object.assert_not_called()
        self.assertFalse(result)

    @patch('source_service.fetchers.s3_fetcher.S3Source._get_client')
    def test_move_document_error_on_delete(self, mock_get_client):
        """Si copy_object funciona pero delete_object falla, debe retornar False."""
        mock_s3 = Mock()
        mock_s3.copy_object.return_value = {}
        mock_s3.delete_object.side_effect = Exception("S3 delete error")
        mock_get_client.return_value = mock_s3

        result = self.fetcher.move_document(
            self.config, self.key, self.destination
        )

        mock_s3.copy_object.assert_called_once()
        mock_s3.delete_object.assert_called_once()
        self.assertFalse(result)

    @patch('source_service.fetchers.s3_fetcher.S3Source._get_client')
    def test_delete_document(self, mock_get_client):
        """Eliminación exitosa."""
        mock_s3 = Mock()
        mock_get_client.return_value = mock_s3

        result = self.fetcher.delete_document(self.config, self.key)

        mock_s3.delete_object.assert_called_once_with(
            Bucket='test-bucket', Key=self.key
        )
        self.assertTrue(result)

    @patch('source_service.fetchers.s3_fetcher.S3Source._get_client')
    def test_delete_document_error(self, mock_get_client):
        """Si delete_object lanza excepción, debe retornar False."""
        mock_s3 = Mock()
        mock_s3.delete_object.side_effect = Exception("S3 delete error")
        mock_get_client.return_value = mock_s3

        result = self.fetcher.delete_document(self.config, self.key)

        mock_s3.delete_object.assert_called_once_with(
            Bucket='test-bucket', Key=self.key
        )
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
