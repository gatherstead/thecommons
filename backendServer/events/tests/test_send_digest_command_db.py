from unittest import mock

from django.core.management import call_command
from django.test import TestCase, tag


@tag('db')
class SendWeeklyDigestCommandTests(TestCase):
    def test_command_enqueues_fan_out_task(self):
        # The command was changed to enqueue the fan-out task rather than send
        # inline — assert it calls .delay(), not the old inline path.
        with mock.patch(
            'events.management.commands.send_weekly_digest.fan_out_weekly_digest.delay'
        ) as delay:
            delay.return_value = mock.Mock(id='task-xyz')
            call_command('send_weekly_digest')
        delay.assert_called_once_with()
