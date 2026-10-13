import json
from pathlib import Path
import unittest
from patrick.knowledge import KnowledgeBase, contact_filter

INDEX = Path(__file__).resolve().parents[1] / 'knowledge' / 'combined.json'

class CombinedKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.kb = KnowledgeBase(INDEX)

    def test_selected_name_is_used_in_rag_identity_and_creator(self):
        kb = KnowledgeBase(INDEX, name='scout')
        results = kb.retrieve('Scout creator Aditya')
        self.assertTrue(any("Scout's creator" in r['text'] for r in results))
        self.assertNotIn('Patrick', ' '.join(r['text'] for r in results))
        self.assertTrue(kb.source.startswith('Scout combined'))

    def test_runtime_rename_preserves_sources_and_product_names(self):
        original = INDEX.read_bytes()
        kb = KnowledgeBase(INDEX, name='jarvis')
        results = kb.retrieve('TASKBOT SCOUT')
        self.assertTrue(any('TASKBOT SCOUT' in r['text'] for r in results))
        self.assertEqual(INDEX.read_bytes(), original)


    def test_preserves_sources(self):
        records = json.loads(INDEX.read_text(encoding='utf8'))['records']
        self.assertEqual(sum(r['group'] == 'robot' for r in records), 10)
        self.assertEqual(sum(r['group'] == 'company' and not r['id'].startswith('full-pdf-page-') for r in records), 52)
        self.assertTrue(any(r['id'] == 'creator-portfolio' for r in records))

    def test_searches_all_relevant_groups(self):
        result = self.kb.retrieve('Revobots Aditya creator robot')
        self.assertEqual({r['group'] for r in result}, {'robot', 'company', 'creator'})

    def test_full_pdf_pages_preserved_and_chunked(self):
        snapshot = json.loads((INDEX.parent / 'revobots-full-pdf.json').read_text(encoding='utf8'))
        combined = json.loads(INDEX.read_text(encoding='utf8'))
        records = [r for r in combined['records'] if r['id'].startswith('full-pdf-page-')]
        self.assertEqual(len(records), 11)
        self.assertEqual([r['text'] for r in records], [p['text'] for p in snapshot['pages']])
        indexed_pages = {m['page'] for m in self.kb.metadata if m['id'].startswith('full-pdf-page-')}
        self.assertEqual(indexed_pages, set(range(1, 12)))

    def test_revo248_aliases_retrieve_framework_and_timings(self):
        for alias in ('REVO248', 'REVO 248', 'REVO 2-4-8'):
            result = self.kb.retrieve(alias)
            framework = next(r for r in result if r.get('title') == 'REVO 2-4-8 (editorial draft)')
            self.assertIn('2 days', framework['text'])
            self.assertIn('4 weeks', framework['text'])
            self.assertIn('8 weeks', framework['text'])

    def test_concepts_preserve_status(self):
        result = self.kb.retrieve('TASKBOT RANGER server handling')
        self.assertTrue(any('draft/concept' in r.get('status', '') for r in result))

    def test_email_requires_email_query(self):
        self.assertNotIn('@', json.dumps(self.kb.retrieve('Aditya creator contact')))
        self.assertTrue(any(r.get('contact') == 'email' for r in self.kb.retrieve('Aditya email')))

    def test_filters_nested_contacts_without_removing_dates(self):
        value = contact_filter({'text': '2019-2023 +91 98765 43210 name@example.com'})
        self.assertIn('2019-2023', value['text'])
        self.assertNotIn('98765', value['text'])
        self.assertNotIn('@', value['text'])
        self.assertIn('@', contact_filter('name@example.com', True))
