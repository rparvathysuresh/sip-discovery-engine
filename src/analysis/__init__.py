"""
Analysis package for the SIP Discovery Engine.
Provides theme clustering, opportunity scoring, segment aggregation,
and continuer vs. dropper comparison.
"""

from src.analysis.continuer_dropper_comparator import ContinuerDropperComparator
from src.analysis.opportunity_scorer import OpportunityScorer
from src.analysis.segment_aggregator import SegmentAggregator
from src.analysis.theme_clusterer import ThemeClusterer

__all__ = [
    "ThemeClusterer",
    "OpportunityScorer",
    "SegmentAggregator",
    "ContinuerDropperComparator",
]
