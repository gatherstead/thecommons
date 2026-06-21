import json
import unittest
from unittest import mock

from django.test import tag

from ingestion.models import StagedEvent
from ingestion.safety_scorer import SAFETY_SCORE_THRESHOLD, score_event


@tag('fast')
class SafetyScorerTests(unittest.TestCase):
    """score_event only reads attributes off the StagedEvent, so an unsaved
    in-memory instance is enough — no DB needed."""

    def _staged(self):
        return StagedEvent(
            title='Community Potluck',
            description='A friendly neighborhood gathering.',
            location_name='Town Commons',
        )

    def _gemini_scoring(self, score):
        client = mock.Mock()
        client.models.generate_content.return_value = mock.Mock(
            text=json.dumps({'score': score, 'notes': 'reason'})
        )
        return mock.patch('ingestion.safety_scorer.genai.Client', return_value=client)

    def test_clear_pass_scores_below_threshold(self):
        with self._gemini_scoring(0.02):
            score, notes = score_event(self._staged())
        self.assertLessEqual(score, SAFETY_SCORE_THRESHOLD)
        self.assertEqual(notes, 'reason')

    def test_clear_fail_scores_above_threshold(self):
        with self._gemini_scoring(0.95):
            score, _ = score_event(self._staged())
        self.assertGreater(score, SAFETY_SCORE_THRESHOLD)

    def test_score_is_clamped_to_unit_interval(self):
        with self._gemini_scoring(4.5):
            score, _ = score_event(self._staged())
        self.assertEqual(score, 1.0)
