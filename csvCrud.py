# term_manager.py
from dataclasses import dataclass
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
    examples: List[str] = None


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
                    extra = metadata.get(term, {})
                    terms.append(GenderTerm(term, [opt.strip() for opt in row[1:] if opt.strip()], extra.get("category", "Other"), extra.get("guidance", ""), extra.get("examples", [])))
        return terms

    def save(self, terms: List[GenderTerm]):
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for entry in terms:
                writer.writerow([entry.term, *entry.options])

    def create(self, term: str, options: List[str], category: str = "Other", guidance: str = "", examples: Optional[List[str]] = None):
        all_terms = self.load()
        if any(entry.term == term for entry in all_terms):
            raise ValueError(f"Term '{term}' already exists.")
            # update existing term instead
        all_terms.append(GenderTerm(term, options, category, guidance, examples or []))
        self.save(all_terms)
        metadata = self._metadata()
        metadata[term] = {"category": category, "guidance": guidance, "examples": examples or []}
        self._save_metadata(metadata)

    def find_term(self, term: str) -> Optional[Dict[str, List[str]]]:
        for entry in self.load():
            if entry.term == term:
                return {entry.term: entry.options}
        return None

    def update(self, term: str, new_options: List[str], category: Optional[str] = None, guidance: Optional[str] = None, examples: Optional[List[str]] = None):
        terms = self.load()
        for entry in terms:
            if entry.term == term:
                entry.options = new_options
                self.save(terms)
                metadata = self._metadata()
                current = metadata.get(term, {})
                if category is not None: current["category"] = category
                if guidance is not None: current["guidance"] = guidance
                if examples is not None: current["examples"] = examples
                metadata[term] = current
                self._save_metadata(metadata)
                return
        raise KeyError(f"Term '{term}' not found.")

    def delete(self, term: str):
        terms = self.load()
        new_terms = [entry for entry in terms if entry.term != term]
        if len(new_terms) == len(terms):
            raise KeyError(f"Term '{term}' not found.")
        self.save(new_terms)
        metadata = self._metadata()
        metadata.pop(term, None)
        self._save_metadata(metadata)

    def get_all_term(self) -> Dict[str, List[str]]:
        return {entry.term: entry.options for entry in self.load()}

    def get_all_records(self) -> List[dict]:
        return [{"term": e.term, "options": e.options, "category": e.category, "guidance": e.guidance, "examples": e.examples or []} for e in self.load()]
