"""Data models for Formulary & Access Intelligence."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum


class DrugType(str, Enum):
    """Drug type enumeration."""
    BRAND = "Brand"
    GENERIC = "Generic"
    UNKNOWN = "Unknown"


class RestrictionCode(str, Enum):
    """Restriction codes with descriptions."""
    PA = "Prior Authorization"
    QL = "Quantity Limit"
    ST = "Step Therapy"
    DL = "Dispensing Limit"
    SP = "Specialty Pharmacy"
    LA = "Limited Access"
    AR = "Age Restriction"
    GR = "Gender Restriction"
    BD = "Medicare Part B or D"
    MME = "Morphine Milligram Equivalent Limit"
    SEVEN_D = "7-Day Supply Limit"


# Restriction mapping for parsing
RESTRICTION_MAP = {
    "PA": RestrictionCode.PA,
    "QL": RestrictionCode.QL,
    "ST": RestrictionCode.ST,
    "DL": RestrictionCode.DL,
    "SP": RestrictionCode.SP,
    "LA": RestrictionCode.LA,
    "AR": RestrictionCode.AR,
    "GR": RestrictionCode.GR,
    "B/D": RestrictionCode.BD,
    "MME": RestrictionCode.MME,
    "7D": RestrictionCode.SEVEN_D,
}

RESTRICTION_DESCRIPTIONS = {
    "PA": "Prior Authorization - Requires approval before coverage",
    "QL": "Quantity Limit - Limits on amount dispensed",
    "ST": "Step Therapy - Must try other drugs first",
    "DL": "Dispensing Limit - 1-month supply per prescription",
    "SP": "Specialty Pharmacy - Must use specialty pharmacy",
    "LA": "Limited Access - Only available from certain facilities",
    "AR": "Age Restriction - Age-based coverage limits",
    "GR": "Gender Restriction - Gender-based coverage limits",
    "B/D": "Medicare Part B or D - Coverage depends on usage",
    "MME": "Morphine Milligram Equivalent - Opioid dose monitoring",
    "7D": "7-Day Limit - Limited to 7-day supply for new opioid users",
}


class AccessLabel(str, Enum):
    """Access level labels."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class AccessScore(BaseModel):
    """Access score for a drug."""
    score: int = Field(..., ge=0, le=15, description="Access score 0-15")
    label: AccessLabel = Field(..., description="Access label")
    factors: Dict[str, Any] = Field(default_factory=dict, description="Score breakdown")


class Drug(BaseModel):
    """Drug model with coverage details."""
    drug_name: str = Field(..., description="Drug name")
    form: Optional[str] = Field(None, description="Drug form (e.g., Oral Capsule)")
    type: DrugType = Field(default=DrugType.UNKNOWN, description="Brand or Generic")
    tier: int = Field(..., ge=1, le=6, description="Formulary tier 1-6")
    restrictions: List[str] = Field(default_factory=list, description="Restriction codes")
    restriction_details: List[str] = Field(default_factory=list, description="Restriction descriptions")
    access_score: Optional[AccessScore] = Field(None, description="Computed access score")
    raw_text: Optional[str] = Field(None, description="Original parsed text")
    
    class Config:
        json_schema_extra = {
            "example": {
                "drug_name": "Ibrance",
                "form": "Oral Capsule",
                "type": "Brand",
                "tier": 5,
                "restrictions": ["PA", "DL", "QL"],
                "restriction_details": [
                    "Prior Authorization - Requires approval before coverage",
                    "Dispensing Limit - Limits on dispensing frequency",
                    "Quantity Limit - Limits on amount dispensed"
                ],
                "access_score": {
                    "score": 4,
                    "label": "Low",
                    "factors": {"tier_penalty": -3, "restriction_penalty": -6}
                }
            }
        }


class FormularyPlan(BaseModel):
    """Formulary plan model."""
    plan_id: str = Field(..., description="Unique plan identifier")
    plan_name: str = Field(..., description="Plan name")
    effective_date: Optional[datetime] = Field(None, description="Plan effective date")
    drugs: List[Drug] = Field(default_factory=list, description="List of drugs")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "plan_id": "plan_abc123",
                "plan_name": "Blue Cross PPO 2026",
                "drugs": [],
                "metadata": {"source_file": "formulary.pdf", "pages": 45}
            }
        }


class FormularySummary(BaseModel):
    """Summary statistics for a formulary."""
    total_drugs: int = Field(0, description="Total number of drugs")
    brand_count: int = Field(0, description="Number of brand drugs")
    generic_count: int = Field(0, description="Number of generic drugs")
    avg_tier: float = Field(0.0, description="Average tier")
    tier_distribution: Dict[int, int] = Field(default_factory=dict, description="Count per tier")
    pa_percentage: float = Field(0.0, description="% drugs requiring PA")
    ql_percentage: float = Field(0.0, description="% drugs with quantity limits")
    st_percentage: float = Field(0.0, description="% drugs with step therapy")
    dl_percentage: float = Field(0.0, description="% drugs with dispensing limits")
    high_restriction_drugs: int = Field(0, description="Drugs with 2+ restrictions")
    avg_access_score: float = Field(0.0, description="Average access score")
    access_distribution: Dict[str, int] = Field(default_factory=dict, description="Count per access label")


class FormularyInsights(BaseModel):
    """Insights generated from formulary analysis."""
    summary: FormularySummary = Field(..., description="Statistical summary")
    insights: List[str] = Field(default_factory=list, description="Generated insights")
    recommendations: List[str] = Field(default_factory=list, description="Recommendations")
    risk_factors: List[str] = Field(default_factory=list, description="Identified risks")


class DrugComparison(BaseModel):
    """Comparison of a drug across plans."""
    drug_name: str
    plan_a: Optional[Dict[str, Any]] = Field(None, description="Drug data in Plan A")
    plan_b: Optional[Dict[str, Any]] = Field(None, description="Drug data in Plan B")
    better_plan: Optional[Literal["A", "B", "Equal", "N/A"]] = None
    score_difference: int = 0
    notes: List[str] = Field(default_factory=list)


class ComparisonSummary(BaseModel):
    """Summary of plan comparison."""
    better_plan: Literal["A", "B", "Equal"]
    plan_a_avg_score: float
    plan_b_avg_score: float
    improvement_percentage: float
    drugs_better_in_a: int
    drugs_better_in_b: int
    drugs_equal: int
    drugs_only_in_a: int
    drugs_only_in_b: int


class PlanComparison(BaseModel):
    """Complete plan comparison result."""
    plan_a_name: str
    plan_b_name: str
    comparison: List[DrugComparison] = Field(default_factory=list)
    summary: ComparisonSummary
    insights: List[str] = Field(default_factory=list)


# Request/Response models for API
class FormularyUploadResponse(BaseModel):
    """Response for formulary upload."""
    success: bool
    plan_id: str
    plan_name: str
    drugs_extracted: int
    message: str
    processing_time_ms: float


class FormularyQueryRequest(BaseModel):
    """Request for querying formulary."""
    plan_id: str
    drug_name: Optional[str] = None
    tier: Optional[int] = None
    restrictions: Optional[List[str]] = None
    min_access_score: Optional[int] = None


class ComparisonRequest(BaseModel):
    """Request for plan comparison."""
    plan_a_id: str
    plan_b_id: str
    drug_names: Optional[List[str]] = Field(None, description="Specific drugs to compare")
