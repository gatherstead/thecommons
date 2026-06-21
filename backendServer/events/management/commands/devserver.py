import socket

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "runserver with automatic port increment on conflict"

    def add_arguments(self, parser):
        parser.add_argument("addrport", nargs="?", default="8000")

    def handle(self, *args, **options):
        addrport = options["addrport"]
        if ":" in addrport:
            addr, port_str = addrport.rsplit(":", 1)
        else:
            addr, port_str = "127.0.0.1", addrport

        port = int(port_str)
        while True:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind((addr, port))
                    break
                except OSError:
                    self.stdout.write(f"Port {port} in use, trying {port + 1}…")
                    port += 1

        call_command("runserver", f"{addr}:{port}")
