import unittest
from unittest import mock

from django.test import tag

from ingestion.models import EventSource
from ingestion.prompt_dispatch import run_batch_per_source


@tag("fast")
class RunBatchPerSourceTests(unittest.TestCase):
    """run_batch_per_source only touches EventSource.objects.all() and the
    batch_fn it's handed, so these are exercised against mocks/stubs — no DB
    needed. The DB-backed regression test that actually mocks Gemini and
    checks prompt content lives in test_prompt_dispatch_db.py.
    """

    def test_calls_batch_fn_once_per_source_then_sweeps_with_none(self):
        s1, s2 = mock.Mock(name="s1"), mock.Mock(name="s2")
        calls = []

        def batch_fn(source=None):
            calls.append(source)
            return 1

        with mock.patch.object(EventSource.objects, "all", return_value=[s1, s2]):
            total = run_batch_per_source(batch_fn, step_name="test")

        self.assertEqual(calls, [s1, s2, None])
        self.assertEqual(total, 3)

    def test_null_source_row_is_still_processed_by_the_sweep(self):
        """A row with no source (or one created after the per-source loop
        started) can't be reached by iterating EventSource.objects.all() —
        the trailing batch_fn(source=None) sweep is what picks it up."""

        def batch_fn(source=None):
            return 1 if source is None else 0

        with mock.patch.object(EventSource.objects, "all", return_value=[mock.Mock()]):
            total = run_batch_per_source(batch_fn, step_name="test")

        self.assertEqual(total, 1)

    def test_one_source_raising_does_not_prevent_the_rest(self):
        s1, s2, s3 = mock.Mock(name="s1"), mock.Mock(name="s2"), mock.Mock(name="s3")

        def batch_fn(source=None):
            if source is s2:
                raise RuntimeError("boom")
            return 1

        with mock.patch.object(EventSource.objects, "all", return_value=[s1, s2, s3]):
            total = run_batch_per_source(batch_fn, step_name="test")

        # s1 + s3 + the final sweep succeed; s2 raised and contributed 0.
        self.assertEqual(total, 3)

    def test_no_sources_still_runs_the_sweep(self):
        def batch_fn(source=None):
            return 5 if source is None else 0

        with mock.patch.object(EventSource.objects, "all", return_value=[]):
            total = run_batch_per_source(batch_fn, step_name="test")

        self.assertEqual(total, 5)
