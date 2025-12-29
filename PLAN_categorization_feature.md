# Action Plan: Categorization Feature for Pain Points, Feature Requests, and Urgent Feedback

## Overview

Currently, the system extracts pain points, feature requests, and urgent feedback from customer feedback text. However, these extracted items are **not categorized** - they're just raw extractions. This feature will add **intelligent categorization** using our analysis models to classify each extracted item into meaningful categories.

---

## Current State

### What exists today:
1. **Pain Points**: Extracted as raw text with count/examples (no categorization)
2. **Feature Requests**: Extracted as raw text with count/examples (no categorization)
3. **Urgent Feedback**: Flagged with `is_urgent=true` (no urgency category)
4. **Tags**: 15 pre-defined tags applied to individual feedback items

### Database Schema (current):
```python
FeedbackItem(
    # ... existing fields ...
    extracted_issue: Text          # Pain point description (if any)
    tags: JSON                     # Category tags array
    is_urgent: Boolean             # Simple boolean flag
)
```

---

## Proposed Feature

### Categorization Taxonomy

#### 1. Pain Point Categories (12 categories)

| Category | Description | Detection Signals | Severity |
|----------|-------------|-------------------|----------|
| `security_breach` | Security vulnerabilities, data exposure | "hacked", "breach", "exposed", "unauthorized", "compromised" | Critical |
| `data_loss` | Data corruption, deletion, or loss | "lost data", "data gone", "disappeared", "deleted", "missing files" | Critical |
| `payment_issue` | Payment failures, billing problems | "payment failed", "charged twice", "billing error", "refund" | Critical |
| `system_crash` | Application crashes, freezes | "crash", "freeze", "hang", "stuck", "unresponsive" | Major |
| `authentication` | Login, signup, password issues | "can't login", "password", "locked out", "authentication" | Major |
| `functionality_broken` | Core features not working | "not working", "broken", "doesn't work", "stopped working" | Major |
| `performance` | Slow loading, lag, timeouts | "slow", "lag", "loading", "timeout", "takes forever" | Moderate |
| `usability` | Confusing UI, poor UX | "confusing", "hard to find", "unintuitive", "complicated" | Moderate |
| `compatibility` | Browser, device, OS issues | "doesn't work on", "browser", "mobile", "safari", "chrome" | Moderate |
| `missing_feature` | Expected feature not present | "no way to", "can't do", "missing", "where is" | Minor |
| `documentation` | Help docs unclear or missing | "documentation", "help", "how to", "instructions" | Minor |
| `cosmetic` | Visual issues, typos, styling | "typo", "color", "font", "align", "spacing", "icon" | Trivial |

#### 2. Feature Request Categories (10 categories)

| Category | Description | Detection Signals | Priority |
|----------|-------------|-------------------|----------|
| `core_functionality` | Essential new features | "need", "must have", "essential", "basic" | High |
| `automation` | Workflow automation requests | "automate", "automatic", "scheduled", "recurring" | High |
| `integration` | Third-party integrations | "integrate", "connect", "sync", "api", "zapier", "slack" | High |
| `reporting` | Analytics, reports, dashboards | "report", "analytics", "dashboard", "metrics", "insights" | Medium |
| `customization` | Personalization, settings | "customize", "personalize", "configure", "settings", "options" | Medium |
| `collaboration` | Team features, sharing | "share", "team", "collaborate", "invite", "permissions" | Medium |
| `export_import` | Data export/import capabilities | "export", "import", "download", "csv", "pdf" | Medium |
| `mobile` | Mobile app features | "mobile", "app", "ios", "android", "phone" | Medium |
| `notifications` | Alerts, reminders, emails | "notify", "alert", "reminder", "email", "push" | Low |
| `ui_enhancement` | Visual improvements | "look", "design", "theme", "dark mode", "layout" | Low |

#### 3. Urgent Feedback Categories (10 categories)

