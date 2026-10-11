import spacy
import csv
import re
import json
import os
from collections import OrderedDict
from typing import Dict, List, Tuple, Optional

# Constants
DEFAULT_PRONOUNS = {
    "male": {"subject": "he", "object": "him", "possessive": "his", "reflexive": "himself"},
    "female": {"subject": "she", "object": "her", "possessive": "her", "reflexive": "herself"},
    "gender_fair": {"subject": "they", "object": "them", "possessive": "their", "reflexive": "themselves"}
}

GENDER_ADJECTIVES = {"male", "female", "lady", "gentlemen", "boy", "girl", "man", "woman", "ladies", }
GENDER_PAIRS = {
    ("girl", "boy"): ["children", "kids", "students", "youth", "young people"],
    ("son", "daughter"): ["children", "kids", "offspring"],
    ("woman", "man"): ["people", "individuals", "persons"],
    ("women", "men"): ["people", "individuals", "persons"],
    ("he", "she"): ["they"],
    ("his", "her"): ["their"],
    ("him", "her"): ["them"],
    ("himself", "herself"): ["themselves"],
    ("husband", "wife"): ["spouse", "partner"],
    ("boyfriend", "girlfriend"): ["partner"],
    ("brother", "sister"): ["sibling"],
    ("father", "mother"): ["parent"],
    ("uncle", "aunt"): ["relative"],
    ("nephew", "niece"): ["relative"],
    ("ladies", "gentlemen"): ["everyone", "all"]
}

nlp = spacy.load('en_core_web_sm')

