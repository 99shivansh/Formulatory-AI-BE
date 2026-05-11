"""Formulary Service - Main orchestrator for formulary operations.

Coordinates all formulary modules:
- PDF ingestion
- Parsing
- Scoring
- Insights
- Comparison
"""

import uuid
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
from loguru import logger

from app.formulary.models import (
    Drug,
    FormularyPlan,
    FormularyInsights,
    PlanComparison,
    FormularyUploadResponse,
)
from app.formulary.pdf_ingestion import get_pdf_service
from app.formulary.parser import FormularyParser
from app.formulary.scoring import get_scoring_engine
from app.formulary.insights import get_insights_engine
from app.formulary.comparison import get_comparison_engine


def _formulary_metadata_from_extraction(extraction_result: Dict[str, Any]) -> Dict[str, Any]:
    """Attach optional Gemini HTML stats without storing full HTML on the plan."""
    md: Dict[str, Any] = {
        "page_count": extraction_result.get("page_count", 0),
        "char_count": extraction_result.get("char_count", 0),
        "extractor_used": extraction_result.get("extractor_used", "unknown"),
    }
    html = extraction_result.get("html")
    if html:
        md["gemini_html_chars"] = len(html)
    return md


class FormularyService:
    """Main service for formulary operations."""
    
    def __init__(self):
        """Initialize formulary service."""
        self.pdf_service = get_pdf_service()
        self.parser = FormularyParser()
        self.scoring_engine = get_scoring_engine()
        self.insights_engine = get_insights_engine()
        self.comparison_engine = get_comparison_engine()
        
        # In-memory storage for plans (use DB in production)
        self._plans: Dict[str, FormularyPlan] = {}
        
        logger.info("FormularyService initialized")
    
    async def process_pdf(
        self,
        pdf_bytes: bytes,
        filename: str,
        plan_name: Optional[str] = None,
    ) -> FormularyUploadResponse:
        """
        Process a formulary PDF end-to-end.
        
        Args:
            pdf_bytes: Raw PDF bytes
            filename: Original filename
            plan_name: Optional custom plan name
            
        Returns:
            FormularyUploadResponse with results
        """
        start_time = time.time()
        
        try:
            # Step 1: Extract text from PDF
            logger.info(f"Processing PDF: {filename}")
            extraction_result = await self.pdf_service.extract_from_bytes(pdf_bytes, filename)
            
            if not extraction_result.get("success"):
                return FormularyUploadResponse(
                    success=False,
                    plan_id="",
                    plan_name="",
                    drugs_extracted=0,
                    message="Failed to extract text from PDF",
                    processing_time_ms=0,
                )
            
            # Step 2: Extract only the "Covered drugs by category" section
            # This avoids parsing the Drug Index which only has names + page numbers
            page_texts = extraction_result.get("page_texts", [])
            if page_texts:
                category_text = self.pdf_service.extract_drug_category_section(page_texts)
            else:
                category_text = extraction_result.get("full_text", "")
            
            # Step 3: Parse drug data from the category section only
            drugs = self.parser.parse(category_text)
            
            if not drugs:
                return FormularyUploadResponse(
                    success=False,
                    plan_id="",
                    plan_name="",
                    drugs_extracted=0,
                    message="No drugs could be extracted from the PDF. Check if the format matches expected patterns.",
                    processing_time_ms=(time.time() - start_time) * 1000,
                )
            
            # Step 4: Score drugs
            scored_drugs = self.scoring_engine.score_drugs(drugs)
            
            # Step 5: Create plan
            plan_id = f"plan_{uuid.uuid4().hex[:12]}"
            plan = FormularyPlan(
                plan_id=plan_id,
                plan_name=plan_name or filename.replace(".pdf", ""),
                drugs=scored_drugs,
                metadata={
                    "source_file": filename,
                    **_formulary_metadata_from_extraction(extraction_result),
                },
                created_at=datetime.utcnow(),
            )
            
            # Store plan
            self._plans[plan_id] = plan
            
            processing_time = (time.time() - start_time) * 1000
            
            logger.info(f"Successfully processed {filename}: {len(scored_drugs)} drugs in {processing_time:.0f}ms")
            
            return FormularyUploadResponse(
                success=True,
                plan_id=plan_id,
                plan_name=plan.plan_name,
                drugs_extracted=len(scored_drugs),
                message=f"Successfully extracted and scored {len(scored_drugs)} drugs",
                processing_time_ms=processing_time,
            )
            
        except Exception as e:
            logger.error(f"Error processing PDF {filename}: {str(e)}")
            return FormularyUploadResponse(
                success=False,
                plan_id="",
                plan_name="",
                drugs_extracted=0,
                message=f"Error processing PDF: {str(e)}",
                processing_time_ms=(time.time() - start_time) * 1000,
            )
    
    def get_plan(self, plan_id: str) -> Optional[FormularyPlan]:
        """Get a plan by ID."""
        return self._plans.get(plan_id)
    
    def list_plans(self) -> List[Dict[str, Any]]:
        """List all stored plans."""
        return [
            {
                "plan_id": p.plan_id,
                "plan_name": p.plan_name,
                "drug_count": len(p.drugs),
                "created_at": p.created_at.isoformat(),
            }
            for p in self._plans.values()
        ]
    
    def delete_plan(self, plan_id: str) -> bool:
        """Delete a plan."""
        if plan_id in self._plans:
            del self._plans[plan_id]
            logger.info(f"Deleted plan: {plan_id}")
            return True
        return False
    
    def get_plan_insights(self, plan_id: str) -> Optional[FormularyInsights]:
        """Get insights for a plan."""
        plan = self.get_plan(plan_id)
        if not plan:
            return None
        
        return self.insights_engine.analyze(plan.drugs)
    
    def compare_plans(
        self,
        plan_a_id: str,
        plan_b_id: str,
        drug_names: Optional[List[str]] = None,
    ) -> Optional[PlanComparison]:
        """Compare two plans."""
        plan_a = self.get_plan(plan_a_id)
        plan_b = self.get_plan(plan_b_id)
        
        if not plan_a or not plan_b:
            return None
        
        return self.comparison_engine.compare_plans(plan_a, plan_b, drug_names)
    
    def search_drug(
        self,
        plan_id: str,
        drug_name: str,
    ) -> Optional[Drug]:
        """Search for a drug in a plan."""
        plan = self.get_plan(plan_id)
        if not plan:
            return None
        
        # Case-insensitive search
        drug_name_lower = drug_name.lower()
        for drug in plan.drugs:
            if drug.drug_name.lower() == drug_name_lower:
                return drug
            # Partial match
            if drug_name_lower in drug.drug_name.lower():
                return drug
        
        return None
    
    def search_drugs(
        self,
        plan_id: str,
        query: str,
        tier: Optional[int] = None,
        restrictions: Optional[List[str]] = None,
        min_access_score: Optional[int] = None,
        limit: int = 50,
    ) -> List[Drug]:
        """
        Search drugs in a plan with filters.
        
        Args:
            plan_id: Plan ID
            query: Search query (drug name)
            tier: Filter by tier
            restrictions: Filter by restrictions
            min_access_score: Minimum access score
            limit: Maximum results
            
        Returns:
            List of matching drugs
        """
        plan = self.get_plan(plan_id)
        if not plan:
            return []
        
        results = []
        query_lower = query.lower() if query else ""
        
        for drug in plan.drugs:
            # Name filter
            if query_lower and query_lower not in drug.drug_name.lower():
                continue
            
            # Tier filter
            if tier is not None and drug.tier != tier:
                continue
            
            # Restrictions filter
            if restrictions:
                if not any(r in drug.restrictions for r in restrictions):
                    continue
            
            # Access score filter
            if min_access_score is not None:
                if not drug.access_score or drug.access_score.score < min_access_score:
                    continue
            
            results.append(drug)
            
            if len(results) >= limit:
                break
        
        return results
    
    def get_drug_details(self, plan_id: str, drug_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a drug including insights."""
        drug = self.search_drug(plan_id, drug_name)
        if not drug:
            return None
        
        # Get drug-specific insights
        drug_insights = self.insights_engine.get_drug_insights(drug)
        
        # Get score explanation
        score_explanation = self.scoring_engine.get_score_explanation(drug)
        
        return {
            "drug": drug.model_dump(),
            "insights": drug_insights,
            "score_explanation": score_explanation,
        }


# Singleton instance
_service_instance: Optional[FormularyService] = None


def get_formulary_service() -> FormularyService:
    """Get or create formulary service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = FormularyService()
    return _service_instance
