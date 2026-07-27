import unittest
from unittest.mock import patch, MagicMock
from source_service.fetchers.s3_fetcher import S3Source
from source_service.exceptions import DocumentNotFoundError


class TestS3Source(unittest.TestCase):
    def setUp(self):
        self.config = {
            'bucket': 'test-bucket',
            'access_key': 'key',
            'secret_key': 'secret',
            'region': 'us-east-1',
        }
        self.source = S3Source()

    @patch('boto3.Session')
    def test_list_documents_success(self, mock_session):
        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {'Contents': [{'Key': 'doc1.pdf', 'Size': 1024,
                           'LastModified': '2023-01-01'}]}
        ]
        mock_s3.get_paginator.return_value = mock_paginator
        mock_session.return_value.client.return_value = mock_s3

        docs = self.source.list_documents(self.config)
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].key, 'doc1.pdf')
        self.assertEqual(docs[0].metadata['size'], 1024)

    @patch('boto3.Session')
    def test_fetch_document_success(self, mock_session):
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {
            'Body': MagicMock(read=MagicMock(return_value=b'content')),
            'ContentLength': 7,
            'LastModified': '2023-01-01',
            'ContentType': 'application/pdf'
        }
        mock_session.return_value.client.return_value = mock_s3

        doc = self.source.fetch_document(self.config, 'doc1.pdf')
        self.assertEqual(doc.key, 'doc1.pdf')
        self.assertEqual(doc.content, b'content')
        self.assertEqual(doc.metadata['size'], 7)

    @patch('boto3.Session')
    def test_fetch_document_not_found(self, mock_session):
        from botocore.exceptions import ClientError
        mock_s3 = MagicMock()
        error_response = {'Error': {'Code': 'NoSuchKey'}}
        mock_s3.get_object.side_effect = ClientError(
            error_response, 'GetObject')
        mock_session.return_value.client.return_value = mock_s3

        with self.assertRaises(DocumentNotFoundError):
            self.source.fetch_document(self.config, 'missing.pdf')
