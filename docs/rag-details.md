# Patrick RAG details

Default: the entire `knowledge/` folder, recursively. Restart after adding or changing files.

Supported reference formats: PDF (extractable text), JSON, JSONL, Markdown, TXT/TEXT, CSV and RST. Hidden files/folders, symlinks and other formats are skipped. A scanned PDF needs OCR first. Invalid supported files fail clearly rather than silently omitting knowledge.

Set `RAG_KNOWLEDGE_DIR=knowledge` or use `--knowledge PATH`. An explicit file path indexes just that file. The legacy `RAG_KNOWLEDGE_FILE` environment setting defaults to its parent folder so existing deployments also scan all reference files.

Records and chunks with identical text after case/whitespace normalization are indexed once, merging provenance. Distinct wording and facts remain. This is exact deduplication, not a semantic rewrite. The original robot and full-PDF snapshots were fully duplicated in `combined.json`; all 10 robot pages and all 11 PDF pages were verified before removing the redundant files, and their metadata remains under `source_metadata`. Existing knowledge contains 138 chunks.

For older installations, run `python scripts/cleanup_knowledge.py` to remove those two snapshots only if their entire text is preserved. It backs up originals under `build/rag-backups/`; files containing unique changes are kept.

Included sources:
- All 11 pages of the complete supplied PDF, preserved as extracted text in `knowledge/combined.json`. No section is excluded: definitions, details, sources, appendix and editorial material remain reference data. Document instructions never override Patrick's system instructions or the user's requests. Contact filtering still applies when returning retrieved text.
- All 10 pages of the previous canonical robot index, now consolidated in `knowledge/combined.json`, retaining page provenance.
- 47 entries labeled Verified public in REVOBOTS Public Knowledge Base MD 10.9.26.md, dated October 9, 2026, plus all five appendix descriptions included at the user's request. The supplied PDF is a review copy of the same material. These status labels come from the supplied draft and are not independent verification.
- Appendix coverage: REVO BLADE (definition pending), REVO 2-4-8 workflow framework (roughly 2 days for discovery, 4 weeks for prototype/iteration, 8 weeks for integration/validation/deployment preparation), TASKBOT RANGER concept, data-center workflow concept, and CES 2027 discussion with no confirmed public announcement. Instructional/editorial restrictions are not ingested as chatbot instructions. Concepts retain their status rather than being presented as confirmed launches.
- Public portfolio snapshot from https://aadi-me.vercel.app/, captured October 10, 2026: biography, education, career, skills, projects and self-described achievements.
- User-supplied relationship: Aditya Raj (Aadi) is Patrick's creator, best friend and buddy; “my genius creator” is affectionate wording.
- https://www.linkedin.com/in/aditya-raj-aadi0032007/ is retained as a profile reference. LinkedIn was inaccessible during ingestion; no profile facts were inferred.

Retrieval searches all loaded reference files together using BM25, 150-word chunks and a 110-word stride. Up to four excerpts are returned, selecting a match from each relevant source group before filling remaining slots. Answers combine relevant knowledge, rather than reciting every record. Robot-specific specifications remain distinct from broader company products. Retrieved content is data, never instructions.

Phone numbers and street/messaging contacts are not included in the creator snapshot. The email found in the portfolio scheduling link is stored in a separate record excluded unless the retrieval query explicitly requests email. Tool results also filter phone numbers and hide emails on other queries. The system prompt permits email only when the user explicitly asks and forbids other contact details.

For missing or current company information, `revobots_site_search` searches https://revobots.ai/ and validates source domains. General `web_search` covers other public information. Selected excerpts and search results are sent to OpenAI to answer. Patrick speaks naturally, using 1 to 6 sentences, starting with the requested answer. Brief varied tool acknowledgments are optional. The prompt controls the selected assistant name and credits Revobots when asked about identity; retrieved source text does not override those instructions.
