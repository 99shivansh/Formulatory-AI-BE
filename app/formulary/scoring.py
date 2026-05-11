"""Scoring Engine for Access Intelligence.

Computes access scores and labels for drugs based on:
- Tier (lower is better)
- Restrictions (fewer is better)
- Drug type (generic typically better access)
"""

from typing import List, Dict, Any, Optional
from loguru import logger

from app.formulary.models import Drug, AccessScore, AccessLabel, DrugType


class ScoringEngine:
    """Engine for computing drug access scores."""
    
    # Scoring configuration (easily customizable)
    DEFAULT_CONFIG = {
        # Base score
        "base_score": 10,
        
        # Tier adjustments
        "tier_bonuses": {
            1: 5,   # Tier 1: +5 (best access)
            2: 3,   # Tier 2: +3
            3: 1,   # Tier 3: +1
            4: -1,  # Tier 4: -1
            5: -3,  # Tier 5: -3
            6: -5,  # Tier 6: -5 (worst access)
        },
        
        # Restriction penalties
        "restriction_penalty": -2,  # Per restriction
        
        # Specific restriction penalties (additional)
        "restriction_specific": {
            "PA": -1,  # Prior auth is particularly burdensome
            "ST": -1,  # Step therapy adds delay
        },
        
        # Type adjustments
        "type_adjustments": {
            "Generic": 1,   # Generics typically easier access
            "Brand": 0,
            "Unknown": 0,
        },
        
        # Score bounds
        "min_score": 0,
        "max_score": 15,
        
        # Label thresholds
        "label_thresholds": {
            "low": 4,      # 0-4: Low access
            "medium": 8,   # 5-8: Medium access
            # 9+: High access
        }
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize scoring engine.
        
        Args:
            config: Optional custom configuration
        """
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}
    
    def score_drug(self, drug: Drug) -> Drug:
        """
        Compute access score for a single drug.
        
        Args:
            drug: Drug to score
            
        Returns:
            Drug with access_score populated
        """
        factors = {}
        score = self.config["base_score"]
        factors["base"] = self.config["base_score"]
        
        # Tier adjustment
        tier_bonus = self.config["tier_bonuses"].get(drug.tier, 0)
        score += tier_bonus
        factors["tier_adjustment"] = tier_bonus
        factors["tier"] = drug.tier
        
        # Restriction penalties
        restriction_penalty = len(drug.restrictions) * self.config["restriction_penalty"]
        score += restriction_penalty
        factors["restriction_count"] = len(drug.restrictions)
        factors["restriction_penalty"] = restriction_penalty
        
        # Additional penalties for specific restrictions
        specific_penalty = 0
        for restriction in drug.restrictions:
            specific_penalty += self.config["restriction_specific"].get(restriction, 0)
        score += specific_penalty
        if specific_penalty != 0:
            factors["specific_restriction_penalty"] = specific_penalty
        
        # Type adjustment
        type_adj = self.config["type_adjustments"].get(drug.type.value, 0)
        score += type_adj
        if type_adj != 0:
            factors["type_adjustment"] = type_adj
        
        # Clamp score
        score = max(self.config["min_score"], min(self.config["max_score"], score))
        factors["final_score"] = score
        
        # Determine label
        label = self._get_label(score)
        
        # Create access score
        drug.access_score = AccessScore(
            score=score,
            label=label,
            factors=factors
        )
        
        return drug
    
    def score_drugs(self, drugs: List[Drug]) -> List[Drug]:
        """
        Score multiple drugs.
        
        Args:
            drugs: List of drugs to score
            
        Returns:
            List of drugs with access scores
        """
        scored_drugs = []
        for drug in drugs:
            scored_drug = self.score_drug(drug)
            scored_drugs.append(scored_drug)
        
        logger.info(f"Scored {len(scored_drugs)} drugs")
        return scored_drugs
    
    def _get_label(self, score: int) -> AccessLabel:
        """Determine access label from score."""
        if score <= self.config["label_thresholds"]["low"]:
            return AccessLabel.LOW
        elif score <= self.config["label_thresholds"]["medium"]:
            return AccessLabel.MEDIUM
        else:
            return AccessLabel.HIGH
    
    def get_score_explanation(self, drug: Drug) -> str:
        """
        Generate human-readable explanation of score.
        
        Args:
            drug: Scored drug
            
        Returns:
            Explanation string
        """
        if not drug.access_score:
            return "Not scored"
        
        score = drug.access_score
        factors = score.factors
        
        explanation_parts = [
            f"Access Score: {score.score}/15 ({score.label.value})",
            f"",
            f"Score Breakdown:",
            f"  • Base score: {factors.get('base', 10)}",
            f"  • Tier {factors.get('tier', '?')} adjustment: {factors.get('tier_adjustment', 0):+d}",
        ]
        
        if factors.get('restriction_count', 0) > 0:
            explanation_parts.append(
                f"  • {factors.get('restriction_count', 0)} restriction(s): {factors.get('restriction_penalty', 0):+d}"
            )
        
        if factors.get('specific_restriction_penalty'):
            explanation_parts.append(
                f"  • Specific restriction penalty: {factors.get('specific_restriction_penalty'):+d}"
            )
        
        if factors.get('type_adjustment'):
            explanation_parts.append(
                f"  • Drug type ({drug.type.value}): {factors.get('type_adjustment'):+d}"
            )
        
        explanation_parts.append(f"")
        explanation_parts.append(f"Final Score: {score.score}")
        
        return "\n".join(explanation_parts)
    
    def reconfigure(self, new_config: Dict[str, Any]) -> None:
        """Update scoring configuration."""
        self.config.update(new_config)
        logger.info("Scoring engine reconfigured")


# Singleton instance
_engine_instance: Optional[ScoringEngine] = None


def get_scoring_engine(config: Optional[Dict[str, Any]] = None) -> ScoringEngine:
    """Get or create scoring engine instance."""
    global _engine_instance
    if _engine_instance is None or config:
        _engine_instance = ScoringEngine(config)
    return _engine_instance
