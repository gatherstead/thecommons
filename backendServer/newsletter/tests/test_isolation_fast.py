import ast
import pathlib

from django.test import SimpleTestCase, tag

# newsletter legitimately imports events (events.email_service.send_email is
# the shared Brevo transport) and accounts (newsletter.email_service._build_
# recipients reads UserProfile.tags to narrow digests — mirrors accounts'
# own sanctioned import of newsletter for its `me` view). It must never
# reach into ingestion or broadcast.
FORBIDDEN_ROOTS = {"ingestion", "broadcast"}


@tag("fast")
class IsolationTest(SimpleTestCase):
    def test_newsletter_imports_nothing_from_ingestion_or_broadcast(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        offenders = []
        for path in root.rglob("*.py"):
            if "tests" in path.parts or "migrations" in path.parts:
                continue
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    mods.append(node.module)
                if isinstance(node, ast.Import):
                    mods.extend(a.name for a in node.names)
                for m in mods:
                    if m.split(".")[0] in FORBIDDEN_ROOTS:
                        offenders.append((str(path), m))
        self.assertFalse(offenders, f"isolation breach: {offenders}")
