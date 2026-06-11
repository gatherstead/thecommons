import ast
import pathlib

from django.test import SimpleTestCase

FORBIDDEN_ROOTS = {"events", "ingestion"}


class IsolationTest(SimpleTestCase):
    def test_broadcast_imports_nothing_from_events_or_ingestion(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        offenders = []
        for path in root.rglob("*.py"):
            if "tests" in path.parts:
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