| Category | Description | Detection Signals | Response Time |
|----------|-------------|-------------------|---------------|
| `service_outage` | Complete service unavailability | "down", "not loading", "503", "502", "unavailable", "offline" | Immediate |
| `data_breach` | Security incident, data exposed | "hacked", "breach", "exposed", "leaked", "stolen" | Immediate |
| `payment_failure` | Unable to process payments | "can't pay", "payment failed", "transaction failed", "declined" | Immediate |
| `data_corruption` | Data lost or corrupted | "lost everything", "data gone", "corrupted", "wiped" | Immediate |
| `account_locked` | Users locked out of accounts | "locked out", "can't access account", "suspended", "blocked" | 1 hour |
| `critical_bug` | Bug preventing core functionality | "completely broken", "nothing works", "unusable" | 1 hour |
| `billing_dispute` | Overcharges, unauthorized charges | "charged twice", "overcharged", "unauthorized charge", "fraud" | 4 hours |
| `churn_risk` | Customer threatening to leave | "cancel", "leaving", "switching to", "competitor", "fed up" | 4 hours |
| `compliance` | Legal, regulatory concerns | "gdpr", "privacy", "legal", "compliance", "lawsuit" | 4 hours |
| `reputation_risk` | Public complaints, review threats | "twitter", "review", "public", "social media", "tell everyone" | 24 hours |

---

## Implementation Plan

### Phase 1: Database Schema Updates

**File**: `/services/backend-api/src/models/feedback.py`

Add new columns:
```python
# Pain point categorization (12 categories)
pain_point_category = Column(String, nullable=True)
# Values: security_breach, data_loss, payment_issue, system_crash, authentication,
#         functionality_broken, performance, usability, compatibility, missing_feature,
#         documentation, cosmetic
pain_point_severity = Column(String, nullable=True)  # critical, major, moderate, minor, trivial
pain_point_text = Column(Text, nullable=True)        # Extracted pain point text

# Feature request categorization (10 categories)
feature_request_category = Column(String, nullable=True)
# Values: core_functionality, automation, integration, reporting, customization,
#         collaboration, export_import, mobile, notifications, ui_enhancement
feature_request_priority = Column(String, nullable=True)  # high, medium, low
feature_request_text = Column(Text, nullable=True)        # Extracted feature request text

# Urgent categorization (10 categories - extends existing is_urgent)
urgent_category = Column(String, nullable=True)
# Values: service_outage, data_breach, payment_failure, data_corruption, account_locked,
#         critical_bug, billing_dispute, churn_risk, compliance, reputation_risk
urgent_response_time = Column(String, nullable=True)  # immediate, 1_hour, 4_hours, 24_hours

# Confidence scores
categorization_confidence = Column(Float, nullable=True)  # 0.0-1.0
```

**Migration**: Create Alembic migration for new columns

---

### Phase 2: Analysis Engine - Categorizer Module

**New File**: `/services/analysis-engine/src/analyzer/categorizer.py`

