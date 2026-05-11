"""API routes for Formulary & Access Intelligence."""

from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse
from typing import Optional, List
from loguru import logger

from app.formulary.service import get_formulary_service
from app.formulary.models import (
    FormularyUploadResponse,
    FormularyInsights,
    PlanComparison,
    Drug,
    ComparisonRequest,
)

router = APIRouter(prefix="/formulary", tags=["Formulary Intelligence"])


@router.post(
    "/upload",
    response_model=FormularyUploadResponse,
    summary="Upload Formulary PDF",
    description="Upload a formulary PDF to extract and analyze drug coverage data",
)
async def upload_formulary(
    file: UploadFile = File(..., description="Formulary PDF file"),
    plan_name: Optional[str] = Form(None, description="Custom plan name"),
) -> FormularyUploadResponse:
    """
    Upload and process a formulary PDF.
    
    - Extracts drug data from PDF
    - Parses and structures the data
    - Computes access scores
    - Stores for future queries
    """
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported"
        )
    
    # Read file
    try:
        pdf_bytes = await file.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file: {str(e)}"
        )
    
    # Process PDF
    service = get_formulary_service()
    result = await service.process_pdf(
        pdf_bytes=pdf_bytes,
        filename=file.filename,
        plan_name=plan_name,
    )
    
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result.message
        )
    
    return result


@router.get(
    "/plans",
    summary="List All Plans",
    description="Get a list of all uploaded formulary plans",
)
async def list_plans():
    """List all stored formulary plans."""
    service = get_formulary_service()
    return {"plans": service.list_plans()}


@router.get(
    "/plans/{plan_id}",
    summary="Get Plan Details",
    description="Get full details of a formulary plan including all drugs",
)
async def get_plan(plan_id: str):
    """Get a specific plan with all its drugs."""
    service = get_formulary_service()
    plan = service.get_plan(plan_id)
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan not found: {plan_id}"
        )
    
    return plan.model_dump()


@router.delete(
    "/plans/{plan_id}",
    summary="Delete Plan",
    description="Delete a formulary plan",
)
async def delete_plan(plan_id: str):
    """Delete a plan."""
    service = get_formulary_service()
    success = service.delete_plan(plan_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan not found: {plan_id}"
        )
    
    return {"message": f"Plan {plan_id} deleted successfully"}


@router.get(
    "/plans/{plan_id}/insights",
    response_model=FormularyInsights,
    summary="Get Plan Insights",
    description="Get analytics and insights for a formulary plan",
)
async def get_plan_insights(plan_id: str) -> FormularyInsights:
    """Get comprehensive insights for a plan."""
    service = get_formulary_service()
    insights = service.get_plan_insights(plan_id)
    
    if not insights:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan not found: {plan_id}"
        )
    
    return insights


@router.get(
    "/plans/{plan_id}/drugs",
    summary="Search Drugs",
    description="Search and filter drugs in a formulary plan",
)
async def search_drugs(
    plan_id: str,
    q: Optional[str] = Query(None, description="Search query (drug name)"),
    tier: Optional[int] = Query(None, ge=1, le=6, description="Filter by tier"),
    restrictions: Optional[str] = Query(None, description="Filter by restrictions (comma-separated: PA,QL,ST)"),
    min_score: Optional[int] = Query(None, ge=0, le=15, description="Minimum access score"),
    limit: int = Query(50, ge=1, le=500, description="Maximum results"),
):
    """Search drugs with optional filters."""
    service = get_formulary_service()
    
    # Parse restrictions
    restriction_list = None
    if restrictions:
        restriction_list = [r.strip().upper() for r in restrictions.split(",")]
    
    drugs = service.search_drugs(
        plan_id=plan_id,
        query=q or "",
        tier=tier,
        restrictions=restriction_list,
        min_access_score=min_score,
        limit=limit,
    )
    
    if not drugs and not service.get_plan(plan_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan not found: {plan_id}"
        )
    
    return {
        "plan_id": plan_id,
        "count": len(drugs),
        "drugs": [d.model_dump() for d in drugs],
    }


@router.get(
    "/plans/{plan_id}/drugs/{drug_name}",
    summary="Get Drug Details",
    description="Get detailed information about a specific drug",
)
async def get_drug_details(plan_id: str, drug_name: str):
    """Get detailed information about a specific drug."""
    service = get_formulary_service()
    details = service.get_drug_details(plan_id, drug_name)
    
    if not details:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Drug '{drug_name}' not found in plan {plan_id}"
        )
    
    return details


@router.post(
    "/compare",
    response_model=PlanComparison,
    summary="Compare Plans",
    description="Compare drug coverage between two formulary plans",
)
async def compare_plans(request: ComparisonRequest) -> PlanComparison:
    """
    Compare two formulary plans.
    
    - Compares drug coverage
    - Calculates score differences
    - Identifies better plan
    - Provides insights
    """
    service = get_formulary_service()
    
    comparison = service.compare_plans(
        plan_a_id=request.plan_a_id,
        plan_b_id=request.plan_b_id,
        drug_names=request.drug_names,
    )
    
    if not comparison:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or both plans not found"
        )
    
    return comparison


@router.get(
    "/compare/{plan_a_id}/{plan_b_id}/drug/{drug_name}",
    summary="Compare Drug Across Plans",
    description="Compare a specific drug between two plans",
)
async def compare_drug(plan_a_id: str, plan_b_id: str, drug_name: str):
    """Compare a specific drug across two plans."""
    service = get_formulary_service()
    
    plan_a = service.get_plan(plan_a_id)
    plan_b = service.get_plan(plan_b_id)
    
    if not plan_a or not plan_b:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or both plans not found"
        )
    
    comparison_engine = service.comparison_engine
    result = comparison_engine.get_drug_comparison_detail(drug_name, plan_a, plan_b)
    
    return result


# Health check for formulary module
@router.get(
    "/health",
    summary="Formulary Module Health",
    description="Check if formulary module is operational",
)
async def formulary_health():
    """Check formulary module health."""
    service = get_formulary_service()
    return {
        "status": "healthy",
        "module": "formulary",
        "plans_loaded": len(service._plans),
    }
