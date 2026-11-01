"""
Collectors package — Source connectors for public data collection.
"""

from src.collectors.base_collector import BaseCollector, detect_platforms
from src.collectors.playstore_collector import PlayStoreCollector
from src.collectors.appstore_collector import AppStoreCollector
from src.collectors.reddit_collector import RedditCollector
from src.collectors.youtube_collector import YouTubeCollector
from src.collectors.forum_collector import ForumCollector
from src.collectors.quora_collector import QuoraCollector

__all__ = [
    "BaseCollector",
    "detect_platforms",
    "PlayStoreCollector",
    "AppStoreCollector",
    "RedditCollector",
    "YouTubeCollector",
    "ForumCollector",
    "QuoraCollector",
]
