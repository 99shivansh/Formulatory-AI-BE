"""PDF Ingestion Module for Formulary Processing.

Handles PDF upload and text extraction using:
- Gemini multimodal (optional primary) — MultimodalParser via Google Gen AI
- pdfplumber (library primary) — tables and structured text
- PyMuPDF/fitz (fallback) — fast text extraction
"""

import asyncio
import io
import re
from typing import Optional, List, Dict, Any
from pathlib import Path
from loguru import logger

from app.config import get_settings

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    logger.warning("pdfplumber not installed, using fallback")

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.warning("PyMuPDF not installed")


class PDFIngestionService:
    """Service for PDF ingestion and text extraction."""
    
    def __init__(self):
        """Initialize PDF ingestion service."""
        settings = get_settings()
        gemini_ready = (
            settings.formulary_pdf_extraction == "gemini"
            and bool(settings.google_api_key)
        )
        library_ready = PDFPLUMBER_AVAILABLE or PYMUPDF_AVAILABLE

        if not gemini_ready and not library_ready:
            raise RuntimeError(
                "No PDF extraction path available. Install pdfplumber and/or PyMuPDF, "
                "or set GOOGLE_API_KEY and FORMULARY_PDF_EXTRACTION=gemini."
            )

        self.primary_extractor = "pdfplumber" if PDFPLUMBER_AVAILABLE else "pymupdf"
        if gemini_ready:
            logger.info(
                "PDF Ingestion: Gemini multimodal enabled; library extractors available as fallback"
            )
        logger.info(f"PDF Ingestion library path primary: {self.primary_extractor}")
    
    async def extract_from_bytes(
        self,
        pdf_bytes: bytes,
        filename: str = "upload.pdf",
    ) -> Dict[str, Any]:
        """
        Extract text from PDF bytes.
        
        Args:
            pdf_bytes: Raw PDF file bytes
            filename: Original filename for metadata
            
        Returns:
            Dict with extracted text and metadata
        """
        settings = get_settings()
        use_gemini = (
            settings.formulary_pdf_extraction == "gemini"
            and bool(settings.google_api_key)
        )

        if use_gemini:
            try:
                from app.formulary.multimodal_parser import multimodal_parse_pdf_bytes

                result = await asyncio.to_thread(
                    multimodal_parse_pdf_bytes,
                    pdf_bytes,
                    filename=filename,
                )
                result["filename"] = filename
                if result.get("success"):
                    logger.info(
                        f"Gemini extracted {result.get('page_count', 0)} pages from {filename}"
                    )
                    return result
                logger.warning("Gemini extraction returned success=False; falling back")
            except Exception as e:
                logger.warning(f"Gemini multimodal extraction failed: {e}; using library extractors")

        if settings.formulary_pdf_extraction == "gemini" and not settings.google_api_key:
            logger.warning(
                "FORMULARY_PDF_EXTRACTION is gemini but GOOGLE_API_KEY is empty; using library extractors"
            )

        try:
            # Try primary extractor first
            if self.primary_extractor == "pdfplumber" and PDFPLUMBER_AVAILABLE:
                result = self._extract_with_pdfplumber(pdf_bytes)
            else:
                result = self._extract_with_pymupdf(pdf_bytes)
            
            # Add metadata
            result["filename"] = filename
            result["extractor_used"] = self.primary_extractor
            
            logger.info(f"Extracted {result['page_count']} pages from {filename}")
            return result
            
        except Exception as e:
            # Try fallback extractor
            logger.warning(f"Primary extractor failed: {e}, trying fallback")
            
            if self.primary_extractor == "pdfplumber" and PYMUPDF_AVAILABLE:
                result = self._extract_with_pymupdf(pdf_bytes)
                result["extractor_used"] = "pymupdf (fallback)"
            elif PDFPLUMBER_AVAILABLE:
                result = self._extract_with_pdfplumber(pdf_bytes)
                result["extractor_used"] = "pdfplumber (fallback)"
            else:
                raise RuntimeError(f"All PDF extractors failed: {e}")
            
            result["filename"] = filename
            return result
    
    def _extract_with_pdfplumber(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Extract using pdfplumber (better for tables)."""
        text_parts = []
        tables_data = []
        page_texts = []
        
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            page_count = len(pdf.pages)
            
            for page_num, page in enumerate(pdf.pages, 1):
                # Extract text
                page_text = page.extract_text() or ""
                text_parts.append(page_text)
                page_texts.append({
                    "page": page_num,
                    "text": page_text,
                    "char_count": len(page_text)
                })
                
                # Extract tables if present
                tables = page.extract_tables()
                if tables:
                    for table_idx, table in enumerate(tables):
                        tables_data.append({
                            "page": page_num,
                            "table_index": table_idx,
                            "rows": table,
                            "row_count": len(table) if table else 0
                        })
        
        full_text = "\n\n".join(text_parts)
        
        return {
            "success": True,
            "full_text": full_text,
            "page_texts": page_texts,
            "tables": tables_data,
            "page_count": page_count,
            "char_count": len(full_text),
            "has_tables": len(tables_data) > 0,
        }
    
    def _extract_with_pymupdf(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Extract using PyMuPDF (fast fallback)."""
        text_parts = []
        page_texts = []
        
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = len(doc)
        
        for page_num in range(page_count):
            page = doc[page_num]
            page_text = page.get_text()
            text_parts.append(page_text)
            page_texts.append({
                "page": page_num + 1,
                "text": page_text,
                "char_count": len(page_text)
            })
        
        doc.close()
        full_text = "\n\n".join(text_parts)
        
        return {
            "success": True,
            "full_text": full_text,
            "page_texts": page_texts,
            "tables": [],  # PyMuPDF doesn't extract tables as well
            "page_count": page_count,
            "char_count": len(full_text),
            "has_tables": False,
        }
    
    async def extract_from_file(self, file_path: str) -> Dict[str, Any]:
        """Extract from a file path."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if not path.suffix.lower() == ".pdf":
            raise ValueError(f"Not a PDF file: {file_path}")
        
        pdf_bytes = path.read_bytes()
        return await self.extract_from_bytes(pdf_bytes, path.name)
    
    def preprocess_text(self, text: str) -> str:
        """
        Preprocess extracted text for parsing.
        
        - Normalize whitespace
        - Fix common OCR issues
        - Clean special characters
        """
        # Normalize line endings
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Remove excessive whitespace but preserve line structure
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Normalize internal whitespace
            line = ' '.join(line.split())
            if line:  # Skip empty lines
                cleaned_lines.append(line)
        
        # Rejoin with single newlines
        text = '\n'.join(cleaned_lines)
        
        # Fix common OCR issues
        text = text.replace('|', 'I')  # Pipe often misread as I
        text = text.replace('0', 'O').replace('O', '0')  # Revert - context dependent
        
        # Actually, let's be more careful with OCR fixes
        text = re.sub(r'\s+', ' ', text)  # Collapse multiple spaces
        text = re.sub(r'\n{3,}', '\n\n', text)  # Max 2 newlines
        
        return text.strip()
    
    def extract_formulary_sections(self, text: str) -> Dict[str, str]:
        """
        Attempt to identify and extract formulary sections.
        
        Common sections:
        - Drug listings by therapeutic class
        - Tier information
        - Restriction legends
        """
        sections = {
            "legend": "",
            "drug_listings": "",
            "tier_info": "",
            "full_text": text,
        }
        
        # Look for legend/key section
        legend_patterns = [
            r"(?i)(legend|key|abbreviations|restriction codes?)[\s\S]{0,500}?(?=\n\n|\Z)",
            r"(?i)(PA\s*[=:]\s*Prior|QL\s*[=:]\s*Quantity)[\s\S]{0,300}",
        ]
        
        for pattern in legend_patterns:
            match = re.search(pattern, text)
            if match:
                sections["legend"] = match.group(0)
                break
        
        # Look for tier information
        tier_patterns = [
            r"(?i)(tier\s*\d[\s\S]{0,200})",
            r"(?i)(formulary\s*tier[\s\S]{0,500})",
        ]
        
        for pattern in tier_patterns:
            matches = re.findall(pattern, text)
            if matches:
                sections["tier_info"] = "\n".join(matches[:5])
                break
        
        return sections
    
    def extract_drug_category_section(self, page_texts: List[Dict]) -> str:
        """
        Extract ONLY the 'Covered drugs by category' section from page texts.
        
        This section contains the actual drug data with tier, B/G, and restrictions.
        The 'Drug index' section (pages 12-29 typically) only has drug names and page numbers.
        
        Args:
            page_texts: List of page dictionaries with 'page' and 'text' keys
            
        Returns:
            Extracted text from the drug category section only
        """
        category_texts = []
        in_category_section = False
        category_start_page = None
        
        # Markers to identify sections
        category_start_markers = [
            "covered drugs by category",
            "drugs by category",
            "drug category",
        ]
        category_end_markers = [
            "covered drugs with a quantity limit",
            "additional covered drugs",
            "quantity limit (ql)",
        ]
        index_markers = [
            "covered drugs by name (drug index)",
            "drug index",
        ]
        
        for page_data in page_texts:
            page_num = page_data.get("page", 0)
            text = page_data.get("text", "").lower()
            
            # Check if we're entering the category section
            if not in_category_section:
                for marker in category_start_markers:
                    if marker in text:
                        in_category_section = True
                        category_start_page = page_num
                        logger.info(f"Found 'Covered drugs by category' starting at page {page_num}")
                        break
            
            # If in category section, check for end markers
            if in_category_section:
                should_stop = False
                for marker in category_end_markers:
                    if marker in text and page_num > (category_start_page or 0) + 5:
                        should_stop = True
                        logger.info(f"Found end of category section at page {page_num}")
                        break
                
                if should_stop:
                    break
                
                # Skip pages that are primarily the drug index (names + page refs).
                # Always include the category start page even if "drug index" appears
                # elsewhere on that page (single-page Gemini blobs often contain both).
                is_index_page = any(marker in text for marker in index_markers)
                if not is_index_page or page_num == category_start_page:
                    category_texts.append(page_data.get("text", ""))
        
        if not category_texts:
            logger.warning("Could not find 'Covered drugs by category' section, using all text")
            return "\n\n".join(p.get("text", "") for p in page_texts)
        
        result = "\n\n".join(category_texts)
        logger.info(f"Extracted {len(category_texts)} pages from category section")
        return result


# Singleton instance
_service_instance: Optional[PDFIngestionService] = None


def get_pdf_service() -> PDFIngestionService:
    """Get or create PDF ingestion service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = PDFIngestionService()
    return _service_instance
