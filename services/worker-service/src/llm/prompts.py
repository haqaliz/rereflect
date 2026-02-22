"""
All LLM prompts used by the worker service.
Moved from openai_client.py — kept identical to preserve existing behavior.
"""

# Built-in pain point categories (12)
PAIN_POINT_CATEGORIES = [
    "security_breach", "data_loss", "payment_issue", "system_crash",
    "authentication", "functionality_broken", "performance", "usability",
    "compatibility", "missing_feature", "documentation", "cosmetic",
]

# Built-in feature request categories (10)
FEATURE_REQUEST_CATEGORIES = [
    "core_functionality", "automation", "integration", "reporting",
    "customization", "collaboration", "export_import", "mobile",
    "notifications", "ui_enhancement",
]

# Built-in urgent categories (10)
URGENT_CATEGORIES = [
    "service_outage", "data_breach", "payment_failure", "data_corruption",
    "account_locked", "critical_bug", "billing_dispute", "churn_risk",
    "compliance", "reputation_risk",
]

CATEGORIZATION_PROMPT = """You are a customer feedback analyst. Analyze the following feedback and return a JSON object.

Available pain point categories: {pain_point_categories}
Available feature request categories: {feature_request_categories}
Available urgent categories: {urgent_categories}
{custom_categories_section}

Return ONLY valid JSON with these fields:
{{
  "sentiment_label": "positive" | "neutral" | "negative",
  "sentiment_score": float (-1.0 to 1.0),
  "is_urgent": boolean,
  "pain_point_category": string | null (from available list),
  "pain_point_severity": "critical" | "major" | "moderate" | "minor" | "trivial" | null,
  "feature_request_category": string | null (from available list),
  "feature_request_priority": "high" | "medium" | "low" | null,
  "urgent_category": string | null (from available list, only if is_urgent),
  "urgent_response_time": "immediate" | "1_hour" | "4_hours" | "24_hours" | null,
  "churn_risk_score": integer (0-100, likelihood customer will churn),
  "suggested_action": string (1-2 sentence recommendation),
  "tags": array of strings (max 5 relevant tags),
  "confidence": float (0.0-1.0)
}}

Feedback text:
\"\"\"{feedback_text}\"\"\""""


CHURN_ANALYSIS_PROMPT = """You are a customer success analyst. Analyze the following feedback data for a single customer and provide a concise churn risk analysis.

Customer email: {customer_email}
Health score: {health_score}/100 (lower = higher risk)
Risk level: {risk_level}
Component scores:
- Churn risk: {churn_risk_component}/100
- Sentiment: {sentiment_component}/100
- Resolution time: {resolution_component}/100
- Feedback frequency: {frequency_component}/100

Recent feedback items (most recent first):
{feedback_items}

Return ONLY valid JSON with this structure:
{{
  "analysis": "2-3 sentence summary of why this customer is at risk and what the key drivers are",
  "recommended_actions": ["action 1", "action 2", "action 3"],
  "risk_drivers": ["driver 1", "driver 2"],
  "estimated_urgency": "immediate" | "this_week" | "this_month"
}}"""


RETENTION_ANALYSIS_PROMPT = """You are a customer success analyst. Analyze the following feedback data for a customer with moderate health and provide a retention analysis.

Customer email: {customer_email}
Health score: {health_score}/100 (40-69 = moderate zone)
Risk level: {risk_level}
Component scores:
- Churn risk: {churn_risk_component}/100
- Sentiment: {sentiment_component}/100
- Resolution time: {resolution_component}/100
- Feedback frequency: {frequency_component}/100

Recent feedback items (most recent first):
{feedback_items}

Focus on:
- Trajectory analysis: is this customer trending toward at-risk or healthy?
- Early warning signs that could push them toward at-risk
- What actions would solidify them as a healthy customer
- Any patterns in their feedback that reveal unmet needs

Return ONLY valid JSON with this structure:
{{
  "analysis": "2-3 sentence summary of the customer's trajectory and key retention factors",
  "recommended_actions": ["action 1", "action 2", "action 3"],
  "risk_drivers": ["early warning sign 1", "early warning sign 2"],
  "estimated_urgency": "this_week" | "this_month"
}}"""


GROWTH_ANALYSIS_PROMPT = """You are a customer success analyst. Analyze the following feedback data for a healthy customer and identify growth and advocacy opportunities.

Customer email: {customer_email}
Health score: {health_score}/100 (70+ = healthy zone)
Risk level: {risk_level}
Component scores:
- Churn risk: {churn_risk_component}/100
- Sentiment: {sentiment_component}/100
- Resolution time: {resolution_component}/100
- Feedback frequency: {frequency_component}/100

Recent feedback items (most recent first):
{feedback_items}

Focus on:
- What strengths and positive signals does this customer exhibit?
- Expansion opportunities (upsell, feature adoption, increased usage)
- Advocacy potential (testimonials, referrals, case studies)
- Minor risks to watch that could erode satisfaction

Return ONLY valid JSON with this structure:
{{
  "analysis": "2-3 sentence summary of customer strengths and growth opportunities",
  "recommended_actions": ["action 1", "action 2", "action 3"],
  "risk_drivers": ["minor risk to watch 1", "minor risk to watch 2"],
  "estimated_urgency": "this_month"
}}"""


INSIGHTS_PROMPT = """You are a customer feedback analyst. Analyze the following batch of customer feedback items and generate 3-5 actionable insights for the product team.

Each insight should identify a pattern, trend, or actionable recommendation based on the feedback.

Feedback items:
{feedback_items}

Return ONLY valid JSON with this structure:
{{
  "insights": [
    {{
      "title": "Short insight title (max 10 words)",
      "description": "Detailed explanation with specific evidence from feedback (2-3 sentences)",
      "category": "pain_point" | "feature_request" | "positive_trend" | "churn_risk" | "opportunity",
      "priority": "high" | "medium" | "low"
    }}
  ]
}}"""
