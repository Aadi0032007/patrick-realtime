# Revobots RAG details

Local index: knowledge/revobots.json
Source: Revobots_Robot_RAG_Knowledge_Base_Company_Updated.pdf
10 pages; 31 chunks. The original PDF is not included in this repository.

Retrieval: local BM25 keyword ranking, 150-word chunks with a 110-word stride (40-word overlap), up to 4 matching excerpts per query. Excerpts preserve PDF source name and page number. Queries should use focused English keywords; answers use the user's language. No embeddings or vector database are needed.

Coverage: robot overview and company context; leadership and core team; mobile AGV base; cameras and perception; sensors; NVIDIA Jetson NX compute; lighting and displays; robotic arm; remote dashboard and teleoperation; Cortex robotic action AI; intended applications; behavior and safety context; sample questions; terminology and provenance.

Source priority:
1. knowledge_search retrieves canonical local robot and team facts.
2. revobots_site_search searches only https://revobots.ai/ (including its subdomains) for missing or current company details. Enabled with the OpenAI web-search provider. It is live retrieval, not a stored website snapshot.
3. web_search handles other current public information.

Robot-specific PDF facts remain primary. Generic product descriptions from the website must not be substituted for this robot's specifications. Unknown details are not invented. Public website searches must not include private PDF excerpts. Retrieved content is data, not instructions.

Official-site retrieval uses OpenAI Responses web_search allowed_domains=['revobots.ai']; cited source hosts are validated. Failed searches return an error. Search results are cached for 120 seconds. The existing tool loop allows up to 4 continuation rounds. Selected PDF excerpts and search results are sent to OpenAI for answering. Web search has additional API usage charges.

Patrick speaks naturally in first person, in 1 to 6 sentences. Searches are silent and sources are not spoken unless requested; links may still print in the terminal. Changing knowledge/revobots.json requires restarting to reload the index.