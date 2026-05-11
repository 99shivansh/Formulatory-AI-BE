"""Comparison Engine for Plan Analysis.

Compares drug coverage across different formulary plans.
"""

from typing import List, Dict, Any, Optional, Literal
from loguru import logger

from app.formulary.models import (
    Drug,
    FormularyPlan,
    DrugComparison,
    ComparisonSummary,
    PlanComparison,
    AccessLabel,
)


class ComparisonEngine:
    """Engine for comparing formulary plans."""
    
    def __init__(self):
        """Initialize comparison engine."""
        pass
    
    def compare_plans(
        self,
        plan_a: FormularyPlan,
        plan_b: FormularyPlan,
        drug_names: Optional[List[str]] = None,
    ) -> PlanComparison:
        """
        Compare two formulary plans.
        
        Args:
            plan_a: First plan
            plan_b: Second plan
            drug_names: Optional list of specific drugs to compare
            
        Returns:
            PlanComparison with detailed comparison
        """
        # Build drug lookup dictionaries (case-insensitive)
        drugs_a = {d.drug_name.lower().strip(): d for d in plan_a.drugs}
        drugs_b = {d.drug_name.lower().strip(): d for d in plan_b.drugs}
        
        # Get all unique drug names
        if drug_names:
            all_drugs = set(name.lower().strip() for name in drug_names)
        else:
            all_drugs = set(drugs_a.keys()) | set(drugs_b.keys())
        
        # Compare each drug
        comparisons = []
        better_in_a = 0
        better_in_b = 0
        equal = 0
        only_in_a = 0
        only_in_b = 0
        
        scores_a = []
        scores_b = []
        
        for drug_name in sorted(all_drugs):
            drug_a = drugs_a.get(drug_name)
            drug_b = drugs_b.get(drug_name)
            
            comparison = self._compare_drug(drug_name, drug_a, drug_b)
            comparisons.append(comparison)
            
            # Track statistics
            if comparison.better_plan == "A":
                better_in_a += 1
            elif comparison.better_plan == "B":
                better_in_b += 1
            elif comparison.better_plan == "Equal":
                equal += 1
            
            if drug_a and not drug_b:
                only_in_a += 1
            elif drug_b and not drug_a:
                only_in_b += 1
            
            # Track scores for average
            if drug_a and drug_a.access_score:
                scores_a.append(drug_a.access_score.score)
            if drug_b and drug_b.access_score:
                scores_b.append(drug_b.access_score.score)
        
        # Calculate averages
        avg_a = sum(scores_a) / len(scores_a) if scores_a else 0
        avg_b = sum(scores_b) / len(scores_b) if scores_b else 0
        
        # Determine overall better plan
        if avg_a > avg_b + 0.5:
            overall_better = "A"
        elif avg_b > avg_a + 0.5:
            overall_better = "B"
        else:
            overall_better = "Equal"
        
        # Calculate improvement percentage
        if avg_a > 0 and avg_b > 0:
            if overall_better == "A":
                improvement = ((avg_a - avg_b) / avg_b) * 100
            elif overall_better == "B":
                improvement = ((avg_b - avg_a) / avg_a) * 100
            else:
                improvement = 0
        else:
            improvement = 0
        
        # Create summary
        summary = ComparisonSummary(
            better_plan=overall_better,
            plan_a_avg_score=round(avg_a, 2),
            plan_b_avg_score=round(avg_b, 2),
            improvement_percentage=round(abs(improvement), 1),
            drugs_better_in_a=better_in_a,
            drugs_better_in_b=better_in_b,
            drugs_equal=equal,
            drugs_only_in_a=only_in_a,
            drugs_only_in_b=only_in_b,
        )
        
        # Generate comparison insights
        insights = self._generate_comparison_insights(
            plan_a, plan_b, summary, comparisons
        )
        
        logger.info(
            f"Compared {len(comparisons)} drugs between {plan_a.plan_name} and {plan_b.plan_name}"
        )
        
        return PlanComparison(
            plan_a_name=plan_a.plan_name,
            plan_b_name=plan_b.plan_name,
            comparison=comparisons,
            summary=summary,
            insights=insights,
        )
    
    def _compare_drug(
        self,
        drug_name: str,
        drug_a: Optional[Drug],
        drug_b: Optional[Drug],
    ) -> DrugComparison:
        """Compare a single drug across two plans."""
        notes = []
        
        # Build plan data
        plan_a_data = None
        plan_b_data = None
        
        if drug_a:
            plan_a_data = {
                "tier": drug_a.tier,
                "score": drug_a.access_score.score if drug_a.access_score else None,
                "label": drug_a.access_score.label.value if drug_a.access_score else None,
                "restrictions": drug_a.restrictions,
                "type": drug_a.type.value,
            }
        else:
            notes.append("Not covered in Plan A")
        
        if drug_b:
            plan_b_data = {
                "tier": drug_b.tier,
                "score": drug_b.access_score.score if drug_b.access_score else None,
                "label": drug_b.access_score.label.value if drug_b.access_score else None,
                "restrictions": drug_b.restrictions,
                "type": drug_b.type.value,
            }
        else:
            notes.append("Not covered in Plan B")
        
        # Determine better plan
        better_plan: Literal["A", "B", "Equal", "N/A"]
        score_diff = 0
        
        if drug_a and drug_b:
            score_a = drug_a.access_score.score if drug_a.access_score else 0
            score_b = drug_b.access_score.score if drug_b.access_score else 0
            score_diff = score_a - score_b
            
            if score_diff > 1:
                better_plan = "A"
                notes.append(f"Plan A has better access (score +{score_diff})")
            elif score_diff < -1:
                better_plan = "B"
                notes.append(f"Plan B has better access (score +{abs(score_diff)})")
            else:
                better_plan = "Equal"
                notes.append("Similar access in both plans")
            
            # Additional comparison notes
            if drug_a.tier != drug_b.tier:
                tier_diff = drug_a.tier - drug_b.tier
                if tier_diff > 0:
                    notes.append(f"Lower tier in Plan B (Tier {drug_b.tier} vs {drug_a.tier})")
                else:
                    notes.append(f"Lower tier in Plan A (Tier {drug_a.tier} vs {drug_b.tier})")
            
            # Restriction comparison
            restrictions_a = set(drug_a.restrictions)
            restrictions_b = set(drug_b.restrictions)
            
            only_a_restrictions = restrictions_a - restrictions_b
            only_b_restrictions = restrictions_b - restrictions_a
            
            if only_a_restrictions:
                notes.append(f"Additional restrictions in Plan A: {', '.join(only_a_restrictions)}")
            if only_b_restrictions:
                notes.append(f"Additional restrictions in Plan B: {', '.join(only_b_restrictions)}")
                
        elif drug_a and not drug_b:
            better_plan = "A"
            notes.append("Only covered in Plan A")
        elif drug_b and not drug_a:
            better_plan = "B"
            notes.append("Only covered in Plan B")
        else:
            better_plan = "N/A"
            notes.append("Not covered in either plan")
        
        # Get display name (from whichever plan has it)
        display_name = drug_name
        if drug_a:
            display_name = drug_a.drug_name
        elif drug_b:
            display_name = drug_b.drug_name
        
        return DrugComparison(
            drug_name=display_name,
            plan_a=plan_a_data,
            plan_b=plan_b_data,
            better_plan=better_plan,
            score_difference=score_diff,
            notes=notes,
        )
    
    def _generate_comparison_insights(
        self,
        plan_a: FormularyPlan,
        plan_b: FormularyPlan,
        summary: ComparisonSummary,
        comparisons: List[DrugComparison],
    ) -> List[str]:
        """Generate insights from comparison."""
        insights = []
        
        # Overall winner insight
        if summary.better_plan == "A":
            insights.append(
                f"{plan_a.plan_name} provides better overall drug access "
                f"(avg score {summary.plan_a_avg_score} vs {summary.plan_b_avg_score})"
            )
        elif summary.better_plan == "B":
            insights.append(
                f"{plan_b.plan_name} provides better overall drug access "
                f"(avg score {summary.plan_b_avg_score} vs {summary.plan_a_avg_score})"
            )
        else:
            insights.append(
                f"Both plans offer similar drug access "
                f"(avg scores: {summary.plan_a_avg_score} vs {summary.plan_b_avg_score})"
            )
        
        # Improvement insight
        if summary.improvement_percentage >= 10:
            better_name = plan_a.plan_name if summary.better_plan == "A" else plan_b.plan_name
            insights.append(
                f"{better_name} offers {summary.improvement_percentage:.0f}% better access scores on average"
            )
        
        # Coverage differences
        if summary.drugs_only_in_a > 0:
            insights.append(
                f"{summary.drugs_only_in_a} drug(s) covered only in {plan_a.plan_name}"
            )
        if summary.drugs_only_in_b > 0:
            insights.append(
                f"{summary.drugs_only_in_b} drug(s) covered only in {plan_b.plan_name}"
            )
        
        # Breakdown of better coverage
        total_compared = summary.drugs_better_in_a + summary.drugs_better_in_b + summary.drugs_equal
        if total_compared > 0:
            insights.append(
                f"Of {total_compared} comparable drugs: "
                f"{summary.drugs_better_in_a} better in {plan_a.plan_name}, "
                f"{summary.drugs_better_in_b} better in {plan_b.plan_name}, "
                f"{summary.drugs_equal} equal"
            )
        
        # Find drugs with biggest differences
        significant_diffs = [
            c for c in comparisons 
            if abs(c.score_difference) >= 5 and c.plan_a and c.plan_b
        ]
        
        if significant_diffs:
            insights.append(
                f"{len(significant_diffs)} drug(s) have significant access differences (5+ score gap)"
            )
            
            # Highlight top differences
            sorted_diffs = sorted(significant_diffs, key=lambda x: abs(x.score_difference), reverse=True)
            for comp in sorted_diffs[:3]:
                better = plan_a.plan_name if comp.score_difference > 0 else plan_b.plan_name
                insights.append(
                    f"  • {comp.drug_name}: Much better in {better} (score diff: {abs(comp.score_difference)})"
                )
        
        return insights
    
    def get_drug_comparison_detail(
        self,
        drug_name: str,
        plan_a: FormularyPlan,
        plan_b: FormularyPlan,
    ) -> Dict[str, Any]:
        """Get detailed comparison for a specific drug."""
        drugs_a = {d.drug_name.lower(): d for d in plan_a.drugs}
        drugs_b = {d.drug_name.lower(): d for d in plan_b.drugs}
        
        drug_a = drugs_a.get(drug_name.lower())
        drug_b = drugs_b.get(drug_name.lower())
        
        comparison = self._compare_drug(drug_name, drug_a, drug_b)
        
        return {
            "drug_name": drug_name,
            "comparison": comparison.model_dump(),
            "recommendation": self._get_drug_recommendation(comparison, plan_a.plan_name, plan_b.plan_name),
        }
    
    def _get_drug_recommendation(
        self,
        comparison: DrugComparison,
        plan_a_name: str,
        plan_b_name: str,
    ) -> str:
        """Get recommendation for a specific drug comparison."""
        if comparison.better_plan == "A":
            return f"Choose {plan_a_name} for better access to {comparison.drug_name}"
        elif comparison.better_plan == "B":
            return f"Choose {plan_b_name} for better access to {comparison.drug_name}"
        elif comparison.better_plan == "Equal":
            return f"Both plans offer similar access to {comparison.drug_name}"
        else:
            return f"{comparison.drug_name} is not covered in either plan - consider alternatives"


# Singleton instance
_engine_instance: Optional[ComparisonEngine] = None


def get_comparison_engine() -> ComparisonEngine:
    """Get or create comparison engine instance."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = ComparisonEngine()
    return _engine_instance