```python
class PainPointCategorizer:
    """Categorize extracted pain points into 12 categories with severity levels"""

    # Category -> (keywords, severity)
    CATEGORIES = {
        'security_breach': {
            'keywords': ['hacked', 'breach', 'exposed', 'unauthorized', 'compromised',
                        'vulnerability', 'attack', 'stolen', 'leaked'],
            'severity': 'critical'
        },
        'data_loss': {
            'keywords': ['lost data', 'data gone', 'disappeared', 'deleted', 'missing files',
                        'corrupted', 'wiped', 'erased', 'can\'t recover'],
            'severity': 'critical'
        },
        'payment_issue': {
            'keywords': ['payment failed', 'charged twice', 'billing error', 'refund',
                        'can\'t pay', 'transaction failed', 'card declined', 'overcharged'],
            'severity': 'critical'
        },
        'system_crash': {
            'keywords': ['crash', 'freeze', 'hang', 'stuck', 'unresponsive', 'not responding',
                        'force quit', 'keeps closing', 'shuts down'],
            'severity': 'major'
        },
        'authentication': {
            'keywords': ['can\'t login', 'password', 'locked out', 'authentication',
                        'sign in', 'forgot password', 'reset password', 'session expired'],
            'severity': 'major'
        },
        'functionality_broken': {
            'keywords': ['not working', 'broken', 'doesn\'t work', 'stopped working',
                        'can\'t use', 'fails', 'error', 'bug'],
            'severity': 'major'
        },
        'performance': {
            'keywords': ['slow', 'lag', 'loading', 'timeout', 'takes forever', 'sluggish',
                        'buffering', 'waiting', 'unacceptably slow'],
            'severity': 'moderate'
        },
        'usability': {
            'keywords': ['confusing', 'hard to find', 'unintuitive', 'complicated',
                        'difficult', 'unclear', 'don\'t understand', 'where is'],
            'severity': 'moderate'
        },
        'compatibility': {
            'keywords': ['doesn\'t work on', 'browser', 'safari', 'chrome', 'firefox',
                        'mobile', 'ios', 'android', 'tablet', 'screen size'],
            'severity': 'moderate'
        },
        'missing_feature': {
            'keywords': ['no way to', 'can\'t do', 'missing', 'where is', 'need option',
                        'should have', 'expected', 'basic feature'],
            'severity': 'minor'
        },
        'documentation': {
            'keywords': ['documentation', 'help', 'how to', 'instructions', 'tutorial',
                        'guide', 'manual', 'faq', 'support article'],
            'severity': 'minor'
        },
        'cosmetic': {
            'keywords': ['typo', 'color', 'font', 'align', 'spacing', 'icon', 'layout',
                        'ugly', 'design', 'visual'],
            'severity': 'trivial'
        }
    }

    def categorize(self, text: str) -> tuple[str, str, float]:
        """Returns (category, severity, confidence)"""
        pass


class FeatureRequestCategorizer:
    """Categorize feature requests into 10 categories with priority levels"""

    # Category -> (keywords, priority)
    CATEGORIES = {
        'core_functionality': {
            'keywords': ['need', 'must have', 'essential', 'basic', 'critical feature',
                        'fundamental', 'core', 'necessary'],
            'priority': 'high'
        },
        'automation': {
            'keywords': ['automate', 'automatic', 'scheduled', 'recurring', 'batch',
                        'bulk', 'workflow', 'trigger', 'rule-based'],
            'priority': 'high'
        },
        'integration': {
            'keywords': ['integrate', 'connect', 'sync', 'api', 'zapier', 'slack',
                        'webhook', 'third-party', 'plugin', 'extension'],
            'priority': 'high'
        },
        'reporting': {
            'keywords': ['report', 'analytics', 'dashboard', 'metrics', 'insights',
                        'statistics', 'chart', 'graph', 'data visualization'],
            'priority': 'medium'
        },
        'customization': {
            'keywords': ['customize', 'personalize', 'configure', 'settings', 'options',
                        'preferences', 'tailor', 'adjust', 'modify'],
            'priority': 'medium'
        },
        'collaboration': {
            'keywords': ['share', 'team', 'collaborate', 'invite', 'permissions',
                        'roles', 'workspace', 'multi-user', 'comment'],
            'priority': 'medium'
        },
        'export_import': {
            'keywords': ['export', 'import', 'download', 'csv', 'pdf', 'excel',
                        'backup', 'migrate', 'transfer'],
            'priority': 'medium'
        },
        'mobile': {
            'keywords': ['mobile', 'app', 'ios', 'android', 'phone', 'tablet',
                        'responsive', 'touch', 'offline'],
            'priority': 'medium'
        },
        'notifications': {
            'keywords': ['notify', 'alert', 'reminder', 'email', 'push', 'notification',
                        'subscribe', 'digest', 'update'],
            'priority': 'low'
        },
        'ui_enhancement': {
            'keywords': ['look', 'design', 'theme', 'dark mode', 'layout', 'appearance',
                        'style', 'beautiful', 'modern'],
            'priority': 'low'
        }
    }

    def categorize(self, text: str, occurrence_count: int = 1) -> tuple[str, str, float]:
        """Returns (category, priority, confidence)"""
        pass


class UrgentCategorizer:
    """Categorize urgent feedback into 10 categories with response time targets"""

    # Category -> (keywords, response_time)
    CATEGORIES = {
        'service_outage': {
            'keywords': ['down', 'not loading', '503', '502', 'unavailable', 'offline',
                        'outage', 'can\'t access', 'service error'],
            'response_time': 'immediate'
        },
        'data_breach': {
            'keywords': ['hacked', 'breach', 'exposed', 'leaked', 'stolen', 'compromised',
                        'security incident', 'unauthorized access'],
            'response_time': 'immediate'
        },
        'payment_failure': {
            'keywords': ['can\'t pay', 'payment failed', 'transaction failed', 'declined',
                        'payment error', 'checkout broken'],
            'response_time': 'immediate'
        },
        'data_corruption': {
            'keywords': ['lost everything', 'data gone', 'corrupted', 'wiped', 'erased',
                        'all data lost', 'can\'t recover'],
            'response_time': 'immediate'
        },
        'account_locked': {
            'keywords': ['locked out', 'can\'t access account', 'suspended', 'blocked',
                        'account disabled', 'banned'],
            'response_time': '1_hour'
        },
        'critical_bug': {
            'keywords': ['completely broken', 'nothing works', 'unusable', 'catastrophic',
                        'critical error', 'major bug'],
            'response_time': '1_hour'
        },
        'billing_dispute': {
            'keywords': ['charged twice', 'overcharged', 'unauthorized charge', 'fraud',
                        'wrong amount', 'unexpected charge'],
            'response_time': '4_hours'
        },
        'churn_risk': {
            'keywords': ['cancel', 'leaving', 'switching to', 'competitor', 'fed up',
                        'last straw', 'done with', 'going to leave'],
            'response_time': '4_hours'
        },
        'compliance': {
            'keywords': ['gdpr', 'privacy', 'legal', 'compliance', 'lawsuit', 'regulation',
                        'data protection', 'terms violation'],
            'response_time': '4_hours'
        },
        'reputation_risk': {
            'keywords': ['twitter', 'review', 'public', 'social media', 'tell everyone',
                        'warn others', 'bad review', 'post about'],
            'response_time': '24_hours'
        }
    }

    def categorize(self, text: str, sentiment_score: float) -> tuple[str, str, float]:
        """Returns (category, response_time, confidence)"""
        pass
```

