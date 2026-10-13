import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

spec = importlib.util.spec_from_file_location('knowledge_cleanup', Path(__file__).resolve().parents[1] / 'scripts/cleanup_knowledge.py')
cleanup_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup_module)


class CleanupTests(unittest.TestCase):
    def test_only_fully_preserved_snapshots_are_removed_with_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            knowledge = root / 'knowledge'
            knowledge.mkdir()
            (knowledge / 'combined.json').write_text(json.dumps({'records': [{'id': 'robot-page-1', 'text': 'Battery charger'}]}))
            old = {'source': 'original.pdf', 'sha256': 'checksum', 'pages': [{'page': 1, 'text': 'Battery charger'}]}
            (knowledge / 'revobots.json').write_text(json.dumps(old))
            (knowledge / 'revobots-full-pdf.json').write_text(json.dumps({'source': 'new.pdf', 'pages': [{'page': 1, 'text': 'Unique new fact'}]}))
            with patch.object(cleanup_module, 'PROJECT', root):
                cleanup_module.cleanup(dry_run=True)
                self.assertTrue((knowledge / 'revobots.json').exists())
                cleanup_module.cleanup()
            self.assertFalse((knowledge / 'revobots.json').exists())
            self.assertTrue((knowledge / 'revobots-full-pdf.json').exists())
            combined = json.loads((knowledge / 'combined.json').read_text())
            self.assertEqual(combined['source_metadata']['original.pdf']['sha256'], 'checksum')
            with ZipFile(next((root / 'build/rag-backups').glob('*.zip'))) as archive:
                self.assertEqual(json.loads(archive.read('revobots.json')), old)
