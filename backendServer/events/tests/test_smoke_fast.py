"""Fast tier: pure logic, no database. `manage.py test --tag=fast` runs only
these and must never open a DB connection.
"""
import unittest

from django.test import tag

from broadcast.access import _parse_codes


@tag('fast')
class ParseCodesTests(unittest.TestCase):
    def test_parses_label_code_pairs(self):
        self.assertEqual(
            _parse_codes('a:CODE1,b:CODE2'),
            {'a': 'CODE1', 'b': 'CODE2'},
        )

    def test_skips_malformed_and_empty_pairs(self):
        self.assertEqual(_parse_codes('a:CODE1,,nocolon, :blank'), {'a': 'CODE1'})

    def test_empty_string_is_empty_dict(self):
        self.assertEqual(_parse_codes(''), {})
