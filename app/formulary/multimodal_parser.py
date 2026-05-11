"""Gemini multimodal PDF transcription for formulary ingestion.

Uses Google Gen AI (Gemini) to read PDFs as vision + document understanding,
then normalizes output for the existing regex-based FormularyParser.

Example:

    parser = MultimodalParser(
        model_provider="google",
        model="gemini-3.1-flash-lite-preview",
        reasoning_effort="low",
        merge_table=True,
        create_html=True,
    )
    result = parser.parse("document.pdf")
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from loguru import logger

ReasoningEffort = Literal["none", "low", "medium", "high"]

# Maps human knob -> Gemini thinking_budget (0 = off; -1 = automatic per SDK docs).
_REASONING_TO_BUDGET: Dict[str, int] = {
    "none": 0,
    "low": 2048,
    "medium": 8192,
    "high": -1,
}

_PAGE_MARKER_RE = re.compile(r"(?:^|\n)---\s*PAGE\s+(\d+)\s*---", re.IGNORECASE)


class MultimodalParser:
    """Parse PDFs via Gemini multimodal (document + vision)."""

    def __init__(
        self,
        *,
        model_provider: Literal["google"] = "google",
        model: str = "gemini-3.1-flash-lite-preview",
        reasoning_effort: ReasoningEffort = "low",
        merge_table: bool = True,
        create_html: bool = True,
        api_key: Optional[str] = None,
    ):
        if model_provider != "google":
            raise ValueError(f"Unsupported model_provider: {model_provider}")
        self.model_provider = model_provider
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.merge_table = merge_table
        self.create_html = create_html
        self.api_key = api_key

    def parse(
        self,
        source: Union[str, Path, bytes],
        *,
        filename: str = "document.pdf",
    ) -> Dict[str, Any]:
        """
        Transcribe a PDF into plain text (and optional HTML) for downstream parsing.

        Args:
            source: Path to a PDF file, or raw PDF bytes.
            filename: Filename used when source is bytes (for logs / metadata).

        Returns:
            Dict aligned with PDFIngestionService extract shape:
            success, full_text, page_texts, tables, page_count, char_count, has_tables,
            plus optional html, raw_response_text.
        """
        pdf_bytes, name = self._resolve_source(source, filename)
        try:
            from google import genai
            from google.genai import types
        except ImportError as e:
            raise RuntimeError(
                "google-genai is required for MultimodalParser. "
                "Install with: pip install google-genai"
            ) from e

        api_key = self.api_key
        if not api_key:
            from app.config import get_settings

            api_key = get_settings().google_api_key
        if not api_key:
            raise RuntimeError(
                "Google API key missing. Set GOOGLE_API_KEY in the environment."
            )

        client = genai.Client(api_key=api_key)
        prompt = self._build_prompt()

        contents: List[Any] = [
            prompt,
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
        ]

        thinking_budget = _REASONING_TO_BUDGET.get(self.reasoning_effort, 2048)
        thinking_cfg = types.ThinkingConfig(thinking_budget=thinking_budget)

        config = types.GenerateContentConfig(
            temperature=0.0,
            thinking_config=thinking_cfg,
            response_mime_type="application/json",
        )

        try:
            response = client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
        except Exception as e:
            logger.warning(f"Gemini JSON mode failed ({e}), retrying without JSON mime type")
            try:
                config = types.GenerateContentConfig(
                    temperature=0.0,
                    thinking_config=thinking_cfg,
                )
                response = client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
            except Exception as e2:
                logger.warning(f"Gemini with thinking_config failed ({e2}), retrying minimal config")
                response = client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(temperature=0.0),
                )

        raw_text = self._response_text(response)
        payload = self._parse_model_payload(raw_text)

        plain = payload.get("plain_text") or payload.get("plainText") or ""
        html = payload.get("html") or ""
        if not self.create_html:
            html = ""

        if not plain.strip():
            plain = raw_text

        page_texts = self._plain_to_page_texts(plain)
        page_count = len(page_texts)
        try:
            reported = int(payload.get("page_count") or payload.get("pageCount") or 0)
            if reported > page_count:
                page_count = reported
        except (TypeError, ValueError):
            pass

        full_text = "\n\n".join(p["text"] for p in page_texts) if page_texts else plain

        return {
            "success": True,
            "full_text": full_text,
            "page_texts": page_texts,
            "tables": [],
            "page_count": page_count or 1,
            "char_count": len(full_text),
            "has_tables": bool(html and "<table" in html.lower()),
            "html": html if html else None,
            "extractor_used": "gemini_multimodal",
            "raw_response_text": raw_text[:8000] if len(raw_text) > 8000 else raw_text,
        }

    def _resolve_source(
        self, source: Union[str, Path, bytes], filename: str
    ) -> tuple[bytes, str]:
        if isinstance(source, bytes):
            return source, filename
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")
        return path.read_bytes(), path.name

    def _build_prompt(self) -> str:
        merge = (
            "Merge table cells that belong to the same drug row so each drug appears on "
            "one logical line when possible (Name (Form) B or G tier restrictions)."
            if self.merge_table
            else "Preserve line breaks as in the document; do not merge table rows."
        )
        html_instr = (
            "Include a field `html`: a single HTML fragment using <table> where tables "
            "appear, preserving headers and drug rows. Escape text properly."
            if self.create_html
            else "Set `html` to an empty string."
        )
        return f"""You are a precise OCR and layout transcription system for health insurance formulary PDFs.

