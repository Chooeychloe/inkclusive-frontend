# term_manager.py
from dataclasses import dataclass, field
from typing import List, Optional, Dict
import csv
import json
import os


@dataclass
class GenderTerm:
    term: str
    options: List[str]
    category: str = "Other"
    guidance: str = ""
    examples: List[str] = field(default_factory=list)


class GenderTermManager:
    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self.metadata_path = os.path.splitext(csv_path)[0] + "_metadata.json"

    def _metadata(self) -> Dict[str, dict]:
        try:
            with open(self.metadata_path, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_metadata(self, metadata: Dict[str, dict]):
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def load(self) -> List[GenderTerm]:
        terms = []
        metadata = self._metadata()
        with open(self.csv_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if row:
                    term = row[0].strip()
                    extra = metadata.get(term, metadata.get(term.casefold(), {}))
                    terms.append(GenderTerm(term, [opt.strip() for opt in row[1:] if opt.strip()], extra.get("category", "Other"), extra.get("guidance", ""), extra.get("examples", [])))
        return terms

    def save(self, terms: List[GenderTerm]):
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for entry in terms:
                writer.writerow([entry.term, *entry.options])

    def create(self, term: str, options: List[str], category: str = "Other", guidance: str = "", examples: Optional[List[str]] = None):
        term = term.strip()
        all_terms = self.load()
        if any(entry.term.casefold() == term.casefold() for entry in all_terms):
            raise ValueError(f"Term '{term}' already exists.")
            # update existing term instead
        all_terms.append(GenderTerm(term, options, category, guidance, examples or []))
        self.save(all_terms)
        metadata = self._metadata()
        metadata[term] = {"category": category, "guidance": guidance, "examples": examples or []}
        self._save_metadata(metadata)

    def create_many(self, entries: List[GenderTerm]):
        existing = self.load()
        known = {entry.term.casefold() for entry in existing}
        incoming = set()
        for entry in entries:
            entry.term = entry.term.strip()
            normalized = entry.term.casefold()
            if normalized in known or normalized in incoming:
                raise ValueError(f"Term '{entry.term}' already exists.")
            incoming.add(normalized)

        self.save(existing + entries)
        metadata = self._metadata()
        for entry in entries:
            metadata[entry.term] = {
                "category": entry.category,
                "guidance": entry.guidance,
                "examples": entry.examples,
            }
        self._save_metadata(metadata)

    def find_term(self, term: str) -> Optional[Dict[str, List[str]]]:
        for entry in self.load():
            if entry.term.casefold() == term.casefold():
                return {entry.term: entry.options}
        return None

    def find_record(self, term: str) -> Optional[dict]:
        normalized = term.casefold()
        for entry in self.get_all_records():
            if entry["term"].casefold() == normalized:
                return entry
        return None

    def update(self, term: str, new_options: List[str], category: Optional[str] = None, guidance: Optional[str] = None, examples: Optional[List[str]] = None):
        terms = self.load()
        for entry in terms:
            if entry.term.casefold() == term.casefold():
                entry.options = new_options
                self.save(terms)
                metadata = self._metadata()
                current = metadata.get(entry.term, {})
                if category is not None: current["category"] = category
                if guidance is not None: current["guidance"] = guidance
                if examples is not None: current["examples"] = examples
                metadata[entry.term] = current
                self._save_metadata(metadata)
                return
        raise KeyError(f"Term '{term}' not found.")

    def delete(self, term: str):
        terms = self.load()
        new_terms = [entry for entry in terms if entry.term.casefold() != term.casefold()]
        if len(new_terms) == len(terms):
            raise KeyError(f"Term '{term}' not found.")
        self.save(new_terms)
        metadata = self._metadata()
        for key in list(metadata):
            if key.casefold() == term.casefold():
                metadata.pop(key, None)
        self._save_metadata(metadata)

    def delete_many(self, terms_to_delete: List[str]) -> int:
        requested = {term.strip().casefold() for term in terms_to_delete if term.strip()}
        terms = self.load()
        remaining = [entry for entry in terms if entry.term.casefold() not in requested]
        deleted = len(terms) - len(remaining)
        if deleted != len(requested):
            missing = requested - {entry.term.casefold() for entry in terms}
            raise KeyError(f"Terms not found: {', '.join(sorted(missing))}")
        self.save(remaining)
        metadata = self._metadata()
        for key in list(metadata):
            if key.casefold() in requested:
                metadata.pop(key, None)
        self._save_metadata(metadata)
        return deleted

    def get_all_term(self) -> Dict[str, List[str]]:
        return {entry.term: entry.options for entry in self.load()}

    def get_all_records(self) -> List[dict]:
        return [{"term": e.term, "options": e.options, "category": e.category, "guidance": e.guidance, "examples": e.examples or []} for e in self.load()]
