"""Extractors for pain points, feature requests, and patterns."""
import re
from typing import List, Dict, Tuple, Set
from collections import defaultdict, Counter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np


class PainPointExtractor:
    """Extracts and clusters customer pain points and complaints."""

    def __init__(self):
        """Initialize pain point extractor."""
        # Patterns that indicate complaints or problems
        self.complaint_patterns = [
            # Direct problem statements
            r'\b(crash(?:es|ing|ed)?|bug(?:gy)?|broken|not\s+work(?:ing)?|fail(?:s|ing|ed)?)\b',
            r'\b(error(?:s)?|issue(?:s)?|problem(?:s)?)\b',
            r'\b(slow|lag(?:gy|ging)?|freeze(?:s)?|hang(?:s|ing)?)\b',

            # Difficulty/frustration
            r'\b(difficult|hard|confus(?:ing|ed)|complicated)\b',
            r'\b(frustrat(?:ing|ed)|annoying|irritating)\b',
            r'\b(can\'?t|cannot|unable|impossible)\b',

            # Negative expressions
            r'\b(hate|dislike|terrible|awful|worst|horrible|bad)\b',
            r'\b(disappoint(?:ed|ing)|unsatisf(?:ied|actory))\b',

            # Missing/lacking
            r'\b(missing|lack(?:s|ing)?|doesn\'?t\s+have|no\s+way\s+to)\b',
            r'\b(need(?:s)?\s+to\s+fix|should\s+fix)\b',
        ]

        # Words that intensify complaints
        self.intensifiers = {
            'always', 'constantly', 'every time', 'never', 'still',
            'keeps', 'keeps on', 'repeatedly', 'again and again'
        }

    def extract(self, feedback_items: List[Dict]) -> List[Dict]:
        """
        Extract pain points from feedback.

        Args:
            feedback_items: List of feedback dictionaries with 'id', 'text', 'sentiment'

        Returns:
            List of pain point dictionaries with issue, count, examples
        """
        complaints = []

        for item in feedback_items:
            text = item['text']
            sentiment = item.get('sentiment', {})

            # Check if this is a complaint
            is_complaint = self._is_complaint(text, sentiment)

            if is_complaint:
                # Extract the core issue
                issue_description = self._extract_issue(text)

                complaints.append({
                    'id': item['id'],
                    'text': text,
                    'issue': issue_description,
                    'full_text': text
                })

        # Cluster similar complaints
        clustered = self._cluster_complaints(complaints)

        return clustered

    def _is_complaint(self, text: str, sentiment: Dict) -> bool:
        """Check if feedback text is a complaint."""
        text_lower = text.lower()

        # Check sentiment
        if sentiment.get('label') == 'negative' or sentiment.get('compound', 0) < -0.05:
            return True

        # Check for complaint patterns
        for pattern in self.complaint_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True

        return False

    def _extract_issue(self, text: str) -> str:
        """Extract the core issue from complaint text."""
        # Simple extraction - just return cleaned text for now
        # In a more advanced version, could use NER or dependency parsing
        cleaned = text.strip()

        # Limit length for issue description
        if len(cleaned) > 100:
            cleaned = cleaned[:97] + '...'

        return cleaned

    def _cluster_complaints(self, complaints: List[Dict], similarity_threshold: float = 0.6) -> List[Dict]:
        """
        Cluster similar complaints together.

        Args:
            complaints: List of complaint dictionaries
            similarity_threshold: Cosine similarity threshold for clustering

        Returns:
            List of clustered pain points
        """
        if not complaints:
            return []

        # Create TF-IDF vectors
        texts = [c['issue'] for c in complaints]
        vectorizer = TfidfVectorizer(
            max_features=100,
            stop_words='english',
            ngram_range=(1, 2)
        )

        try:
            tfidf_matrix = vectorizer.fit_transform(texts)
        except ValueError:
            # Not enough data for vectorization
            return self._simple_clustering(complaints)

        # Compute similarity matrix
        similarity_matrix = cosine_similarity(tfidf_matrix)

        # Simple clustering: group similar items
        clusters = []
        assigned = set()

        for i in range(len(complaints)):
            if i in assigned:
                continue

            # Start new cluster
            cluster_items = [complaints[i]]
            assigned.add(i)

            # Find similar items
            for j in range(i + 1, len(complaints)):
                if j in assigned:
                    continue

                if similarity_matrix[i][j] >= similarity_threshold:
                    cluster_items.append(complaints[j])
                    assigned.add(j)

            # Create cluster summary
            cluster_label = self._generate_cluster_label(cluster_items)
            examples = [item['full_text'][:100] for item in cluster_items[:3]]

            clusters.append({
                'issue': cluster_label,
                'count': len(cluster_items),
                'examples': examples
            })

        # Sort by frequency
        clusters.sort(key=lambda x: x['count'], reverse=True)

        return clusters

    def _simple_clustering(self, complaints: List[Dict]) -> List[Dict]:
        """Simple keyword-based clustering fallback."""
        keyword_groups = defaultdict(list)

        for complaint in complaints:
            # Extract key terms
            text_lower = complaint['text'].lower()
            key = None

            # Try to find a key term
            if 'crash' in text_lower:
                key = 'App crashes'
            elif 'slow' in text_lower or 'lag' in text_lower:
                key = 'Performance issues'
            elif 'bug' in text_lower or 'error' in text_lower:
                key = 'Bugs and errors'
            elif 'confus' in text_lower or 'difficult' in text_lower:
                key = 'Usability issues'
            else:
                key = 'Other issues'

            keyword_groups[key].append(complaint)

        # Convert to output format
        result = []
        for label, items in keyword_groups.items():
            examples = [item['text'][:100] for item in items[:3]]
            result.append({
                'issue': label,
                'count': len(items),
                'examples': examples
            })

        result.sort(key=lambda x: x['count'], reverse=True)
        return result

    def _generate_cluster_label(self, cluster_items: List[Dict]) -> str:
        """Generate a descriptive label for a cluster."""
        # Use the most common words in the cluster
        all_text = ' '.join([item['text'].lower() for item in cluster_items])

        # Extract common phrases
        words = re.findall(r'\b\w+\b', all_text)
        word_counts = Counter(words)

        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'may', 'might', 'can', 'this', 'that', 'it', 'its', 'i', 'me', 'my', 'we', 'our'}

        meaningful_words = [(word, count) for word, count in word_counts.most_common(10)
                           if word not in stop_words and len(word) > 3]

        if meaningful_words:
            # Use top 2-3 words to create label
            top_words = [word for word, _ in meaningful_words[:3]]
            label = ' '.join(top_words).title()

            # Add context
            if len(label) < 30:
                # Use first complaint as template
                first_text = cluster_items[0]['text']
                if len(first_text) < 60:
                    return first_text
                else:
                    return first_text[:57] + '...'

            return label
        else:
            # Fallback to first item
            return cluster_items[0]['issue']


