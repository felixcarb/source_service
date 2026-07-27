import unittest
from source_service.factory import SourceFactory
from source_service.exceptions import InvalidConfigurationError


class TestFactory(unittest.TestCase):
    def test_get_existing_source(self):
        source = SourceFactory.get_source('s3')
        self.assertIsNotNone(source)

    def test_get_invalid_source(self):
        with self.assertRaises(InvalidConfigurationError):
            SourceFactory.get_source('invalid')
