from django.core.management.base import BaseCommand
from events.email_service import send_digest


class Command(BaseCommand):
    help = 'Send the event digest newsletter (weekly or monthly)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--frequency',
            choices=['WEEKLY', 'MONTHLY'],
            default='WEEKLY',
            help='Which digest to send (default: WEEKLY)',
        )

    def handle(self, *args, **options):
        frequency = options['frequency']
        self.stdout.write(f"Sending {frequency} digest...")
        result = send_digest(frequency)
        self.stdout.write(self.style.SUCCESS(
            f"Done. Sent: {result['sent']}, Failed: {result['failed']}"
        ))
