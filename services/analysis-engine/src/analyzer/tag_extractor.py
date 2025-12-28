"""Tag extraction module for categorizing feedback."""
import re
from typing import List, Set


class TagExtractor:
    """Extracts category tags from feedback text."""

    def __init__(self):
        """Initialize tag extractor with keyword mappings."""
        self.tag_keywords = {
            'bug': [
                r'\b(bug|error|crash|broken|issue|problem|fail|glitch|defect)\b',
                r'\b(doesn\'t work|not working|won\'t work|can\'t)\b',
            ],
            'performance': [
                r'\b(slow|lag|loading|speed|performance|timeout|freeze|hang)\b',
                r'\b(takes forever|too long|wait)\b',
            ],
            'ui-ux': [
                r'\b(ui|ux|design|interface|layout|confusing|unintuitive)\b',
                r'\b(hard to use|difficult|complicated|user experience)\b',
            ],
            'feature-request': [
                r'\b(would like|wish|hope|want|need|add|implement|feature)\b',
                r'\b(could you|can you|please add|suggestion)\b',
            ],
            'mobile': [
                r'\b(mobile|app|ios|android|phone|tablet|smartphone)\b',
            ],
            'web': [
                r'\b(website|web|browser|desktop|online)\b',
            ],
            'security': [
                r'\b(security|privacy|password|login|authentication|permission)\b',
                r'\b(unauthorized|hack|breach)\b',
            ],
            'pricing': [
                r'\b(price|pricing|cost|expensive|cheap|subscription|payment|billing)\b',
            ],
            'support': [
                r'\b(support|help|customer service|response|reply)\b',
            ],
            'documentation': [
                r'\b(documentation|docs|guide|tutorial|help|instructions)\b',
            ],
            'integration': [
                r'\b(integration|integrate|api|connect|sync|import|export)\b',
            ],
            'data': [
                r'\b(data|database|export|import|backup|restore|migration)\b',
            ],
            'notification': [
                r'\b(notification|alert|email|push|reminder)\b',
            ],
            'search': [
                r'\b(search|find|filter|sort)\b',
            ],
            'accessibility': [
                r'\b(accessibility|accessible|screen reader|keyboard|contrast)\b',
            ],
        }

    def extract_tags(self, text: str, max_tags: int = 5) -> List[str]:
        """
        Extract relevant category tags from feedback text.

        Args:
            text: Feedback text to analyze
            max_tags: Maximum number of tags to return

        Returns:
            List of extracted tags
        """
        text_lower = text.lower()
        found_tags: Set[str] = set()

        # Check each tag category
        for tag, patterns in self.tag_keywords.items():
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    found_tags.add(tag)
                    break  # One match per tag is enough

        # Convert to sorted list and limit to max_tags
        tags_list = sorted(list(found_tags))[:max_tags]

        return tags_list

    def get_tag_display_name(self, tag: str) -> str:
        """
        Get display-friendly name for a tag.

        Args:
            tag: Tag identifier

        Returns:
            Display name
        """
        display_names = {
            'bug': 'Bug',
            'performance': 'Performance',
            'ui-ux': 'UI/UX',
            'feature-request': 'Feature Request',
            'mobile': 'Mobile',
            'web': 'Web',
            'security': 'Security',
            'pricing': 'Pricing',
            'support': 'Support',
            'documentation': 'Documentation',
            'integration': 'Integration',
            'data': 'Data',
            'notification': 'Notification',
            'search': 'Search',
            'accessibility': 'Accessibility',
        }

        return display_names.get(tag, tag.title())

    def get_tag_color(self, tag: str) -> str:
        """
        Get color scheme for a tag (for UI display).

        Args:
            tag: Tag identifier

        Returns:
            Color name (tailwind-compatible)
        """
        color_map = {
            'bug': 'red',
            'performance': 'orange',
            'ui-ux': 'purple',
            'feature-request': 'blue',
            'mobile': 'green',
            'web': 'indigo',
            'security': 'yellow',
            'pricing': 'pink',
            'support': 'cyan',
            'documentation': 'gray',
            'integration': 'teal',
            'data': 'violet',
            'notification': 'amber',
            'search': 'lime',
            'accessibility': 'emerald',
        }

        return color_map.get(tag, 'gray')