class GenderFairLanguage:
    def __init__(self, terms_csv: str = 'gendered_terms.csv'):
        self.terms_csv = terms_csv
        self.gendered_terms = self._load_and_prioritize_terms(terms_csv)
        metadata_path = re.sub(r'\.csv$', '_metadata.json', terms_csv)
        try:
            with open(metadata_path, encoding='utf-8') as metadata_file:
                self.term_metadata = {key.lower(): value for key, value in json.load(metadata_file).items()}
        except (FileNotFoundError, json.JSONDecodeError):
            self.term_metadata = {}
        self._source_signature = self._get_source_signature()

    def _get_source_signature(self):
        metadata_path = re.sub(r'\.csv$', '_metadata.json', self.terms_csv)
        return tuple(os.path.getmtime(path) if os.path.exists(path) else None for path in (self.terms_csv, metadata_path))

    def refresh_terms_if_changed(self):
        signature = self._get_source_signature()
        if signature == self._source_signature:
            return
        self.gendered_terms = self._load_and_prioritize_terms(self.terms_csv)
        metadata_path = re.sub(r'\.csv$', '_metadata.json', self.terms_csv)
        try:
            with open(metadata_path, encoding='utf-8') as metadata_file:
                self.term_metadata = {key.lower(): value for key, value in json.load(metadata_file).items()}
        except (FileNotFoundError, json.JSONDecodeError):
            self.term_metadata = {}
        self._source_signature = signature
        
    def _load_and_prioritize_terms(self, csv_filename: str) -> OrderedDict:
        gendered_terms = OrderedDict()
        try:
            with open(csv_filename, 'r') as csvfile:
                reader = csv.reader(csvfile)
                for row in reader:
                    if len(row) >= 2:
                        term = row[0].strip().lower()
                        replacements = [repl.strip() for repl in row[1:] if repl.strip()]
                        if term and replacements:
                            gendered_terms[term] = replacements
        except Exception as e:
            raise ValueError(f"Error loading gendered terms: {e}")
            
        return OrderedDict(
            sorted(gendered_terms.items(), key=lambda item: len(item[0].split()), reverse=True)
        )

    @staticmethod
    def _adjust_capitalization(original: str, replacement: str) -> str:
        # Preserve replacement's casing if it has any uppercase letters
        if any(c.isupper() for c in replacement):
            return replacement
        if original.isupper():
            return replacement.upper()
        elif original.istitle():
            return replacement.capitalize()
        return replacement.lower()

    def _is_within_quotes(self, doc, start_idx: int, end_idx: int) -> bool:
        text = doc.text
        before = len(re.findall(r'(?<!\\)"', text[:start_idx]))
        after = len(re.findall(r'(?<!\\)"', text[end_idx:]))
        return (before % 2 == 1) and (after % 2 == 1)

    def _process_text_replacements(self, text: str, name_pronoun_map: Dict) -> Tuple[str, List[Dict]]:
        doc = nlp(text)
        TITLE_MAPPING = {
                        'mr': 'male',
                        'ms': 'female', 
                        'mrs': 'female', 
                        'mx': 'gender_fair',
                        'sir': 'male',
                        'madam': "female",
                         }
        i = 0
        while i < len(doc):
            token = doc[i]
            base_title = token.text.lower().rstrip('.')

            if base_title in TITLE_MAPPING:
                name_parts = [token.text]
                j = i + 1
                hyphen_buffer = None  # Track hyphens for merging

                while j < len(doc):
                    current_token = doc[j]
                    current_text = current_token.text

                    # Handle hyphen merging
                    if current_text == '-':
                        hyphen_buffer = current_text
                    elif hyphen_buffer and current_token.pos_ == 'PROPN':
                        # Merge hyphen with next word
                        name_parts.append(hyphen_buffer + current_text)
                        hyphen_buffer = None
                    elif current_token.pos_ == 'PROPN' or (current_text in ['-'] and not hyphen_buffer):
                        name_parts.append(current_text)
                    else:
                        break
                    
                    j += 1

                if len(name_parts) > 1:
                    # Clean and normalize names
                    full_name = self._normalize_hyphenated_name(' '.join(name_parts))
                    name_without_title = self._normalize_hyphenated_name(' '.join(name_parts[1:]))

                    category = TITLE_MAPPING[base_title]
                    name_pronoun_map[full_name.lower()] = category
                    name_pronoun_map[name_without_title.lower()] = category

                i = j - 1  # Skip processed tokens
            i += 1

        # Rest of processing remains
        corrections = []
        corrections.extend(self._find_gender_pairs(text, doc))
        corrections.extend(self._find_adjective_noun_pairs(text, doc))
        corrections.extend(self._find_individual_terms(text, doc))
        corrections.extend(self._find_pronoun_replacements(text, doc, name_pronoun_map))
        corrections.extend(self._find_possessive_constructions(text, doc)) 
        corrections = self._filter_overlapping_corrections(corrections)

        for correction in corrections:
            original = correction.get('original_text', '')
            term_info = self.term_metadata.get(original.lower(), {})
            correction['category'] = term_info.get('category', 'Gender-fair language')
            correction['rule_id'] = 'GFL_TERM_LIBRARY' if term_info else 'GFL_LANGUAGE_PATTERN'
            correction['message'] = term_info.get('guidance') or 'This wording may unnecessarily imply gender; consider a neutral alternative when gender is not relevant.'
            correction['rationale'] = correction['message']
            correction['examples'] = term_info.get('examples', [])

        revised_text = text
        for correction in sorted(corrections, key=lambda x: -x['character_offset']):
            replacement_str = correction['replacements'][0]
            revised_text = revised_text[:correction['character_offset']] + replacement_str + revised_text[correction['character_endset']:]

        return revised_text, corrections

    @staticmethod
    def _normalize_hyphenated_name(name: str) -> str:
        return re.sub(r'\s*-\s*', '-', name).strip()

    def _find_pronoun_replacements(self, text: str, doc, name_pronoun_map: Dict) -> List[Dict]:
        corrections = []
        name_to_category = {name.lower(): category for name, category in name_pronoun_map.items()}
        processed_names = set(name_to_category.keys())

        # Track all name variants from titles
        name_variants = []
        for name in processed_names:
            name_variants.extend([
                name,
                name.replace('-', ' '),  # "adam-silver" -> "adam silver"
                name.replace(' ', '-')    # "adam silver" -> "adam-silver"
            ])

        NEUTRAL_PRONOUNS = {"i", "me", "my", "mine", "myself",
                            "we", "us", "our", "ours", "ourselves",
                            "you", "your", "yours", "yourself", "yourselves",
                            "they", "them", "their", "theirs", "themselves", "it", "its", "itself"}

        for token in doc:
            if (token.tag_ in ["PRP", "PRP$"] and 
                token.text.lower() not in NEUTRAL_PRONOUNS and
                not self._is_within_quotes(doc, token.idx, token.idx + len(token.text))):

                # Find closest matching name in previous context
                referent = None
                lookback_window = doc[max(0, token.i-10):token.i]  # 10 tokens back
                for prev_token in reversed(lookback_window):
                    if prev_token.pos_ == 'PROPN':
                        candidate = self._normalize_hyphenated_name(prev_token.text).lower()
                        if candidate in processed_names:
                            referent = candidate
                            break
                        for variant in [candidate, candidate.replace('-', ' ')]:
                            if variant in name_to_category:
                                referent = variant
                                break
                        if referent:
                            break

                if not referent:
                    for ent in reversed(doc.ents):
                        if ent.end <= token.i and ent.label_ in ["PERSON", "ORG"]:
                            candidate = self._normalize_hyphenated_name(ent.text).lower()
                            if candidate in processed_names:
                                referent = candidate
                                break

                if referent:
                    category = name_to_category[referent]
                    role = self._get_pronoun_role(token)
                    new_pronoun = DEFAULT_PRONOUNS[category][role]
                else:
                    new_pronoun = DEFAULT_PRONOUNS["gender_fair"][self._get_pronoun_role(token)]

                # Apply capitalization and replacement
                new_pronoun = self._adjust_capitalization(token.text, new_pronoun)
                if new_pronoun != token.text:
                    corrections.append({
                        "word_index": token.i,
                        "original_text": token.text,
                        "replacements": [new_pronoun],
                        "character_offset": token.idx,
                        "character_endset": token.idx + len(token.text)
                    })

        return corrections

    def _get_pronoun_role(self, token) -> str:
        """Determine pronoun grammatical role."""
        if token.dep_ in ["nsubj", "nsubjpass"]:
            return "subject"
        if token.dep_ in ["dobj", "iobj", "pobj"]:
            return "object"
        if token.dep_ == "poss" or token.tag_ == "PRP$":
            return "possessive"
        if token.dep_ == "reflexive":
            return "reflexive"
        return "subject"  # Default fallback

    def _find_gender_pairs(self, text: str, doc) -> List[Dict]:
        """Find specific gender pairs to replace with more inclusive terms."""
        corrections = []

        for (term1, term2), replacements in GENDER_PAIRS.items():
             for t1, t2 in [(term1, term2), (term2, term1)]:
                term1_variants = [t1, t1 + 's', t1 + 'es']
                term2_variants = [t2, t2 + 's', t2 + 'es']

                for v1 in term1_variants:
                    for v2 in term2_variants:
                        pattern = rf'\b({v1})\s+(and|or)\s+({v2})\b'
                        matches = list(re.finditer(pattern, text, re.IGNORECASE))

                        for match in reversed(matches):
                            if self._is_within_quotes(doc, match.start(), match.end()):
                                continue

                            is_or = match.group(2).lower() == "or"

                            # Handle singular/plural for "or" cases
                            if is_or:
                                adjusted_replacements = []
                                for repl in replacements:
                                    if repl.endswith('s'):
                                        adjusted = repl[:-1]  # children -> child
                                    elif repl.endswith('es'):
                                        adjusted = repl[:-2]  # ladies -> lady
                                    else:
                                        adjusted = repl
                                    adjusted_replacements.append(adjusted)
                            else:
                                adjusted_replacements = replacements

                            first_word = match.group(1)
                            adjusted_replacements = [
                                self._adjust_capitalization(first_word, repl)
                                for repl in adjusted_replacements
                            ]

                            corrections.append({
                                "word_index": next((i for i, t in enumerate(doc) if t.idx <= match.start() < t.idx + len(t.text)), None),
                                "original_text": match.group(0),
                                "replacements": adjusted_replacements,
                                "character_offset": match.start(),
                                "character_endset": match.end()
                            })

        return corrections


    def _find_adjective_noun_pairs(self, text: str, doc) -> List[Dict]:
        corrections = []
        
        for i in range(len(doc) - 1):
            token = doc[i]
            next_token = doc[i + 1]
            
            if (token.text.lower() in GENDER_ADJECTIVES and 
                next_token.pos_ == "NOUN" and
                not self._is_within_quotes(doc, token.idx, next_token.idx + len(next_token.text))):
                
                noun_replacements = self.gendered_terms.get(next_token.text.lower(), [next_token.text])
                adjusted_replacements = [self._adjust_capitalization(next_token.text, repl) for repl in noun_replacements]
                
                corrections.append({
                    "word_index": i,
                    "original_text": f"{token.text} {next_token.text}",
                    "replacements": adjusted_replacements,
                    "character_offset": token.idx,
                    "character_endset": next_token.idx + len(next_token.text)
                })
        
        return corrections

    def _find_individual_terms(self, text: str, doc) -> List[Dict]:
        corrections = []
        
        for term, replacements_list in self.gendered_terms.items():
            pattern = rf'\b{re.escape(term)}\b'  # Handles multi-word terms
            matches = list(re.finditer(pattern, text, re.IGNORECASE))
            
            for match in reversed(matches):
                if self._is_within_quotes(doc, match.start(), match.end()):
                    continue
                
                original_text = match.group(0)
                # Filter out identical replacements
                unique_replacements = [
                    repl for repl in replacements_list 
                    if repl.lower() != original_text.lower()
                ]
                
                if not unique_replacements:
                    continue  # Skip if no actual replacements
                    
                adjusted_replacements = [
                    self._adjust_capitalization(original_text, repl) 
                    for repl in unique_replacements
                ]
                
                corrections.append({
                    "word_index": next((i for i, t in enumerate(doc) if t.idx <= match.start() < t.idx + len(t.text)), None),
                    "original_text": original_text,
                    "replacements": adjusted_replacements,
                    "character_offset": match.start(),
                    "character_endset": match.end()
                })
        
        return corrections

    def _find_pronoun_replacements(self, text: str, doc, name_pronoun_map: Dict) -> List[Dict]:
        corrections = []
        # Normalize all keys in the pronoun map to lowercase
        name_to_category = {name.lower(): category for name, category in name_pronoun_map.items()}
        processed_names = set(name_to_category.keys())

        # Track all name variants from titles
        name_variants = []
        for name in processed_names:
            name_variants.extend([
                name,
                name.replace('-', ' '),  # "adam-silver" -> "adam silver"
                name.replace(' ', '-')    # "adam silver" -> "adam-silver"
            ])

        NEUTRAL_PRONOUNS = {"i", "me", "my", "mine", "myself",
                            "we", "us", "our", "ours", "ourselves",
                            "you", "your", "yours", "yourself", "yourselves",
                            "they", "them", "their", "theirs", "themselves", "it", "its", "itself", "'s"}

        for token in doc:
            if (token.tag_ in ["PRP", "PRP$"] and 
                token.text.lower() not in NEUTRAL_PRONOUNS and
                not self._is_within_quotes(doc, token.idx, token.idx + len(token.text))):

                # Find closest matching name in previous context (case-insensitive)
                referent = None
                lookback_window = doc[max(0, token.i-10):token.i]  # 10 tokens back
                for prev_token in reversed(lookback_window):
                    if prev_token.pos_ == 'PROPN':
                        candidate = self._normalize_hyphenated_name(prev_token.text).lower()
                        if candidate in processed_names:
                            referent = candidate
                            break
                        for variant in [candidate, candidate.replace('-', ' ')]:
                            if variant in name_to_category:
                                referent = variant
                                break
                        if referent:
                            break

                if not referent:
                    for ent in reversed(doc.ents):
                        if ent.end <= token.i and ent.label_ in ["PERSON", "ORG"]:
                            candidate = self._normalize_hyphenated_name(ent.text).lower()
                            if candidate in processed_names:
                                referent = candidate
                                break

                if referent:
                    category = name_to_category.get(referent, None)
                    if not category:
                        category = "gender_fair"
                    role = self._get_pronoun_role(token)
                    new_pronoun = DEFAULT_PRONOUNS[category][role]
                else:
                    new_pronoun = DEFAULT_PRONOUNS["gender_fair"][self._get_pronoun_role(token)]

                # Apply capitalization and replacement
                new_pronoun = self._adjust_capitalization(token.text, new_pronoun)
                if new_pronoun != token.text:
                    corrections.append({
                        "word_index": token.i,
                        "original_text": token.text,
                        "replacements": [new_pronoun],
                        "character_offset": token.idx,
                        "character_endset": token.idx + len(token.text)
                    })

        return corrections
    
    def _find_possessive_constructions(self, text: str, doc) -> List[Dict]:
        corrections = []
        for token in doc:
            if token.text.lower() in GENDER_ADJECTIVES:
                # Check for possessive constructions
                case_children = [
                    child for child in token.children 
                    if child.dep_ == 'case' 
                    and re.match(r"^['’]s?$", child.text.lower())
                ]
                if case_children:
                    possessive_marker = case_children[0]
                    start = token.idx
                    end = possessive_marker.idx + len(possessive_marker.text)
                    
                    if end < len(text) and text[end] == ' ':
                        end += 1
                    
                    if self._is_within_quotes(doc, start, end):
                        continue
                    
                    # Create replacement entry
                    original_span = text[start:end]
                    corrections.append({
                        "word_index": token.i,
                        "original_text": original_span,
                        "replacements": [""],
                        "character_offset": start,
                        "character_endset": end
                    })
        return corrections

    def _filter_overlapping_corrections(self, corrections: List[Dict]) -> List[Dict]:
        if not corrections:
            return []
            
        sorted_corrections = sorted(corrections, key=lambda x: (x['character_offset'], -x['character_endset']))
        filtered = []
        last_end = -1
        
        for c in sorted_corrections:
            if c['character_offset'] >= last_end:
                filtered.append(c)
                last_end = c['character_endset']
        
        return filtered

    def process_text(self, text: str, name_pronoun_map: Optional[Dict] = None) -> Dict:
        if not text or not isinstance(text, str):
            raise ValueError("Input text must be a non-empty string")
            
        revised_text, corrections = self._process_text_replacements(text, name_pronoun_map or {})
        
        return {
            "original_text": text,
            "revised_text": revised_text,
            "corrections": sorted([
                c for c in corrections if c['character_offset'] >= 0
            ], key=lambda x: x['character_offset'])
        }

def load_gfl(csv_path: str = 'gendered_terms.csv') -> GenderFairLanguage:
    return GenderFairLanguage(csv_path)
