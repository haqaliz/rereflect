"""Categorizers for pain points, feature requests, and urgent feedback."""
import re
from typing import Tuple, Optional
from dataclasses import dataclass


@dataclass
class CategorizationResult:
    """Result of categorizing feedback."""
    category: str
    level: str  # severity, priority, or response_time
    confidence: float
    text: Optional[str] = None


class PainPointCategorizer:
    """Categorize extracted pain points into 12 categories with severity levels."""

    CATEGORIES = {
        'security_breach': {
            'keywords': [
                'hacked', 'breach', 'exposed', 'unauthorized', 'compromised',
                'vulnerability', 'attack', 'stolen', 'leaked', 'security issue',
                'security problem', 'data exposed', 'unauthorized access'
            ],
            'severity': 'critical'
        },
        'data_loss': {
            'keywords': [
                'lost data', 'data gone', 'disappeared', 'deleted', 'missing files',
                'corrupted', 'wiped', 'erased', "can't recover", 'data lost',
                'lost everything', 'files gone', 'data disappeared'
            ],
            'severity': 'critical'
        },
        'payment_issue': {
            'keywords': [
                'payment failed', 'charged twice', 'billing error', 'refund',
                "can't pay", 'transaction failed', 'card declined', 'overcharged',
                'double charge', 'wrong charge', 'payment problem', 'billing issue'
            ],
            'severity': 'critical'
        },
        'system_crash': {
            'keywords': [
                'crash', 'freeze', 'hang', 'stuck', 'unresponsive', 'not responding',
                'force quit', 'keeps closing', 'shuts down', 'crashed again',
                'keeps crashing', 'freezing', 'frozen', 'app closed'
            ],
            'severity': 'major'
        },
        'authentication': {
            'keywords': [
                "can't login", 'password', 'locked out', 'authentication',
                'sign in', 'forgot password', 'reset password', 'session expired',
                "can't log in", 'login failed', 'wrong password', 'invalid credentials',
                "can't access account", 'login issue', 'login problem'
            ],
            'severity': 'major'
        },
        'functionality_broken': {
            'keywords': [
                'not working', 'broken', "doesn't work", 'stopped working',
                "can't use", 'fails', 'error', 'bug', 'glitch', 'malfunction',
                'feature broken', "won't work", 'stopped functioning'
            ],
            'severity': 'major'
        },
        'performance': {
            'keywords': [
                'slow', 'lag', 'loading', 'timeout', 'takes forever', 'sluggish',
                'buffering', 'waiting', 'unacceptably slow', 'too slow', 'very slow',
                'laggy', 'delays', 'performance issue', 'loading time'
            ],
            'severity': 'moderate'
        },
        'usability': {
            'keywords': [
                'confusing', 'hard to find', 'unintuitive', 'complicated',
                'difficult', 'unclear', "don't understand", 'where is',
                'hard to use', 'not intuitive', 'confusing interface', 'poor ux',
                'bad design', 'user unfriendly', 'hard to navigate'
            ],
            'severity': 'moderate'
        },
        'compatibility': {
            'keywords': [
                "doesn't work on", 'browser', 'safari', 'chrome', 'firefox',
                'mobile', 'ios', 'android', 'tablet', 'screen size',
                'not compatible', 'compatibility issue', 'not supported',
                'works on', 'browser issue'
            ],
            'severity': 'moderate'
        },
        'missing_feature': {
            'keywords': [
                'no way to', "can't do", 'missing', 'need option',
                'should have', 'expected', 'basic feature', 'no option',
                "doesn't have", 'lacking', 'not available', 'not possible'
            ],
            'severity': 'minor'
        },
        'documentation': {
            'keywords': [
                'documentation', 'help', 'how to', 'instructions', 'tutorial',
                'guide', 'manual', 'faq', 'support article', 'no docs',
                'outdated docs', 'unclear documentation', 'poor documentation'
            ],
            'severity': 'minor'
        },
        'cosmetic': {
            'keywords': [
                'typo', 'color', 'font', 'align', 'spacing', 'icon', 'layout',
                'ugly', 'design', 'visual', 'looks wrong', 'misaligned',
                'wrong color', 'display issue', 'styling'
            ],
            'severity': 'trivial'
        }
    }

    def categorize(self, text: str) -> CategorizationResult:
        """
        Categorize a pain point text.

        Args:
            text: The pain point text to categorize

        Returns:
            CategorizationResult with category, severity, and confidence
        """
        text_lower = text.lower()
        best_match = None
        best_score = 0

        for category, config in self.CATEGORIES.items():
            score = self._calculate_match_score(text_lower, config['keywords'])
            if score > best_score:
                best_score = score
                best_match = (category, config['severity'])

        if best_match and best_score > 0:
            confidence = min(best_score / 3.0, 1.0)  # Normalize to 0-1
            return CategorizationResult(
                category=best_match[0],
                level=best_match[1],
                confidence=confidence,
                text=self._extract_pain_point_text(text)
            )

        # Default to functionality_broken if no match
        return CategorizationResult(
            category='functionality_broken',
            level='major',
            confidence=0.3,
            text=self._extract_pain_point_text(text)
        )

    def _calculate_match_score(self, text: str, keywords: list) -> float:
        """Calculate match score based on keyword matches."""
        score = 0
        for keyword in keywords:
            if keyword in text:
                # Longer keywords get higher scores
                score += 1 + (len(keyword.split()) - 1) * 0.5
        return score

    def _extract_pain_point_text(self, text: str) -> str:
        """Extract a concise pain point description."""
        # Remove common filler words from the start
        cleaned = re.sub(r'^(i |the |my |our |we |it |this |that )', '', text.lower(), flags=re.IGNORECASE)
        cleaned = cleaned.strip().capitalize()

        if len(cleaned) > 150:
            # Try to find a natural break point
            break_points = ['. ', '! ', '? ', ', but ', ', and ']
            for bp in break_points:
                idx = cleaned[:150].rfind(bp)
                if idx > 50:
                    return cleaned[:idx + 1].strip()
            return cleaned[:147] + '...'

        return cleaned


