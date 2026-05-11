"""Insights Engine for Formulary Analytics.

Generates summary statistics and intelligent insights from drug data.
"""

from typing import List, Dict, Any, Optional
from collections import Counter
from loguru import logger

from app.formulary.models import (
    Drug, 
    DrugType, 
    AccessLabel,
    FormularySummary,
    FormularyInsights,
)


class InsightsEngine:
    """Engine for generating formulary insights and analytics."""
    
    # Thresholds for insight generation
    THRESHOLDS = {
        "high_pa_percentage": 50,      # >50% = high PA rate
        "high_restriction_count": 2,   # 2+ restrictions = high restriction
        "high_tier_threshold": 4,      # Tier 4+ = high tier
        "low_access_percentage": 30,   # >30% low access = concern
        "dominant_tier_percentage": 40, # >40% in one tier = dominant
    }
    
    def __init__(self, thresholds: Optional[Dict[str, Any]] = None):
        """Initialize insights engine."""
        self.thresholds = {**self.THRESHOLDS, **(thresholds or {})}
    
    def analyze(self, drugs: List[Drug]) -> FormularyInsights:
        """
        Generate complete insights for a list of drugs.
        
        Args:
            drugs: List of scored drugs
            
        Returns:
            FormularyInsights with summary, insights, and recommendations
        """
        if not drugs:
            return FormularyInsights(
                summary=FormularySummary(),
                insights=["No drugs to analyze"],
                recommendations=[],
                risk_factors=[]
            )
        
        # Compute summary statistics
        summary = self._compute_summary(drugs)
        
        # Generate insights
        insights = self._generate_insights(summary, drugs)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(summary, drugs)
        
        # Identify risk factors
        risk_factors = self._identify_risks(summary, drugs)
        
        logger.info(f"Generated insights for {summary.total_drugs} drugs")
        
        return FormularyInsights(
            summary=summary,
            insights=insights,
            recommendations=recommendations,
            risk_factors=risk_factors
        )
    
    def _compute_summary(self, drugs: List[Drug]) -> FormularySummary:
        """Compute summary statistics."""
        total = len(drugs)
        
        # Count by type
        brand_count = sum(1 for d in drugs if d.type == DrugType.BRAND)
        generic_count = sum(1 for d in drugs if d.type == DrugType.GENERIC)
        
        # Tier distribution
        tier_counter = Counter(d.tier for d in drugs)
        tier_distribution = dict(tier_counter)
        
        # Average tier
        avg_tier = sum(d.tier for d in drugs) / total if total > 0 else 0
        
        # Restriction percentages
        pa_count = sum(1 for d in drugs if "PA" in d.restrictions)
        ql_count = sum(1 for d in drugs if "QL" in d.restrictions)
        st_count = sum(1 for d in drugs if "ST" in d.restrictions)
        dl_count = sum(1 for d in drugs if "DL" in d.restrictions)
        
        pa_percentage = (pa_count / total * 100) if total > 0 else 0
        ql_percentage = (ql_count / total * 100) if total > 0 else 0
        st_percentage = (st_count / total * 100) if total > 0 else 0
        dl_percentage = (dl_count / total * 100) if total > 0 else 0
        
        # High restriction drugs (2+ restrictions)
        high_restriction_drugs = sum(
            1 for d in drugs 
            if len(d.restrictions) >= self.thresholds["high_restriction_count"]
        )
        
        # Access score distribution
        access_scores = [d.access_score.score for d in drugs if d.access_score]
        avg_access_score = sum(access_scores) / len(access_scores) if access_scores else 0
        
        access_labels = Counter(
            d.access_score.label.value for d in drugs if d.access_score
        )
        access_distribution = dict(access_labels)
        
        return FormularySummary(
            total_drugs=total,
            brand_count=brand_count,
            generic_count=generic_count,
            avg_tier=round(avg_tier, 2),
            tier_distribution=tier_distribution,
            pa_percentage=round(pa_percentage, 1),
            ql_percentage=round(ql_percentage, 1),
            st_percentage=round(st_percentage, 1),
            dl_percentage=round(dl_percentage, 1),
            high_restriction_drugs=high_restriction_drugs,
            avg_access_score=round(avg_access_score, 2),
            access_distribution=access_distribution,
        )
    
    def _generate_insights(self, summary: FormularySummary, drugs: List[Drug]) -> List[str]:
        """Generate analytical insights."""
        insights = []
        
        # Tier insights
        if summary.avg_tier >= 4:
            insights.append(
                f"High average tier ({summary.avg_tier:.1f}) indicates this formulary "
                f"favors cost containment over accessibility"
            )
        elif summary.avg_tier <= 2:
            insights.append(
                f"Low average tier ({summary.avg_tier:.1f}) indicates good drug accessibility"
            )
        
        # Check for dominant tier
        if summary.tier_distribution:
            max_tier = max(summary.tier_distribution.items(), key=lambda x: x[1])
            tier_percentage = (max_tier[1] / summary.total_drugs * 100) if summary.total_drugs > 0 else 0
            if tier_percentage > self.thresholds["dominant_tier_percentage"]:
                insights.append(
                    f"Tier {max_tier[0]} dominates with {tier_percentage:.0f}% of all drugs"
                )
        
        # Prior authorization insights
        if summary.pa_percentage >= self.thresholds["high_pa_percentage"]:
            insights.append(
                f"High prior authorization rate ({summary.pa_percentage:.0f}%) - "
                f"expect delays and administrative burden for most prescriptions"
            )
        elif summary.pa_percentage >= 30:
            insights.append(
                f"Moderate prior authorization requirements ({summary.pa_percentage:.0f}% of drugs)"
            )
        
        # Step therapy insights
        if summary.st_percentage >= 20:
            insights.append(
                f"Step therapy required for {summary.st_percentage:.0f}% of drugs - "
                f"patients may need to try alternative medications first"
            )
        
        # Quantity limits
        if summary.ql_percentage >= 40:
            insights.append(
                f"Widespread quantity limits ({summary.ql_percentage:.0f}%) may affect chronic condition management"
            )
        
        # High restriction drugs
        high_restriction_pct = (summary.high_restriction_drugs / summary.total_drugs * 100) if summary.total_drugs > 0 else 0
        if high_restriction_pct >= 30:
            insights.append(
                f"{summary.high_restriction_drugs} drugs ({high_restriction_pct:.0f}%) have multiple restrictions"
            )
        
        # Access score insights
        if summary.access_distribution:
            low_access = summary.access_distribution.get("Low", 0)
            low_pct = (low_access / summary.total_drugs * 100) if summary.total_drugs > 0 else 0
            
            if low_pct >= self.thresholds["low_access_percentage"]:
                insights.append(
                    f"Overall access is limited - {low_pct:.0f}% of drugs have low access scores"
                )
            
            high_access = summary.access_distribution.get("High", 0)
            high_pct = (high_access / summary.total_drugs * 100) if summary.total_drugs > 0 else 0
            if high_pct >= 40:
                insights.append(
                    f"Good accessibility - {high_pct:.0f}% of drugs have high access scores"
                )
        
        # Brand vs Generic
        if summary.total_drugs > 0:
            generic_pct = (summary.generic_count / summary.total_drugs * 100)
            if generic_pct >= 70:
                insights.append(
                    f"Formulary favors generics ({generic_pct:.0f}%), which typically means lower costs"
                )
            elif summary.brand_count > summary.generic_count:
                insights.append(
                    f"Higher proportion of brand drugs may indicate higher overall costs"
                )
        
        # Ensure we have at least one insight
        if not insights:
            insights.append(
                f"Formulary contains {summary.total_drugs} drugs with average tier of {summary.avg_tier:.1f}"
            )
        
        return insights
    
    def _generate_recommendations(self, summary: FormularySummary, drugs: List[Drug]) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []
        
        # PA-related recommendations
        if summary.pa_percentage >= 50:
            recommendations.append(
                "Consider proactive prior authorization submission for commonly prescribed medications"
            )
        
        # Step therapy recommendations
        if summary.st_percentage >= 20:
            recommendations.append(
                "Document patient's medication history to expedite step therapy exceptions when clinically appropriate"
            )
        
        # High restriction recommendations
        if summary.high_restriction_drugs > 10:
            recommendations.append(
                "Review high-restriction drugs with patients to set expectations and plan alternatives"
            )
        
        # Low access recommendations
        low_access_count = summary.access_distribution.get("Low", 0)
        if low_access_count > summary.total_drugs * 0.3:
            recommendations.append(
                "Consider formulary alternatives for drugs with low access scores where clinically appropriate"
            )
        
        # Generic recommendations
        if summary.brand_count > summary.generic_count:
            recommendations.append(
                "Evaluate generic alternatives to reduce costs and improve access"
            )
        
        return recommendations
    
    def _identify_risks(self, summary: FormularySummary, drugs: List[Drug]) -> List[str]:
        """Identify potential risk factors."""
        risks = []
        
        # Access risks
        if summary.avg_access_score < 5:
            risks.append("LOW OVERALL ACCESS: Average access score below 5 indicates significant barriers")
        
        # PA burden
        if summary.pa_percentage >= 70:
            risks.append("HIGH ADMINISTRATIVE BURDEN: >70% PA rate may cause treatment delays")
        
        # Step therapy risks
        if summary.st_percentage >= 30:
            risks.append("TREATMENT DELAYS: High step therapy requirements may delay optimal treatment")
        
        # Tier concentration
        tier_5_6_count = summary.tier_distribution.get(5, 0) + summary.tier_distribution.get(6, 0)
        if tier_5_6_count > summary.total_drugs * 0.4:
            risks.append("HIGH COST EXPOSURE: >40% of drugs in highest tiers (5-6)")
        
        return risks
    
    def get_drug_insights(self, drug: Drug) -> Dict[str, Any]:
        """Get insights for a specific drug."""
        if not drug.access_score:
            return {"drug_name": drug.drug_name, "insight": "Not scored"}
        
        insights = {
            "drug_name": drug.drug_name,
            "access_level": drug.access_score.label.value,
            "score": drug.access_score.score,
            "concerns": [],
            "positives": [],
        }
        
        # Concerns
        if drug.tier >= 4:
            insights["concerns"].append(f"High tier ({drug.tier}) - higher out-of-pocket costs")
        
        if "PA" in drug.restrictions:
            insights["concerns"].append("Requires prior authorization - expect processing delays")
        
        if "ST" in drug.restrictions:
            insights["concerns"].append("Step therapy required - must try other drugs first")
        
        if len(drug.restrictions) >= 3:
            insights["concerns"].append("Multiple restrictions may complicate access")
        
        # Positives
        if drug.tier <= 2:
            insights["positives"].append(f"Low tier ({drug.tier}) - better coverage")
        
        if not drug.restrictions:
            insights["positives"].append("No restrictions - straightforward access")
        
        if drug.type == DrugType.GENERIC:
            insights["positives"].append("Generic - typically lower cost")
        
        return insights


# Singleton instance
_engine_instance: Optional[InsightsEngine] = None


def get_insights_engine(thresholds: Optional[Dict[str, Any]] = None) -> InsightsEngine:
    """Get or create insights engine instance."""
    global _engine_instance
    if _engine_instance is None or thresholds:
        _engine_instance = InsightsEngine(thresholds)
    return _engine_instance
