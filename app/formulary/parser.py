"""Text Parsing Module for Formulary Data Extraction.

Extracts drug information using:
1. Pattern matching (regex) - Fast, handles well-formatted data
2. LLM enhancement - Handles edge cases and complex formats
"""

import re
import json
from typing import List, Dict, Any, Optional, Tuple
from loguru import logger

from app.formulary.models import (
    Drug, 
    DrugType, 
    RESTRICTION_MAP, 
    RESTRICTION_DESCRIPTIONS,
)


class FormularyParser:
    """Parser for extracting drug data from formulary text."""

    @staticmethod
    def _normalize_extracted_drug_name(name: str) -> str:
        """
        Fix OCR/Gemini artifact where a line break is merged into a leading 'n'
        before TitleCase names (e.g. nEtodolac, nFlurbiprofen -> Etodolac).
        Leaves names like nitroglycerin unchanged (n followed by lowercase).
        """
        name = name.strip()
        if len(name) >= 3 and name[0] == "n" and name[1].isupper():
            return name[1:].lstrip()
        return name
    
    # Pattern for drug entries:
    # <Drug Name> (<Form>) [B|G] <Tier> <Restrictions>
    # Examples:
    # "Lipitor (Oral Tablet) B 2 PA, QL"
    # "Metformin (Oral Tablet) G 1"
    # "Ibrance (Oral Capsule) B 5 PA DL QL"
    
    # All known restriction codes from UHC formulary
    RESTRICTION_CODES = r'PA|QL|ST|DL|SP|LA|AR|GR|B/D|MME|7D'
    
    DRUG_PATTERNS = [
        # Pattern 1 (PRIMARY): UHC Format with REQUIRED form in parentheses
        # This is the most reliable pattern - almost all real drugs have form info
        # Examples: "Cefaclor (Oral Capsule) G 3"
        #           "BRIVIACT (Oral Solution) B 4 PA; DL; QL"
        #           "Donepezil HCl (10MG Oral Tablet, 5MG Oral Tablet) G 1 QL"
        re.compile(
            r'(?P<drug_name>[A-Za-z][A-Za-z0-9\-\s\.]+?)\s*'
            r'\((?P<form>[^)]+)\)\s*'
            r'(?P<type>[BG])\s+'
            r'(?P<tier>[1-6])\s*'
            r'(?P<restrictions>(?:' + RESTRICTION_CODES + r')(?:\s*[,;]?\s*(?:' + RESTRICTION_CODES + r'))*)?',
            re.IGNORECASE | re.MULTILINE
        ),
        
        # Pattern 2: Multiline form - handles entries where form spans multiple lines
        # Drug Name (first part of form,
        # more details here) G/B Tier Restrictions
        re.compile(
            r'(?P<drug_name>[A-Za-z][A-Za-z0-9\-\s\.]+?)\s*'
            r'\((?P<form>[^)]+)\)\s*\n?\s*'
            r'(?P<type>[BG])\s+'
            r'(?P<tier>[1-6])\s*'
            r'(?P<restrictions>(?:' + RESTRICTION_CODES + r')(?:\s*[,;]?\s*(?:' + RESTRICTION_CODES + r'))*)?',
            re.IGNORECASE | re.MULTILINE
        ),
        
        # Pattern 3 (FALLBACK): Without form - ONLY for known drug name patterns
        # Very strict: Only matches if drug name looks like a real drug
        # Must end with common drug suffixes or contain chemical indicators
        re.compile(
            r'^(?P<drug_name>[A-Za-z][a-z]+'  # Start with capital, then lowercase
            r'(?:in|ol|ide|ate|ine|one|an|il|ax|ir|ar|en|ex|ix|um|ib|ab|ub|mab|nib|vir|pam|lam|zole|pine|done|zine|triptan|sartan|pril|olol|dipine|statin|cycline|mycin|floxacin|azole|conazole)?'  # Drug suffixes
            r'(?:\s+(?:HCl|Sodium|Potassium|Calcium|Sulfate|Acetate|Mesylate|Maleate|Tartrate|Fumarate|ER|XR|SR|ODT|DR))?)\s+'  # Optional salt forms
            r'(?P<type>[BG])\s+'
            r'(?P<tier>[1-6])\s*'
            r'(?P<restrictions>(?:' + RESTRICTION_CODES + r')(?:\s*[,;]?\s*(?:' + RESTRICTION_CODES + r'))*)?$',
            re.IGNORECASE | re.MULTILINE
        ),
    ]
    
    # Restriction pattern - all known codes
    RESTRICTION_PATTERN = re.compile(r'\b(PA|QL|ST|DL|SP|LA|AR|GR|B/D|MME|7D)\b', re.IGNORECASE)
    
    def __init__(self, llm_client=None):
        """
        Initialize parser.
        
        Args:
            llm_client: Optional LLM client for enhanced parsing
        """
        self.llm_client = llm_client
    
    def parse(self, text: str, use_llm: bool = False) -> List[Drug]:
        """
        Parse formulary text and extract drugs.
        
        Args:
            text: Raw text from PDF
            use_llm: Whether to use LLM for difficult extractions
            
        Returns:
            List of Drug objects
        """
        logger.info("Starting formulary parsing...")
        
        # Step 1: Preprocess text
        processed_text = self._preprocess(text)
        
        # Step 2: Try pattern matching first (fast)
        drugs = self._pattern_extract(processed_text)
        logger.info(f"Pattern matching extracted {len(drugs)} drugs")
        
        # Step 3: Line-by-line parsing for missed entries
        existing_keys = {self._drug_identity_key(d) for d in drugs}
        additional_drugs = self._line_by_line_parse(processed_text, existing_keys)
        drugs.extend(additional_drugs)
        logger.info(f"Line parsing found {len(additional_drugs)} additional drugs")
        
        # Step 4: LLM enhancement for complex entries (optional)
        if use_llm and self.llm_client:
            # This would be implemented with async LLM call
            pass
        
        # Step 5: Deduplicate
        drugs = self._deduplicate(drugs)
        logger.info(f"After deduplication: {len(drugs)} drugs")
        
        # Step 6: Final validation pass - remove any remaining bad entries
        validated_drugs = []
        rejected_count = 0
        for drug in drugs:
            if self._final_validation(drug):
                validated_drugs.append(drug)
            else:
                rejected_count += 1
                logger.debug(f"Final validation rejected: {drug.drug_name}")
        
        if rejected_count > 0:
            logger.info(f"Final validation removed {rejected_count} invalid entries")
        
        logger.info(f"Final count: {len(validated_drugs)} drugs")
        
        return validated_drugs
    
    def _preprocess(self, text: str) -> str:
        """Preprocess text for better pattern matching."""
        # Normalize whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        
        # =============================================
        # CRITICAL: Remove category markers and headers
        # =============================================
        
        # Remove standalone category markers (A1, B1, C1 on their own lines)
        text = re.sub(r'^[ABC][0-9]\s*$', '', text, flags=re.MULTILINE)
        
        # Remove category markers at start of lines (but keep drug info after)
        # e.g., "A1 Anesthetics" -> removed, but "Lidocaine (Oral) G 2" -> kept
        text = re.sub(r'^[ABC][0-9]\s+(?![A-Za-z]+\s*\()', '', text, flags=re.MULTILINE)
        
        # Remove lines that are just category headers (no drug info)
        # These typically don't have parentheses and are short
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            line_stripped = line.strip()
            # Skip empty lines
            if not line_stripped:
                cleaned_lines.append(line)
                continue
            # Skip pure category headers (no parentheses, no B/G tier pattern)
            if '(' not in line_stripped and not re.search(r'[BG]\s+[1-6]', line_stripped, re.IGNORECASE):
                # Check if it looks like a category
                if re.match(r'^[A-Za-z\-\s,]+$', line_stripped) and len(line_stripped) < 50:
                    continue  # Skip this category header
            cleaned_lines.append(line)
        text = '\n'.join(cleaned_lines)
        
        # =============================================
        # Standard normalization
        # =============================================
        
        # Normalize restriction codes (handle variations)
        text = re.sub(r'\bP\.?A\.?\b', 'PA', text, flags=re.IGNORECASE)
        text = re.sub(r'\bQ\.?L\.?\b', 'QL', text, flags=re.IGNORECASE)
        text = re.sub(r'\bS\.?T\.?\b', 'ST', text, flags=re.IGNORECASE)
        text = re.sub(r'\bD\.?L\.?\b', 'DL', text, flags=re.IGNORECASE)
        
        # Normalize type indicators
        text = re.sub(r'\bBrand\b', 'B', text, flags=re.IGNORECASE)
        text = re.sub(r'\bGeneric\b', 'G', text, flags=re.IGNORECASE)
        
        return text
    
    def _pattern_extract(self, text: str) -> List[Drug]:
        """Extract drugs using regex patterns."""
        drugs = []
        
        for pattern in self.DRUG_PATTERNS:
            matches = pattern.finditer(text)
            
            for match in matches:
                try:
                    drug = self._match_to_drug(match)
                    if drug and self._validate_drug(drug):
                        drugs.append(drug)
                except Exception as e:
                    logger.debug(f"Failed to parse match: {e}")
        
        return drugs
    
    def _line_by_line_parse(self, text: str, existing_keys: set) -> List[Drug]:
        """Parse text line by line for entries missed by patterns."""
        drugs = []
        lines = text.split('\n')
        
        # Buffer for multiline entries (drug name + form can span lines)
        buffer = ""
        
        for line in lines:
            line = line.strip()
            if not line:
                buffer = ""  # Reset on empty line
                continue
            
            # Skip obvious category headers and markers
            if re.match(r'^[ABC][0-9]\s', line):  # Starts with A1, B1, C1
                buffer = ""
                continue
            if re.search(r'\b[ABC][0-9]\b', line) and '(' not in line:  # Contains markers, no form
                buffer = ""
                continue
            
            # Check if this line looks like a complete drug entry
            # Must have: (Form details) followed by G/B and tier
            if re.search(r'\([^)]+\)\s*[BG]\s+[1-6]', line, re.IGNORECASE):
                # This line has form + type + tier - parse it
                text_to_parse = (buffer + " " + line).strip() if buffer else line
                drug = self._parse_single_line(text_to_parse)
                if drug:
                    key = self._drug_identity_key(drug)
                    if key not in existing_keys and self._validate_drug(drug):
                        drugs.append(drug)
                        existing_keys.add(key)
                buffer = ""
            elif re.search(r'^[A-Za-z][A-Za-z0-9\-\s\.]+\s*\(', line) and not buffer:
                # Line starts with drug name and opening parenthesis - might continue
                buffer = line
            elif buffer and ')' in line:
                # Continue buffer and try to complete
                buffer += " " + line
                if re.search(r'\)\s*[BG]\s+[1-6]', buffer, re.IGNORECASE):
                    drug = self._parse_single_line(buffer)
                    if drug:
                        key = self._drug_identity_key(drug)
                        if key not in existing_keys and self._validate_drug(drug):
                            drugs.append(drug)
                            existing_keys.add(key)
                    buffer = ""
            elif buffer:
                buffer += " " + line
                # Reset if buffer gets too long
                if len(buffer) > 300:
                    buffer = ""
            else:
                buffer = ""
        
        return drugs
    
    def _parse_single_line(self, line: str) -> Optional[Drug]:
        """Parse a single line into a Drug object."""
        # Try each pattern
        for pattern in self.DRUG_PATTERNS:
            match = pattern.search(line)
            if match:
                return self._match_to_drug(match, raw_text=line)
        
        # Fallback: Simple extraction
        return self._simple_extract(line)
    
    def _simple_extract(self, text: str) -> Optional[Drug]:
        """
        Simple extraction for lines that don't match main patterns.
        STRICT: Only extracts if form is present (high confidence).
        """
        # PRIORITY: Look for format WITH parentheses (form info)
        # This is the reliable format: Drug Name (Form) G/B Tier Restrictions
        match = re.search(
            r'([A-Za-z][A-Za-z0-9\-\s\.]+?)\s*\(([^)]+)\)\s*([BG])\s+([1-6])\s*((?:PA|QL|ST|DL|SP|LA|AR|GR|B/D|MME|7D|\s|,|;)*)',
            text,
            re.IGNORECASE
        )
        
        if match:
            drug_name = self._normalize_extracted_drug_name(match.group(1).strip())
            form = match.group(2).strip()
            drug_type = match.group(3).upper()
            tier = int(match.group(4))
            restrictions_str = match.group(5) if match.group(5) else ""
            
            # Parse restrictions
            restrictions = self._extract_restrictions(restrictions_str)
            
            return Drug(
                drug_name=drug_name,
                form=form,
                type=DrugType.BRAND if drug_type == 'B' else DrugType.GENERIC,
                tier=tier,
                restrictions=restrictions,
                restriction_details=[RESTRICTION_DESCRIPTIONS.get(r, r) for r in restrictions],
                raw_text=text,
            )
        
        # FALLBACK: Without form - ONLY if drug name looks legitimate
        # Skip this for entries that look like category headers
        match = re.search(
            r'^([A-Za-z][a-z]+(?:in|ol|ide|ate|ine|one|mab|nib|vir)?(?:\s+(?:HCl|Sodium|Calcium))?)\s+([BG])\s+([1-6])\s*(.*?)$',
            text,
            re.IGNORECASE
        )
        
        if match:
            drug_name = self._normalize_extracted_drug_name(match.group(1).strip())
            drug_type = match.group(2).upper()
            tier = int(match.group(3))
            restrictions_str = match.group(4) if match.group(4) else ""
            
            # Extra validation: reject if name contains category markers
            if re.search(r'\b[ABC][0-9]\b|Agents|Inhibitors|Anesthetics', drug_name, re.IGNORECASE):
                return None
            
            restrictions = self._extract_restrictions(restrictions_str)
            
            return Drug(
                drug_name=drug_name,
                form=None,
                type=DrugType.BRAND if drug_type == 'B' else DrugType.GENERIC,
                tier=tier,
                restrictions=restrictions,
                restriction_details=[RESTRICTION_DESCRIPTIONS.get(r, r) for r in restrictions],
                raw_text=text,
            )
        
        return None
    
    def _match_to_drug(self, match: re.Match, raw_text: str = None) -> Optional[Drug]:
        """Convert regex match to Drug object."""
        groups = match.groupdict()
        
        drug_name = self._normalize_extracted_drug_name(groups.get('drug_name', '').strip())
        if not drug_name or len(drug_name) < 2:
            return None
        
        # Parse type
        type_str = groups.get('type', '').upper()
        if type_str in ('B', 'BRAND'):
            drug_type = DrugType.BRAND
        elif type_str in ('G', 'GENERIC'):
            drug_type = DrugType.GENERIC
        else:
            drug_type = DrugType.UNKNOWN
        
        # Parse tier
        try:
            tier = int(groups.get('tier', 1))
            tier = max(1, min(6, tier))  # Clamp to 1-6
        except (ValueError, TypeError):
            tier = 1
        
        # Parse restrictions
        restrictions_str = groups.get('restrictions', '') or ''
        restrictions = self._extract_restrictions(restrictions_str)
        
        # Parse form
        form = groups.get('form', '').strip() if groups.get('form') else None
        
        return Drug(
            drug_name=drug_name,
            form=form,
            type=drug_type,
            tier=tier,
            restrictions=restrictions,
            restriction_details=[RESTRICTION_DESCRIPTIONS.get(r, r) for r in restrictions],
            raw_text=raw_text or match.group(0),
        )
    
    def _extract_restrictions(self, text: str) -> List[str]:
        """Extract restriction codes from text."""
        if not text:
            return []
        
        matches = self.RESTRICTION_PATTERN.findall(text)
        # Normalize to uppercase and dedupe while preserving order
        seen = set()
        restrictions = []
        for r in matches:
            r_upper = r.upper()
            if r_upper not in seen:
                seen.add(r_upper)
                restrictions.append(r_upper)
        
        return restrictions
    
    def _validate_drug(self, drug: Drug) -> bool:
        """Validate a drug entry with strict rules for 95%+ accuracy."""
        name = drug.drug_name.strip() if drug.drug_name else ""
        
        # Name must be at least 3 characters
        if len(name) < 3:
            return False
        
        # Name shouldn't be all numbers
        if name.isdigit():
            return False
        
        # Drug names should start with a letter
        if not re.match(r'^[A-Za-z]', name):
            return False
        
        # ============================================
        # CRITICAL: Filter out category markers/paths
        # ============================================
        
        # Skip entries containing category markers like "A1", "B1", "C1"
        # These are hierarchy indicators in UHC PDFs, not drug names
        if re.search(r'\b[ABC][0-9]\b', name):
            return False
        
        # Skip entries that contain multiple category-like words joined
        # e.g., "Anesthetics B1 Local Anesthetics C1 Lidocaine"
        if re.search(r'[A-Z][0-9]\s+[A-Z]', name):
            return False
        
        # Skip pure category headers (common suffixes)
        category_patterns = [
            r'^.*\s+(Agents|Inhibitors|Blockers|Agonists|Antagonists|Modulators)$',
            r'^(Anti[-\s]?\w+|Miscellaneous|Other|General)\s*$',
            r'^.*ics$',  # Anesthetics, Antibiotics, etc. (but not drug names ending in -ics)
        ]
        # Only apply if no form is present (drugs have forms in parentheses)
        if not drug.form:
            for pattern in category_patterns:
                if re.match(pattern, name, re.IGNORECASE):
                    # Double-check: if it looks like a category, reject
                    if len(name.split()) <= 2:  # Short names like "Agents" or "Atypical Agents"
                        return False
        
        # Skip page numbers or markers
        if re.match(r'^\d+$|^page\s*\d*$|^--\s*\d+', name, re.IGNORECASE):
            return False
        
        # Skip entries with dots (page references like "..............54")
        if re.search(r'\.{3,}', name):
            return False
        
        # Skip common PDF artifacts and non-drug words
        skip_words = {
            'page', 'tier', 'form', 'brand', 'generic', 'type', 'restrictions', 
            'legend', 'key', 'note', 'section', 'chapter', 'index', 'table',
            'contents', 'drug', 'name', 'coverage', 'rules', 'limits', 'use',
            'last', 'updated', 'october', 'january', 'february', 'march',
            'you', 'can', 'find', 'information', 'what', 'the', 'abbreviations',
            'this', 'mean', 'pages', 'for', 'more', 'agents', 'inhibitors',
            'anesthetics', 'antibiotics', 'antifungals', 'antivirals',
            'analgesics', 'sedatives', 'stimulants', 'antagonists', 'agonists',
            'blockers', 'modulators', 'atypical', 'miscellaneous', 'other',
            'anti-craving', 'antiparasitics', 'anthelmintics', 'antigout',
            'antiparkinson', 'anticholinergics', 'local', 'general', 'topical',
            'systemic', 'oral', 'injectable', 'aminoglycosides', 'cephalosporins',
            'penicillins', 'macrolides', 'quinolones', 'sulfonamides', 'tetracyclines',
        }
        if name.lower().strip() in skip_words:
            return False
        
        # ============================================
        # POSITIVE VALIDATION: What makes a REAL drug
        # ============================================
        
        # HIGH CONFIDENCE: Has form in parentheses (almost all real drugs do)
        # This is the strongest indicator of a real drug entry
        if drug.form:
            # If it has a form like "(Oral Tablet)" or "(Injection)", very likely real
            return True
        
        # MEDIUM CONFIDENCE: Name looks like a drug name
        # Real drug names typically:
        # - End with common suffixes: -in, -ol, -ide, -ate, -ine, -one, -an, -il, -ax
        # - Are single words or have HCl, Sodium, etc.
        drug_name_patterns = [
            r'.*(in|ol|ide|ate|ine|one|an|il|ax|ir|ar|en|ex|ix|um|ib|ab|ub|mab|nib|vir)$',
            r'.*\s+(HCl|Sodium|Potassium|Calcium|Sulfate|Acetate|Mesylate|Maleate|Tartrate|Fumarate).*',
            r'^[A-Z][a-z]+$',  # Single capitalized word like "Lipitor", "Metformin"
        ]
        for pattern in drug_name_patterns:
            if re.match(pattern, name, re.IGNORECASE):
                return True
        
        # If no form and doesn't match drug patterns, likely a category - reject
        if not drug.form and len(name.split()) > 2:
            return False
        
        # Default: accept if nothing explicitly rejects it
        return True
    
    def _drug_identity_key(self, drug: Drug) -> tuple:
        """
        Stable identity for deduplication: same salt/form/strength/tier/restrictions
        can coexist; only rows that match on all fields collapse as duplicates.
        """
        name = drug.drug_name.lower().strip()
        form_norm = re.sub(r'\s+', ' ', (drug.form or '').strip().lower())
        if not form_norm and drug.raw_text:
            form_norm = re.sub(r'\s+', ' ', drug.raw_text.strip().lower())[:200]
        tier = int(drug.tier)
        typ = drug.type.value if drug.type else DrugType.UNKNOWN.value
        rests = tuple(sorted((r or "").upper() for r in (drug.restrictions or [])))
        return (name, form_norm, tier, typ, rests)

    def _prefer_richer_duplicate(self, a: Drug, b: Drug) -> Drug:
        """When identity keys collide, keep the row with more usable fields."""
        if b.form and not a.form:
            return b
        if a.form and not b.form:
            return a
        if len(b.restrictions) > len(a.restrictions):
            return b
        if len(a.restrictions) > len(b.restrictions):
            return a
        if b.type != DrugType.UNKNOWN and a.type == DrugType.UNKNOWN:
            return b
        return a

    def _deduplicate(self, drugs: List[Drug]) -> List[Drug]:
        """Remove only exact duplicates (same identity key); keep formulation variants."""
        seen: Dict[tuple, Drug] = {}
        order: List[tuple] = []

        for drug in drugs:
            key = self._drug_identity_key(drug)
            if key not in seen:
                seen[key] = drug
                order.append(key)
            else:
                seen[key] = self._prefer_richer_duplicate(seen[key], drug)

        return [seen[k] for k in order]
    
    def _final_validation(self, drug: Drug) -> bool:
        """
        Final validation pass with strict rules.
        This catches any remaining bad entries after initial parsing.
        """
        name = drug.drug_name.strip() if drug.drug_name else ""
        
        # Minimum length
        if len(name) < 3:
            return False
        
        # Must start with letter
        if not name[0].isalpha():
            return False
        
        # STRICT: Reject any entry still containing category markers
        bad_patterns = [
            r'\b[ABC][0-9]\b',  # A1, B1, C1 markers
            r'^(Agents?|Inhibitors?|Blockers?|Modulators?|Anesthetics?|Antibiotics?)$',
            r'^(Anti[-\s]?\w+s?)$',  # Anti-craving, Antiparasitics alone
            r'(Agents?|Inhibitors?)\s*$',  # Ends with category words
            r'^(Local|General|Topical|Systemic|Oral|Injectable)\s*$',  # Route-only
            r'^\d+\s*$',  # Just numbers
            r'Last updated',  # Page footers
            r'Brand Drug Coverage',  # Table headers
            r'You can find',  # Instructions
        ]
        
        for pattern in bad_patterns:
            if re.search(pattern, name, re.IGNORECASE):
                return False
        
        # STRICT: If no form, name must look like a real drug
        if not drug.form:
            # Without form info, require strong drug name indicators
            drug_suffixes = r'(in|ol|ide|ate|ine|one|mab|nib|vir|pril|lol|tan|zole|mycin|cillin|oxacin|cycline)$'
            salt_forms = r'\b(HCl|Sodium|Potassium|Calcium|Sulfate|Acetate|Mesylate)\b'
            
            has_drug_suffix = re.search(drug_suffixes, name, re.IGNORECASE)
            has_salt_form = re.search(salt_forms, name, re.IGNORECASE)
            is_single_capitalized = re.match(r'^[A-Z][a-z]+$', name)
            
            if not (has_drug_suffix or has_salt_form or is_single_capitalized):
                # No strong drug indicators and no form - reject
                return False
        
        # Passed all checks
        return True
    
    def get_llm_extraction_prompt(self, text: str) -> str:
        """Generate prompt for LLM-based extraction (for complex cases)."""
        return f"""Extract drug information from the following formulary text. 
For each drug, identify:
- drug_name: The name of the drug
- form: The form (e.g., Oral Tablet, Injection)
- type: "Brand" or "Generic" (B=Brand, G=Generic)
- tier: The formulary tier (1-6)
- restrictions: Array of restriction codes (PA, QL, ST, DL, etc.)

Return as JSON array:
[{{"drug_name": "...", "form": "...", "type": "...", "tier": N, "restrictions": [...]}}]

Text to parse:
{text[:3000]}

JSON output:"""
    
    async def parse_with_llm(self, text: str, llm_func) -> List[Drug]:
        """Parse using LLM for difficult text (async)."""
        prompt = self.get_llm_extraction_prompt(text)
        
        try:
            response = await llm_func(prompt)
            
            # Parse JSON response
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                data = json.loads(json_match.group())
                
                drugs = []
                for item in data:
                    drug = Drug(
                        drug_name=self._normalize_extracted_drug_name(str(item.get('drug_name', ''))),
                        form=item.get('form'),
                        type=DrugType.BRAND if item.get('type', '').upper() in ('B', 'BRAND') else DrugType.GENERIC,
                        tier=int(item.get('tier', 1)),
                        restrictions=item.get('restrictions', []),
                        restriction_details=[RESTRICTION_DESCRIPTIONS.get(r, r) for r in item.get('restrictions', [])],
                    )
                    if self._validate_drug(drug):
                        drugs.append(drug)
                
                return drugs
        except Exception as e:
            logger.error(f"LLM parsing failed: {e}")
        
        return []


# Factory function
def get_parser(llm_client=None) -> FormularyParser:
    """Get a FormularyParser instance."""
    return FormularyParser(llm_client=llm_client)