Task: Read the attached PDF and return strict JSON with these keys:
- "plain_text": Full verbatim transcription for programmatic parsing. Use UTF-8 text only.
- "page_count": Integer number of pages you processed.
- "html": {html_instr}

Rules for plain_text:
1. Transcribe visible text faithfully (drug names, tiers, B/G, restriction codes like PA, QL).
2. Between each page, insert EXACTLY this delimiter on its own line (required):
   ---PAGE N---
   where N is 1-based page index.
3. {merge}
4. Do not summarize, interpret coverage, or omit drug lines.

Return ONLY valid JSON, no markdown fences."""

    @staticmethod
    def _response_text(response: Any) -> str:
        if response is None:
            return ""
        text = getattr(response, "text", None)
        if text:
            return text
        try:
            cand = response.candidates[0]
            parts = cand.content.parts
            out = []
            for p in parts:
                if getattr(p, "text", None):
                    out.append(p.text)
            return "\n".join(out)
        except (AttributeError, IndexError, TypeError):
            return ""

    def _parse_model_payload(self, raw_text: str) -> Dict[str, Any]:
        raw_text = (raw_text or "").strip()
        if not raw_text:
            return {}
        blob = raw_text
        if blob.startswith("```"):
            blob = re.sub(r"^```(?:json)?\s*", "", blob)
            blob = re.sub(r"\s*```\s*$", "", blob)

        def _try_load(s: str) -> Optional[Dict[str, Any]]:
            try:
                data = json.loads(s)
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None

        parsed = _try_load(blob)
        if parsed is not None:
            return parsed

        # Model sometimes adds prose before/after the JSON object
        m = re.search(r"\{[\s\S]*\}\s*$", raw_text)
        if m:
            parsed = _try_load(m.group(0).strip())
            if parsed is not None:
                logger.debug("Parsed Gemini JSON by extracting trailing object from response")
                return parsed

        m2 = re.search(r"\{[\s\S]*\}", raw_text)
        if m2:
            parsed = _try_load(m2.group(0).strip())
            if parsed is not None:
                logger.debug("Parsed Gemini JSON by scanning first object in response")
                return parsed

        logger.info(
            "Gemini did not return valid JSON; using full response as plain_text (parsing still works)"
        )
        return {"plain_text": raw_text}

    def _plain_to_page_texts(self, plain: str) -> List[Dict[str, Any]]:
        if not plain.strip():
            return []

        matches = list(_PAGE_MARKER_RE.finditer(plain))
        if not matches:
            t = plain.strip()
            return [{"page": 1, "text": t, "char_count": len(t)}]

        page_texts: List[Dict[str, Any]] = []
        for i, m in enumerate(matches):
            body_start = m.end()
            body_end = matches[i + 1].start() if i + 1 < len(matches) else len(plain)
            chunk = plain[body_start:body_end].strip()
            try:
                page_num = int(m.group(1))
            except (ValueError, TypeError):
                page_num = i + 1
            if i == 0:
                preamble = plain[: m.start()].strip()
                if preamble:
                    chunk = f"{preamble}\n\n{chunk}".strip()
            if chunk:
                page_texts.append(
                    {"page": page_num, "text": chunk, "char_count": len(chunk)}
                )

        if not page_texts:
            t = plain.strip()
            return [{"page": 1, "text": t, "char_count": len(t)}]
        return page_texts


def multimodal_parse_pdf_bytes(
    pdf_bytes: bytes,
    *,
    filename: str = "document.pdf",
) -> Dict[str, Any]:
    """Convenience: parse bytes using settings-derived defaults."""
    from app.config import get_settings

    s = get_settings()
    parser = MultimodalParser(
        model_provider="google",
        model=s.gemini_pdf_model,
        reasoning_effort=s.gemini_pdf_reasoning_effort,
        merge_table=s.gemini_pdf_merge_tables,
        create_html=s.gemini_pdf_create_html,
    )
    return parser.parse(pdf_bytes, filename=filename)
