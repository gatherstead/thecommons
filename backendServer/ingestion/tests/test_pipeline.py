from unittest import mock

from celery.exceptions import Retry
from django.test import TestCase, override_settings

from ingestion.tasks import run_ingestion_pipeline


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class RunIngestionPipelineTests(TestCase):
    def test_runs_all_steps_once(self):
        with mock.patch('ingestion.tasks.call_command') as cleanup, \
             mock.patch('ingestion.tasks.poll_all_ics_sources', return_value=3) as poll, \
             mock.patch('ingestion.tasks.standardize_all_unprocessed', return_value=2) as standardize, \
             mock.patch('ingestion.tasks.dedup_all_pending', return_value=1) as dedup, \
             mock.patch('ingestion.tasks.score_all_unscored', return_value=2) as score, \
             mock.patch(
                 'ingestion.tasks.auto_publish_safe_events',
                 return_value={'auto_approved': 1, 'held_for_review': 1},
             ) as autopublish:
            run_ingestion_pipeline.delay()

        cleanup.assert_called_once_with('cleanup_old_events')
        poll.assert_called_once()
        standardize.assert_called_once()
        dedup.assert_called_once()
        score.assert_called_once()
        autopublish.assert_called_once()

    def test_failing_step_retries_whole_pipeline(self):
        with mock.patch('ingestion.tasks.call_command'), \
             mock.patch('ingestion.tasks.poll_all_ics_sources', return_value=0), \
             mock.patch('ingestion.tasks.standardize_all_unprocessed', side_effect=RuntimeError('gemini timeout')) as standardize, \
             mock.patch('ingestion.tasks.dedup_all_pending', return_value=0), \
             mock.patch('ingestion.tasks.score_all_unscored', return_value=0), \
             mock.patch('ingestion.tasks.auto_publish_safe_events', return_value={'auto_approved': 0, 'held_for_review': 0}):
            # In eager mode self.retry() raises Retry rather than re-executing inline;
            # this confirms a failed step requests a whole-pipeline retry.
            with self.assertRaises(Retry):
                run_ingestion_pipeline.delay()

        self.assertEqual(standardize.call_count, 1)