---

### Phase 3: Update Core Analyzer

**File**: `/services/analysis-engine/src/analyzer/core.py`

Modify `FeedbackAnalyzer` class to:
1. Import new categorizers
2. After extracting pain points → categorize each one
3. After extracting feature requests → categorize each one
4. After flagging urgent → categorize the urgency type

Update return models to include categories.

---

### Phase 4: Update Background Scheduler

**File**: `/services/backend-api/src/background/scheduler.py`

Modify `process_unanalyzed_feedback()` to:
1. Detect if feedback contains pain point → extract text + categorize
2. Detect if feedback contains feature request → extract text + categorize
3. If urgent → categorize urgency type
4. Save all new fields to database

---

### Phase 5: Update API Endpoints

**File**: `/services/backend-api/src/api/routes/feedback.py`

- Update response schemas to include new category fields
- Add filter parameters: `pain_point_category`, `feature_request_category`, `urgent_category`

**File**: `/services/backend-api/src/api/routes/dashboard.py`

- Group pain points by category
- Group feature requests by category
- Group urgent feedback by category
- Add category breakdown to response

---

### Phase 6: Update Frontend

**Files**:
- `/services/frontend-web/app/pain-points/page.tsx`
- `/services/frontend-web/app/feature-requests/page.tsx`
- `/services/frontend-web/app/urgent-feedback/page.tsx`
- `/services/frontend-web/app/dashboard/page.tsx`

Changes:
1. Display category badges on list items
2. Add category filter dropdowns
3. Show category distribution charts on dashboard
4. Color-code by category severity

---

## Detailed Task Breakdown

### Backend Tasks

| # | Task | File(s) | Estimated Lines |
|---|------|---------|-----------------|
| 1 | Add new columns to FeedbackItem model | `models/feedback.py` | 10 |
| 2 | Create Alembic migration | `alembic/versions/` | 30 |
| 3 | Create PainPointCategorizer class | `analyzer/categorizer.py` | 60 |
| 4 | Create FeatureRequestCategorizer class | `analyzer/categorizer.py` | 60 |
| 5 | Create UrgentCategorizer class | `analyzer/categorizer.py` | 60 |
| 6 | Update FeedbackAnalyzer to use categorizers | `analyzer/core.py` | 40 |
| 7 | Update data models for categories | `analyzer/models.py` | 20 |
| 8 | Update background scheduler | `background/scheduler.py` | 50 |
| 9 | Update feedback API schemas | `schemas/feedback.py` | 15 |
| 10 | Add category filters to feedback routes | `routes/feedback.py` | 30 |
| 11 | Update dashboard route for category grouping | `routes/dashboard.py` | 50 |

### Frontend Tasks

