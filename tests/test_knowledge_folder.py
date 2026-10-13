import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from patrick.knowledge import KnowledgeBase


class FolderKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding='utf8')
        return path

    def test_recursive_files_and_new_files_after_restart(self):
        self.write('robots.json', json.dumps({'source': 'robot', 'pages': [{'page': 1, 'text': 'Cameras detect obstacles.'}]}))
        self.write('company/info.md', '# Company\nRevobots provides teleoperation.')
        self.write('other.txt', 'The antenna supports wireless communication.')
        kb = KnowledgeBase(self.root)
        self.assertEqual(len(kb.files), 3)
        self.assertTrue(kb.retrieve('antenna'))
        self.write('new.md', 'The charger supports automatic docking.')
        self.assertFalse(kb.retrieve('charger'))
        self.assertTrue(KnowledgeBase(self.root).retrieve('charger'))

    def test_duplicate_records_merge_provenance(self):
        self.write('a.txt', 'Robots use cameras for navigation.')
        self.write('b.md', 'Robots  use cameras\nfor navigation.')
        kb = KnowledgeBase(self.root)
        self.assertEqual(len(kb.chunks), 1)
        self.assertEqual(kb.duplicate_records, 1)
        self.assertEqual({r['file'] for r in kb.retrieve('navigation')[0]['references']}, {'a.txt', 'b.md'})

    def test_duplicate_chunks_do_not_remove_unique_facts(self):
        common = ' '.join('shared' + str(i) for i in range(150))
        self.write('a.txt', common + ' copper motor')
        self.write('b.txt', common + ' silver antenna')
        kb = KnowledgeBase(self.root)
        self.assertEqual(kb.duplicate_chunks, 1)
        self.assertTrue(kb.retrieve('copper'))
        self.assertTrue(kb.retrieve('silver'))

    def test_jsonl_and_structured_json(self):
        self.write('facts.jsonl', '{"text":"battery charging system"}\n{"text":"motor encoder"}\n')
        self.write('spec.json', '{"payload_kg":5,"device":"gripper"}')
        kb = KnowledgeBase(self.root)
        self.assertTrue(kb.retrieve('encoder'))
        self.assertTrue(kb.retrieve('gripper'))

    def test_hidden_files_and_unsupported_files_are_not_ingested(self):
        self.write('public.txt', 'Public robot navigation.')
        self.write('.secret.txt', 'Private password.')
        self.write('backup.zip', 'not a document')
        self.write('.cache/notes.txt', 'Hidden cache.')
        kb = KnowledgeBase(self.root)
        self.assertEqual(kb.files, ['public.txt'])
        self.assertFalse(kb.retrieve('password'))

    def test_unrelated_page_json_keeps_first_lines(self):
        file = self.write('page.json', json.dumps({'source': 'manual', 'pages': [{'page': 1, 'text': 'Battery voltage\n24 volts\nCharger'}]}))
        self.assertIn('24 volts', KnowledgeBase(file).retrieve('voltage')[0]['text'])

    def test_invalid_json_and_empty_folder_fail_clearly(self):
        with self.assertRaisesRegex(ValueError, 'No supported'):
            KnowledgeBase(self.root)
        self.write('invalid.json', '{invalid')
        with self.assertRaisesRegex(ValueError, 'invalid.json'):
            KnowledgeBase(self.root)

    def test_folder_contacts_are_filtered(self):
        self.write('contact.txt', 'Creator biography name@example.com +91 98765 43210')
        kb = KnowledgeBase(self.root)
        result = json.dumps(kb.retrieve('creator biography'))
        self.assertNotIn('@', result)
        self.assertNotIn('98765', result)
        self.assertIn('@', json.dumps(kb.retrieve('creator email biography')))

    def test_pdf_page_provenance_and_empty_pdf_error(self):
        self.write('manual.pdf', 'fixture')
        page = type('Page', (), {'extract_text': lambda self, **kwargs: 'Lidar enables perception.'})()
        reader = type('Reader', (), {'pages': [page]})()
        with patch('pypdf.PdfReader', return_value=reader):
            result = KnowledgeBase(self.root).retrieve('lidar')[0]
        self.assertEqual(result['page'], 1)
        self.assertEqual(result['file'], 'manual.pdf')
        empty = type('Reader', (), {'pages': []})()
        with patch('pypdf.PdfReader', return_value=empty), self.assertRaisesRegex(ValueError, 'OCR'):
            KnowledgeBase(self.root)
