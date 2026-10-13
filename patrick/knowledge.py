"""Small local BM25 reference retriever; no model downloads or external requests."""
from collections import Counter
import json
import math
from pathlib import Path
import re
from .identity import render_identity
from .knowledge_files import load_records, canonical

STOP = set("a an the is are was were what who how many much your you my me i it of for to in on and do does can have has tell about please this that with as from".split())


def tokens(text):
    return [word for word in re.findall(r"[^\W_]+", text.lower()) if word not in STOP]


def email_requested(query):
    return bool(re.search(r'\b(?:email|e-mail|mail)\b|ईमेल|メール', query, re.I))


def contact_filter(value, allow_email=False):
    if isinstance(value, dict):
        return {key: contact_filter(item, allow_email) for key, item in value.items()}
    if isinstance(value, list):
        return [contact_filter(item, allow_email) for item in value]
    if not isinstance(value, str):
        return value
    value = re.sub(r'(?<!\w)\+?\d[\d ()\-]{7,}\d(?!\w)',
                   lambda m: '[contact omitted]' if len(re.sub(r'\D', '', m.group())) >= 10 else m.group(), value)
    if not allow_email:
        value = re.sub(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}', '[email omitted]', value)
    return value


class KnowledgeBase:
    def __init__(self, path, name="patrick"):
        records, self.files = load_records(path)
        self.name = name.strip().title()
        self.source = f'{self.name} knowledge folder: {len(self.files)} files' if Path(path).is_dir() else render_identity(
            records[0].get('collection', records[0]['source']), self.name)
        self.chunks = []
        self.metadata = []
        self.duplicate_records = self.duplicate_chunks = 0
        unique = {}
        for page in records:
            key = (canonical(page['text']), page.get('contact'))
            reference = {k: v for k, v in page.items() if k != 'text'}
            if key in unique:
                self.duplicate_records += 1
                if reference not in unique[key]['references']:
                    unique[key]['references'].append(reference)
            else:
                unique[key] = {**page, 'references': [reference]}
        chunk_keys = {}
        for page in unique.values():
            text = page["text"]
            text = render_identity(text, self.name)
            words = text.split()
            for start in range(0, len(words), 110):
                chunk = " ".join(words[start:start + 150])
                if chunk:
                    meta = {key: value for key, value in page.items() if key != 'text'}
                    key = (canonical(chunk), page.get('contact'))
                    if key in chunk_keys:
                        self.duplicate_chunks += 1
                        previous = self.metadata[chunk_keys[key]]
                        for reference in meta['references']:
                            if reference not in previous['references']:
                                previous['references'].append(reference)
                        continue
                    chunk_keys[key] = len(self.chunks)
                    self.chunks.append((page.get("page"), chunk, Counter(tokens(chunk))))
                    self.metadata.append(meta)
        self.df = Counter(word for _, _, counts in self.chunks for word in counts)
        self.average = sum(sum(c.values()) for _, _, c in self.chunks) / max(1, len(self.chunks))

    def retrieve(self, query, limit=4):
        terms = set(tokens(query))
        ranked = []
        for index, (page, text, counts) in enumerate(self.chunks):
            meta = self.metadata[index]
            if meta.get('contact') == 'email' and not email_requested(query):
                continue
            length = sum(counts.values())
            score = 0.0
            for word in terms:
                frequency = counts[word]
                if frequency:
                    idf = math.log(1 + (len(self.chunks) - self.df[word] + .5) / (self.df[word] + .5))
                    score += idf * frequency * 2.2 / (frequency + 1.2 * (.25 + .75 * length / self.average))
            if score:
                ranked.append((score, index, text))
        ranked.sort(key=lambda item: item[0], reverse=True)
        selected = []
        groups = set()
        # Include each relevant source group before filling with highest-ranked matches.
        for item in ranked:
            group = self.metadata[item[1]].get('group', 'robot')
            if group not in groups and len(selected) < limit:
                selected.append(item)
                groups.add(group)
        for item in ranked:
            if len(selected) >= limit:
                break
            if item not in selected:
                selected.append(item)
        return [contact_filter({**self.metadata[index], "text": text}, email_requested(query))
                for _, index, text in selected]


class KnowledgeTools:
    """Let the LLM translate retrieval keywords without sending private RAG to the web."""
    def __init__(self, knowledge, other=None):
        self.knowledge, self.other = knowledge, other
        self.schemas = list(getattr(other, "schemas", [])) + [{
            "type": "function", "function": {
                "name": "knowledge_search",
                "description": "Search local robot, Revobots company and Aditya biography knowledge. Use focused English keywords; respond in the user's language.",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}},
                               "required": ["query"], "additionalProperties": False},
            }}]

    def execute(self, name, arguments, cancelled, register_stream=lambda stream: None):
        if name != "knowledge_search":
            if self.other:
                return self.other.execute(name, arguments, cancelled, register_stream)
            return {"error": "Unknown tool"}
        if cancelled.is_set():
            return {"error": "Knowledge search cancelled"}
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
            if not isinstance(args, dict) or set(args) != {"query"}:
                raise ValueError()
            query = args["query"]
            if not isinstance(query, str) or not 1 <= len(query.strip()) <= 500:
                raise ValueError()
        except (ValueError, TypeError):
            return {"error": "knowledge_search requires one query string of 1-500 characters"}
        return {"excerpts": self.knowledge.retrieve(query), "source": self.knowledge.source}
