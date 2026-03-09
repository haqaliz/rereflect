"""
Default system response templates for Rereflect.

These 8 templates are seeded at startup/migration and are read-only.
They cannot be edited or deleted by any organization.
"""

SYSTEM_TEMPLATES = [
    {
        "name": "Bug Report Acknowledgment",
        "category": "Bug Report",
        "body": (
            "Hi {{customer_name}},\n\n"
            "Thank you for reporting this issue. We've logged it and our team is looking into it.\n\n"
            "Here's what we know so far: your feedback about \"{{feedback_excerpt}}\" has been "
            "categorized and prioritized.\n\n"
            "We'll follow up with an update as soon as we have more information. If you have any "
            "additional details that might help us reproduce the issue, please don't hesitate to share.\n\n"
            "Best regards,\n"
            "{{agent_name}}\n"
            "{{product_name}} Team"
        ),
        "is_system": True,
    },
    {
        "name": "Feature Request Acknowledgment",
        "category": "Feature Request",
        "body": (
            "Hi {{customer_name}},\n\n"
            "Thank you for this feature suggestion! We really appreciate customers who take the time "
            "to share ideas for improving {{product_name}}.\n\n"
            "Your request has been added to our product backlog and will be reviewed during our next "
            "prioritization cycle. While we can't commit to a specific timeline, customer feedback "
            "like yours directly influences our roadmap.\n\n"
            "If you'd like to add more context or detail about your use case, we'd love to hear it.\n\n"
            "Thanks again,\n"
            "{{agent_name}}\n"
            "{{product_name}} Team"
        ),
        "is_system": True,
    },
    {
        "name": "Churn Risk Outreach",
        "category": "Churn Risk",
        "body": (
            "Hi {{customer_name}},\n\n"
            "I wanted to reach out personally because I noticed you've been experiencing some "
            "friction with {{product_name}} recently.\n\n"
            "Your satisfaction is really important to us, and I'd love to understand how we can "
            "improve your experience. Would you be open to a quick 15-minute call this week? "
            "I'm happy to work through any issues directly.\n\n"
            "If you'd prefer, you can also reply to this message with your concerns and I'll make "
            "sure they get addressed promptly.\n\n"
            "Looking forward to hearing from you,\n"
            "{{agent_name}}\n"
            "{{support_email}}"
        ),
        "is_system": True,
    },
    {
        "name": "Positive Feedback Thanks",
        "category": "Positive",
        "body": (
            "Hi {{customer_name}},\n\n"
            "Thank you so much for the kind words! It means a lot to our team to hear that "
            "{{product_name}} is making a difference for you.\n\n"
            "We're always working to make things even better, so if you ever have suggestions or "
            "run into anything, don't hesitate to reach out.\n\n"
            "Thanks for being a valued customer!\n\n"
            "Best,\n"
            "{{agent_name}}\n"
            "{{product_name}} Team"
        ),
        "is_system": True,
    },
    {
        "name": "General Complaint Response",
        "category": "Complaint",
        "body": (
            "Hi {{customer_name}},\n\n"
            "Thank you for sharing your feedback with us. I'm sorry to hear about your experience, "
            "and I want you to know we take this seriously.\n\n"
            "I've flagged your concern internally and our team will review it. We want to make sure "
            "this gets resolved properly.\n\n"
            "Could you share any additional details that would help us understand the issue better? "
            "We'd like to get this right.\n\n"
            "Best regards,\n"
            "{{agent_name}}\n"
            "{{support_email}}"
        ),
        "is_system": True,
    },
    {
        "name": "Urgent Issue Escalation",
        "category": "Urgent",
        "body": (
            "Hi {{customer_name}},\n\n"
            "I see this is a critical issue and I want to assure you it has our immediate attention. "
            "Your report has been escalated to our engineering team.\n\n"
            "We understand the impact this is having and we're treating it as a top priority. "
            "You can expect an update from us within the next few hours.\n\n"
            "In the meantime, if there's anything else you need, please reach out directly to "
            "{{support_email}} and reference this conversation.\n\n"
            "Thank you for your patience,\n"
            "{{agent_name}}\n"
            "{{product_name}} Team"
        ),
        "is_system": True,
    },
    {
        "name": "Follow-up Check-in",
        "category": "Follow-up",
        "body": (
            "Hi {{customer_name}},\n\n"
            "I wanted to follow up on the issue you reported earlier. Has everything been resolved "
            "on your end?\n\n"
            "We made some changes based on your feedback and I want to make sure things are working "
            "smoothly for you now.\n\n"
            "If you're still experiencing any issues, or if there's anything else we can help with, "
            "please don't hesitate to let us know.\n\n"
            "Best,\n"
            "{{agent_name}}\n"
            "{{product_name}} Team"
        ),
        "is_system": True,
    },
    {
        "name": "Onboarding Help",
        "category": "Onboarding",
        "body": (
            "Hi {{customer_name}},\n\n"
            "Welcome to {{product_name}}! I noticed you might be getting started and I wanted to "
            "reach out to make sure your onboarding goes smoothly.\n\n"
            "Here are a few resources that might help:\n"
            "- Our getting started guide covers the basics\n"
            "- You can reach us anytime at {{support_email}}\n\n"
            "If you'd like a personalized walkthrough, I'm happy to set up a quick call.\n\n"
            "Looking forward to helping you get the most out of {{product_name}}!\n\n"
            "Best,\n"
            "{{agent_name}}\n"
            "{{product_name}} Team"
        ),
        "is_system": True,
    },
]
