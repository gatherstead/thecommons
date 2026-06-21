import os
import unittest
from datetime import date
from unittest import mock

from django.test import tag

from ingestion.tasks import _resolve_env_shard


def _env_without_shard():
    return {k: v for k, v in os.environ.items() if k != 'INGEST_SHARD_COUNT'}


@tag('fast')
class ResolveEnvShardTests(unittest.TestCase):
    def test_unset_returns_none(self):
        with mock.patch.dict(os.environ, _env_without_shard(), clear=True):
            self.assertIsNone(_resolve_env_shard())

    def test_count_of_one_disables_sharding(self):
        with mock.patch.dict(os.environ, {'INGEST_SHARD_COUNT': '1'}):
            self.assertIsNone(_resolve_env_shard())

    def test_non_integer_is_ignored(self):
        with mock.patch.dict(os.environ, {'INGEST_SHARD_COUNT': 'abc'}):
            self.assertIsNone(_resolve_env_shard())

    def test_valid_count_rotates_by_day_of_year(self):
        with mock.patch.dict(os.environ, {'INGEST_SHARD_COUNT': '4'}):
            result = _resolve_env_shard()
        expected_n = date.today().timetuple().tm_yday % 4
        self.assertEqual(result, (expected_n, 4))
