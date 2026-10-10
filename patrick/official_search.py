"""Official Revobots website fallback alongside general web search."""
import json
from urllib.parse import urlparse
from .tools import OpenAISearchTools, WEB_SEARCH_SCHEMA


class OfficialRevobotsSearch(OpenAISearchTools):
    def _request(self, query):
        request = super()._request(query)
        body = json.loads(request.data)
        body["tools"][0]["filters"] = {"allowed_domains": ["revobots.ai"]}
        request.data = json.dumps(body).encode()
        return request

    def _result(self, data, query):
        result = super()._result(data, query)
        for source in result["sources"]:
            host = (urlparse(source["url"]).hostname or "").lower()
            if host != "revobots.ai" and not host.endswith(".revobots.ai"):
                raise ValueError("Official search returned a source outside revobots.ai")
        result["official_site"] = "https://revobots.ai/"
        return result


class RevobotsWebTools:
    def __init__(self, general):
        self.general = general
        self.official = OfficialRevobotsSearch(general.api_key, general.model, general.timeout, general.opener)
        self.schemas = list(general.schemas) + [{"type": "function", "function": {
            **WEB_SEARCH_SCHEMA["function"], "name": "revobots_site_search",
            "description": "Search only revobots.ai, Revobots' official website, for public company details missing from local knowledge or current company information. Use public English keywords only."}}]

    def execute(self, name, arguments, cancelled, register_stream=lambda stream: None):
        if name == "revobots_site_search":
            return self.official.execute("web_search", arguments, cancelled, register_stream)
        return self.general.execute(name, arguments, cancelled, register_stream)
