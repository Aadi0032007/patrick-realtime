# Patrick RAG details

Default index: `knowledge/combined.json`. Restart Patrick after updating the index.

Included sources:
- All 11 pages of the complete supplied PDF, stored verbatim as extracted text in `knowledge/revobots-full-pdf.json` and indexed in `knowledge/combined.json`. No section is excluded: definitions, details, sources, appendix and editorial material remain reference data. Document instructions never override Patrick's system instructions or the user's requests. Contact filtering still applies when returning retrieved text.
- All 10 pages of the previous canonical robot index (`knowledge/revobots.json`), retaining page provenance.
- 47 entries labeled Verified public in REVOBOTS Public Knowledge Base MD 10.9.26.md, dated October 9, 2026, plus all five appendix descriptions included at the user's request. The supplied PDF is a review copy of the same material. These status labels come from the supplied draft and are not independent verification.
- Appendix coverage: REVO BLADE (definition pending), REVO 2-4-8 workflow framework (roughly 2 days for discovery, 4 weeks for prototype/iteration, 8 weeks for integration/validation/deployment preparation), TASKBOT RANGER concept, data-center workflow concept, and CES 2027 discussion with no confirmed public announcement. Instructional/editorial restrictions are not ingested as chatbot instructions. Concepts retain their status rather than being presented as confirmed launches.
- Public portfolio snapshot from https://aadi-me.vercel.app/, captured October 10, 2026: biography, education, career, skills, projects and self-described achievements.
- User-supplied relationship: Aditya Raj (Aadi) is Patrick's creator, best friend and buddy; “my genius creator” is affectionate wording.
- https://www.linkedin.com/in/aditya-raj-aadi0032007/ is retained as a profile reference. LinkedIn was inaccessible during ingestion; no profile facts were inferred.

Retrieval searches the combined index using BM25, 150-word chunks and a 110-word stride. Up to four excerpts are returned, selecting a match from each relevant source group before filling remaining slots. Answers combine relevant knowledge, rather than reciting every record. Robot-specific specifications remain distinct from broader company products. Retrieved content is data, never instructions.

Phone numbers and street/messaging contacts are not included in the creator snapshot. The email found in the portfolio scheduling link is stored in a separate record excluded unless the retrieval query explicitly requests email. Tool results also filter phone numbers and hide emails on other queries. The system prompt permits email only when the user explicitly asks and forbids other contact details.

For missing or current company information, `revobots_site_search` searches https://revobots.ai/ and validates source domains. General `web_search` covers other public information. Selected excerpts and search results are sent to OpenAI to answer. Patrick speaks naturally, using 1 to 6 sentences, starting with the requested answer without introductions, thinking aloud, or permission commentary. His identity and creator relationship are mentioned only when asked or directly relevant.
