import ast
import pathlib

from django.test import SimpleTestCase, tag

# accounts legitimately imports events (Tag/Town M2M fields, business filters)
# and newsletter (the `me` view syncs a NewsletterSubscriber row). It must
# never reach into ingestion or broadcast.
FORBIDDEN_ROOTS = {"ingestion", "broadcast"}


@tag("fast")
class IsolationTest(SimpleTestCase):
    def test_accounts_imports_nothing_from_ingestion_or_broadcast(self):
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