class FeatureRequestExtractor:
    """Extracts and clusters feature requests from feedback."""

    def __init__(self):
        """Initialize feature request extractor."""
        # Patterns indicating feature requests
        self.request_patterns = [
            r'\b(wish|hope|want|would\s+like|would\s+love)\b',
            r'\b(please\s+(?:add|include|give|provide))\b',
            r'\b(need(?:s)?|require(?:s)?)\s+(?:a|an|the|to)?\s*\w+',
            r'\b(could\s+you|can\s+you|will\s+you)\s+(?:add|include|make)\b',
            r'\b(should\s+(?:add|have|include))\b',
            r'\b(missing|lack(?:s|ing)?|no\s+way\s+to|doesn\'?t\s+have)\b',
            r'\b(feature\s+request|suggestion)\b',
            r'\b(it\s+would\s+be\s+(?:great|nice|helpful|useful))\b',
        ]

    def extract(self, feedback_items: List[Dict]) -> List[Dict]:
        """
        Extract feature requests from feedback.

        Args:
            feedback_items: List of feedback dictionaries

        Returns:
            List of feature request dictionaries
        """
        requests = []

        for item in feedback_items:
            text = item['text']

            if self._is_feature_request(text):
                feature_desc = self._extract_feature(text)

                requests.append({
                    'id': item['id'],
                    'text': text,
                    'feature': feature_desc,
                    'full_text': text
                })

        # Cluster similar requests
        clustered = self._cluster_requests(requests)

        return clustered

    def _is_feature_request(self, text: str) -> bool:
        """Check if text contains a feature request."""
        text_lower = text.lower()

        for pattern in self.request_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True

        return False

    def _extract_feature(self, text: str) -> str:
        """Extract feature description from request text."""
        # Simple extraction
        cleaned = text.strip()

        if len(cleaned) > 100:
            cleaned = cleaned[:97] + '...'

        return cleaned

    def _cluster_requests(self, requests: List[Dict], similarity_threshold: float = 0.6) -> List[Dict]:
        """Cluster similar feature requests."""
        if not requests:
            return []

        # Similar to pain point clustering
        texts = [r['feature'] for r in requests]
        vectorizer = TfidfVectorizer(
            max_features=100,
            stop_words='english',
            ngram_range=(1, 2)
        )

        try:
            tfidf_matrix = vectorizer.fit_transform(texts)
        except ValueError:
            return self._simple_clustering(requests)

        similarity_matrix = cosine_similarity(tfidf_matrix)

        clusters = []
        assigned = set()

        for i in range(len(requests)):
            if i in assigned:
                continue

            cluster_items = [requests[i]]
            assigned.add(i)

            for j in range(i + 1, len(requests)):
                if j in assigned:
                    continue

                if similarity_matrix[i][j] >= similarity_threshold:
                    cluster_items.append(requests[j])
                    assigned.add(j)

            cluster_label = self._generate_cluster_label(cluster_items)
            examples = [item['full_text'][:100] for item in cluster_items[:3]]

            clusters.append({
                'feature': cluster_label,
                'count': len(cluster_items),
                'examples': examples
            })

        clusters.sort(key=lambda x: x['count'], reverse=True)

        return clusters

    def _simple_clustering(self, requests: List[Dict]) -> List[Dict]:
        """Simple keyword-based clustering fallback."""
        # Group by common keywords
        keyword_groups = defaultdict(list)

        for request in requests:
            text_lower = request['text'].lower()
            key = 'Feature request'

            # Try to categorize
            if 'dark mode' in text_lower or 'night mode' in text_lower or 'theme' in text_lower:
                key = 'Dark mode'
            elif 'integrat' in text_lower or 'connect' in text_lower:
                key = 'Integration requests'
            elif 'export' in text_lower:
                key = 'Export functionality'
            elif 'search' in text_lower:
                key = 'Search features'
            elif 'notif' in text_lower:
                key = 'Notification features'
            elif 'offline' in text_lower:
                key = 'Offline functionality'

            keyword_groups[key].append(request)

        result = []
        for label, items in keyword_groups.items():
            examples = [item['text'][:100] for item in items[:3]]
            result.append({
                'feature': label,
                'count': len(items),
                'examples': examples
            })

        result.sort(key=lambda x: x['count'], reverse=True)
        return result

    def _generate_cluster_label(self, cluster_items: List[Dict]) -> str:
        """Generate descriptive label for feature request cluster."""
        all_text = ' '.join([item['text'].lower() for item in cluster_items])
        words = re.findall(r'\b\w+\b', all_text)
        word_counts = Counter(words)

        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'may', 'might', 'can', 'this', 'that', 'it', 'its', 'i', 'me', 'my', 'we', 'our', 'wish', 'want', 'need', 'please', 'add'}

        meaningful_words = [(word, count) for word, count in word_counts.most_common(10)
                           if word not in stop_words and len(word) > 3]

        if meaningful_words:
            top_words = [word for word, _ in meaningful_words[:3]]
            label = ' '.join(top_words).title()

            if len(label) > 10:
                return label
            else:
                first_text = cluster_items[0]['text']
                if len(first_text) < 60:
                    return first_text
                return first_text[:57] + '...'
        else:
            return cluster_items[0]['feature']