| # | Task | File(s) | Estimated Lines |
|---|------|---------|-----------------|
| 12 | Update TypeScript types for categories | `lib/api/feedback.ts` | 15 |
| 13 | Update dashboard API types | `lib/api/dashboard.ts` | 20 |
| 14 | Add category badges to pain-points page | `app/pain-points/page.tsx` | 40 |
| 15 | Add category filter to pain-points page | `app/pain-points/page.tsx` | 30 |
| 16 | Add category badges to feature-requests page | `app/feature-requests/page.tsx` | 40 |
| 17 | Add category filter to feature-requests page | `app/feature-requests/page.tsx` | 30 |
| 18 | Add category badges to urgent-feedback page | `app/urgent-feedback/page.tsx` | 40 |
| 19 | Add category filter to urgent-feedback page | `app/urgent-feedback/page.tsx` | 30 |
| 20 | Add category breakdown to dashboard | `app/dashboard/page.tsx` | 60 |

---

## Category Color Scheme

### Pain Point Categories (by severity)

| Severity | Categories | Text Color | Badge Background |
|----------|------------|------------|------------------|
| Critical | `security_breach`, `data_loss`, `payment_issue` | `text-red-700 dark:text-red-400` | `bg-red-100 dark:bg-red-900/40` |
| Major | `system_crash`, `authentication`, `functionality_broken` | `text-orange-700 dark:text-orange-400` | `bg-orange-100 dark:bg-orange-900/40` |
| Moderate | `performance`, `usability`, `compatibility` | `text-amber-700 dark:text-amber-400` | `bg-amber-100 dark:bg-amber-900/40` |
| Minor | `missing_feature`, `documentation` | `text-yellow-700 dark:text-yellow-400` | `bg-yellow-100 dark:bg-yellow-900/40` |
| Trivial | `cosmetic` | `text-slate-600 dark:text-slate-400` | `bg-slate-100 dark:bg-slate-900/40` |

### Feature Request Categories (by priority)

| Priority | Categories | Text Color | Badge Background |
|----------|------------|------------|------------------|
| High | `core_functionality`, `automation`, `integration` | `text-emerald-700 dark:text-emerald-400` | `bg-emerald-100 dark:bg-emerald-900/40` |
| Medium | `reporting`, `customization`, `collaboration`, `export_import`, `mobile` | `text-blue-700 dark:text-blue-400` | `bg-blue-100 dark:bg-blue-900/40` |
| Low | `notifications`, `ui_enhancement` | `text-purple-700 dark:text-purple-400` | `bg-purple-100 dark:bg-purple-900/40` |

### Urgent Categories (by response time)

| Response Time | Categories | Text Color | Badge Background |
|---------------|------------|------------|------------------|
| Immediate | `service_outage`, `data_breach`, `payment_failure`, `data_corruption` | `text-red-700 dark:text-red-400` | `bg-red-200 dark:bg-red-800/50` |
| 1 Hour | `account_locked`, `critical_bug` | `text-orange-700 dark:text-orange-400` | `bg-orange-100 dark:bg-orange-900/40` |
| 4 Hours | `billing_dispute`, `churn_risk`, `compliance` | `text-amber-700 dark:text-amber-400` | `bg-amber-100 dark:bg-amber-900/40` |
| 24 Hours | `reputation_risk` | `text-yellow-700 dark:text-yellow-400` | `bg-yellow-100 dark:bg-yellow-900/40` |

### Individual Category Icons

**Pain Points:**
| Category | Icon |
|----------|------|
| `security_breach` | `ShieldAlert` |
| `data_loss` | `DatabaseZap` |
| `payment_issue` | `CreditCard` |
| `system_crash` | `ServerCrash` |
| `authentication` | `KeyRound` |
| `functionality_broken` | `CircleX` |
| `performance` | `Gauge` |
| `usability` | `MousePointerClick` |
| `compatibility` | `Laptop` |
| `missing_feature` | `PackageX` |
| `documentation` | `FileQuestion` |
| `cosmetic` | `Paintbrush` |

**Feature Requests:**
| Category | Icon |
|----------|------|
| `core_functionality` | `Boxes` |
| `automation` | `Workflow` |
| `integration` | `Plug` |
| `reporting` | `BarChart3` |
| `customization` | `Settings2` |
| `collaboration` | `Users` |
| `export_import` | `ArrowUpDown` |
| `mobile` | `Smartphone` |
| `notifications` | `Bell` |
| `ui_enhancement` | `Palette` |