class FeatureRequestCategorizer:
    """Categorize feature requests into 10 categories with priority levels."""

    CATEGORIES = {
        'core_functionality': {
            'keywords': [
                'need', 'must have', 'essential', 'basic', 'critical feature',
                'fundamental', 'core', 'necessary', 'required', 'important feature',
                'key feature', 'main feature', 'primary'
            ],
            'priority': 'high'
        },
        'automation': {
            'keywords': [
                'automate', 'automatic', 'scheduled', 'recurring', 'batch',
                'bulk', 'workflow', 'trigger', 'rule-based', 'auto-',
                'automatically', 'schedule', 'cron', 'timer'
            ],
            'priority': 'high'
        },
        'integration': {
            'keywords': [
                'integrate', 'connect', 'sync', 'api', 'zapier', 'slack',
                'webhook', 'third-party', 'plugin', 'extension', 'integration',
                'google', 'microsoft', 'salesforce', 'hubspot'
            ],
            'priority': 'high'
        },
        'reporting': {
            'keywords': [
                'report', 'analytics', 'dashboard', 'metrics', 'insights',
                'statistics', 'chart', 'graph', 'data visualization', 'kpi',
                'tracking', 'monitor', 'performance data'
            ],
            'priority': 'medium'
        },
        'customization': {
            'keywords': [
                'customize', 'personalize', 'configure', 'settings', 'options',
                'preferences', 'tailor', 'adjust', 'modify', 'custom',
                'flexible', 'configurable'
            ],
            'priority': 'medium'
        },
        'collaboration': {
            'keywords': [
                'share', 'team', 'collaborate', 'invite', 'permissions',
                'roles', 'workspace', 'multi-user', 'comment', 'co-',
                'together', 'teamwork', 'group'
            ],
            'priority': 'medium'
        },
        'export_import': {
            'keywords': [
                'export', 'import', 'download', 'csv', 'pdf', 'excel',
                'backup', 'migrate', 'transfer', 'upload', 'file',
                'data export', 'data import'
            ],
            'priority': 'medium'
        },
        'mobile': {
            'keywords': [
                'mobile', 'app', 'ios', 'android', 'phone', 'tablet',
                'responsive', 'touch', 'offline', 'native app', 'mobile app',
                'smartphone'
            ],
            'priority': 'medium'
        },
        'notifications': {
            'keywords': [
                'notify', 'alert', 'reminder', 'email', 'push', 'notification',
                'subscribe', 'digest', 'update', 'notify me', 'send alert',
                'email notification', 'push notification'
            ],
            'priority': 'low'
        },
        'ui_enhancement': {
            'keywords': [
                'look', 'design', 'theme', 'dark mode', 'layout', 'appearance',
                'style', 'beautiful', 'modern', 'ui', 'ux', 'interface',
                'visual', 'prettier', 'light mode'
            ],
            'priority': 'low'
        }
    }

    def categorize(self, text: str, occurrence_count: int = 1) -> CategorizationResult:
        """
        Categorize a feature request text.

        Args:
            text: The feature request text to categorize
            occurrence_count: How many times this request appears (affects priority)

        Returns:
            CategorizationResult with category, priority, and confidence
        """
        text_lower = text.lower()
        best_match = None
        best_score = 0

        for category, config in self.CATEGORIES.items():
            score = self._calculate_match_score(text_lower, config['keywords'])
            if score > best_score:
                best_score = score
                best_match = (category, config['priority'])

        if best_match and best_score > 0:
            # Adjust priority based on occurrence count
            priority = best_match[1]
            if occurrence_count >= 10:
                priority = 'high'
            elif occurrence_count >= 5 and priority == 'low':
                priority = 'medium'

            confidence = min(best_score / 3.0, 1.0)
            return CategorizationResult(
                category=best_match[0],
                level=priority,
                confidence=confidence,
                text=self._extract_feature_text(text)
            )

        # Default to core_functionality for unmatched requests
        return CategorizationResult(
            category='core_functionality',
            level='medium',
            confidence=0.3,
            text=self._extract_feature_text(text)
        )

    def _calculate_match_score(self, text: str, keywords: list) -> float:
        """Calculate match score based on keyword matches."""
        score = 0
        for keyword in keywords:
            if keyword in text:
                score += 1 + (len(keyword.split()) - 1) * 0.5
        return score

    def _extract_feature_text(self, text: str) -> str:
        """Extract a concise feature request description."""
        # Remove common request phrases
        patterns_to_remove = [
            r'^(please |could you |can you |i wish |i want |i would like |i need |we need )',
            r'^(it would be nice if |it would be great if |it would help if )',
            r'^(would love to |would like to )'
        ]

        cleaned = text.lower()
        for pattern in patterns_to_remove:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        cleaned = cleaned.strip().capitalize()

        if len(cleaned) > 150:
            break_points = ['. ', '! ', '? ', ', but ', ', and ']
            for bp in break_points:
                idx = cleaned[:150].rfind(bp)
                if idx > 50:
                    return cleaned[:idx + 1].strip()
            return cleaned[:147] + '...'

        return cleaned


