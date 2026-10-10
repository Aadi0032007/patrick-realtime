import json
import threading
import unittest
from patrick.tools import OpenAISearchTools
from patrick.official_search import OfficialRevobotsSearch, RevobotsWebTools


class OfficialSearchTests(unittest.TestCase):
    def test_official_request_has_domain_filter_general_does_not(self):
        tools = RevobotsWebTools(OpenAISearchTools("test-key"))
        self.assertEqual(json.loads(tools.official._request("products").data)["tools"][0]["filters"],
                         {"allowed_domains": ["revobots.ai"]})
        self.assertNotIn("filters", json.loads(tools.general._request("news").data)["tools"][0])
        self.assertEqual({s["function"]["name"] for s in tools.schemas}, {"web_search", "revobots_site_search"})

    def test_rejects_unofficial_source_urls(self):
        search = OfficialRevobotsSearch("test-key")
        data = {"status": "completed", "output": [{"type": "web_search_call"},
            {"type": "message", "content": [{"type": "output_text", "text": "A fact", "annotations": [
                {"type": "url_citation", "url": "https://revobots.ai.fake.example/", "title": "Fake"}]}]}]}
        with self.assertRaises(ValueError):
            search._result(data, "facts")
        data["output"][1]["content"][0]["annotations"][0]["url"] = "https://revobots.ai/"
        self.assertEqual(search._result(data, "facts")["official_site"], "https://revobots.ai/")

    def test_unknown_tool_is_rejected_without_network(self):
        tools = RevobotsWebTools(OpenAISearchTools("test-key", opener=lambda *a, **kw: self.fail("Network access")))
        self.assertIn("error", tools.execute("run_shell", {}, threading.Event()))