**Urgent:**
| Category | Icon |
|----------|------|
| `service_outage` | `ServerOff` |
| `data_breach` | `ShieldOff` |
| `payment_failure` | `BanknoteX` |
| `data_corruption` | `HardDriveOff` |
| `account_locked` | `Lock` |
| `critical_bug` | `Bug` |
| `billing_dispute` | `Receipt` |
| `churn_risk` | `UserMinus` |
| `compliance` | `Scale` |
| `reputation_risk` | `Megaphone` |

---

## API Response Changes

### Dashboard Response (Updated)
```json
{
  "pain_points": [
    {
      "issue": "Login not working",
      "count": 5,
      "category": "authentication",
      "severity": "major",
      "examples": ["..."]
    }
  ],
  "pain_points_by_severity": {
    "critical": 2,
    "major": 8,
    "moderate": 5,
    "minor": 10,
    "trivial": 3
  },
  "pain_points_by_category": {
    "security_breach": 1,
    "data_loss": 1,
    "payment_issue": 0,
    "system_crash": 3,
    "authentication": 2,
    "functionality_broken": 3,
    "performance": 2,
    "usability": 2,
    "compatibility": 1,
    "missing_feature": 5,
    "documentation": 5,
    "cosmetic": 3
  },
  "feature_requests": [
    {
      "feature": "Dark mode",
      "count": 12,
      "category": "ui_enhancement",
      "priority": "low",
      "examples": ["..."]
    }
  ],
  "feature_requests_by_priority": {
    "high": 8,
    "medium": 15,
    "low": 6
  },
  "feature_requests_by_category": {
    "core_functionality": 3,
    "automation": 2,
    "integration": 3,
    "reporting": 4,
    "customization": 3,
    "collaboration": 2,
    "export_import": 3,
    "mobile": 3,
    "notifications": 2,
    "ui_enhancement": 4
  },
  "urgent_items": [
    {
      "id": 86,
      "text": "System is completely down!",
      "category": "service_outage",
      "response_time": "immediate"
    }
  ],
  "urgent_by_response_time": {
    "immediate": 4,
    "1_hour": 2,
    "4_hours": 3,
    "24_hours": 1
  },
  "urgent_by_category": {
    "service_outage": 1,
    "data_breach": 0,
    "payment_failure": 2,
    "data_corruption": 1,
    "account_locked": 1,
    "critical_bug": 1,
    "billing_dispute": 2,
    "churn_risk": 1,
    "compliance": 0,
    "reputation_risk": 1
  }
}
```

### Feedback Item Response (Updated)
```json
{
  "id": 86,
  "text": "The login system is broken...",
  "sentiment_label": "negative",
  "sentiment_score": -0.65,
  "is_urgent": true,
  "urgent_category": "critical_bug",
  "urgent_response_time": "1_hour",
  "pain_point_category": "authentication",
  "pain_point_severity": "major",
  "pain_point_text": "Login system broken",
  "feature_request_category": null,
  "feature_request_priority": null,
  "feature_request_text": null,
  "tags": ["bug", "security"],
  "categorization_confidence": 0.85
}
```

---

## Implementation Order

1. **Phase 1**: Database schema (migration)
2. **Phase 2**: Analysis engine categorizers
3. **Phase 3**: Update core analyzer
4. **Phase 4**: Update background scheduler
5. **Phase 5**: Update API endpoints
6. **Phase 6**: Update frontend pages

---

## Testing Checklist

- [ ] Unit tests for each categorizer class
- [ ] Integration test for full analysis pipeline
- [ ] API tests for new filter parameters
- [ ] Frontend displays categories correctly
- [ ] Category filters work as expected
- [ ] Dashboard shows correct category breakdowns
- [ ] Existing feedback re-analyzed with new categories
- [ ] Performance acceptable with new categorization step

---

## Questions to Clarify

1. Should we re-analyze all existing feedback to apply categories? (Recommended: Yes)
2. Should category be editable by users? (Recommended: No, auto-only for now)
3. Do we want confidence thresholds to skip uncertain categorizations? (Recommended: Yes, >0.5)
4. Should we add category to the feedback table view? (Recommended: Yes, as badge)