class UrgentCategorizer:
    """Categorize urgent feedback into 10 categories with response time targets."""

    CATEGORIES = {
        'service_outage': {
            'keywords': [
                'down', 'not loading', '503', '502', 'unavailable', 'offline',
                'outage', "can't access", 'service error', 'site down',
                'server down', 'not accessible', 'website down'
            ],
            'response_time': 'immediate'
        },
        'data_breach': {
            'keywords': [
                'hacked', 'breach', 'exposed', 'leaked', 'stolen', 'compromised',
                'security incident', 'unauthorized access', 'data leak',
                'security breach', 'account compromised'
            ],
            'response_time': 'immediate'
        },
        'payment_failure': {
            'keywords': [
                "can't pay", 'payment failed', 'transaction failed', 'declined',
                'payment error', 'checkout broken', 'payment not working',
                "can't complete purchase", 'order failed'
            ],
            'response_time': 'immediate'
        },
        'data_corruption': {
            'keywords': [
                'lost everything', 'data gone', 'corrupted', 'wiped', 'erased',
                'all data lost', "can't recover", 'data destroyed',
                'files corrupted', 'database corrupted'
            ],
            'response_time': 'immediate'
        },
        'account_locked': {
            'keywords': [
                'locked out', "can't access account", 'suspended', 'blocked',
                'account disabled', 'banned', 'account locked',
                "can't get into account", 'access denied'
            ],
            'response_time': '1_hour'
        },
        'critical_bug': {
            'keywords': [
                'completely broken', 'nothing works', 'unusable', 'catastrophic',
                'critical error', 'major bug', 'totally broken',
                'everything broken', 'app unusable'
            ],
            'response_time': '1_hour'
        },
        'billing_dispute': {
            'keywords': [
                'charged twice', 'overcharged', 'unauthorized charge', 'fraud',
                'wrong amount', 'unexpected charge', 'double charged',
                'fraudulent charge', 'billing dispute'
            ],
            'response_time': '4_hours'
        },
        'churn_risk': {
            'keywords': [
                'cancel', 'leaving', 'switching to', 'competitor', 'fed up',
                'last straw', 'done with', 'going to leave', 'canceling',
                'unsubscribe', 'deleting account', 'closing account'
            ],
            'response_time': '4_hours'
        },
        'compliance': {
            'keywords': [
                'gdpr', 'privacy', 'legal', 'compliance', 'lawsuit', 'regulation',
                'data protection', 'terms violation', 'privacy violation',
                'regulatory', 'ccpa', 'legal action'
            ],
            'response_time': '4_hours'
        },
        'reputation_risk': {
            'keywords': [
                'twitter', 'review', 'public', 'social media', 'tell everyone',
                'warn others', 'bad review', 'post about', 'going viral',
                'negative review', 'complaint public'
            ],
            'response_time': '24_hours'
        }
    }

    def categorize(self, text: str, sentiment_score: float = 0.0) -> CategorizationResult:
        """
        Categorize urgent feedback text.

        Args:
            text: The urgent feedback text to categorize
            sentiment_score: Sentiment score (-1 to 1) to influence categorization

        Returns:
            CategorizationResult with category, response_time, and confidence
        """
        text_lower = text.lower()
        best_match = None
        best_score = 0

        for category, config in self.CATEGORIES.items():
            score = self._calculate_match_score(text_lower, config['keywords'])

            # Boost score for very negative sentiment
            if sentiment_score < -0.5:
                score *= 1.2

            if score > best_score:
                best_score = score
                best_match = (category, config['response_time'])

        if best_match and best_score > 0:
            confidence = min(best_score / 3.0, 1.0)
            return CategorizationResult(
                category=best_match[0],
                level=best_match[1],
                confidence=confidence
            )

        # Default to critical_bug for unmatched urgent feedback
        return CategorizationResult(
            category='critical_bug',
            level='1_hour',
            confidence=0.3
        )

    def _calculate_match_score(self, text: str, keywords: list) -> float:
        """Calculate match score based on keyword matches."""
        score = 0
        for keyword in keywords:
            if keyword in text:
                score += 1 + (len(keyword.split()) - 1) * 0.5
        return score
