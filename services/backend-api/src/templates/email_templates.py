"""
Rereflect Email Templates - Sunset Horizon Design System

These templates use email-safe CSS with the Rereflect color palette:
- Primary gradient: #f97316 → #ea580c (coral/orange)
- Background: #faf8f5 (warm cream)
- Text: #3d2f2b (warm dark brown)
- Muted: #78716c (warm gray)
- Accent: #e5a366 (golden amber)
"""

# Common color palette (email-safe hex values)
COLORS = {
    "primary": "#f97316",
    "primary_dark": "#ea580c",
    "background": "#faf8f5",
    "card": "#ffffff",
    "text": "#3d2f2b",
    "muted": "#78716c",
    "accent": "#e5a366",
    "border": "#ede8e3",
    "success": "#22c55e",
    "success_bg": "#f0fdf4",
}

# Shared email components
EMAIL_HEADER = """
<!-- Header with Logo -->
<tr>
    <td style="padding: 0;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background: linear-gradient(135deg, #f97316 0%, #ea580c 50%, #dc5407 100%); border-radius: 16px 16px 0 0;">
            <tr>
                <td style="padding: 40px 40px 32px 40px;">
                    <!-- Logo -->
                    <table cellpadding="0" cellspacing="0">
                        <tr>
                            <td style="padding-right: 12px;">
                                <div style="width: 44px; height: 44px; background: rgba(255,255,255,0.2); border-radius: 12px; display: inline-block; text-align: center; line-height: 44px;">
                                    <span style="font-size: 24px; color: #ffffff;">✦</span>
                                </div>
                            </td>
                            <td>
                                <span style="font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 26px; font-weight: 700; color: #ffffff; letter-spacing: -0.5px;">
                                    <span style="opacity: 0.75;">Re</span>reflect
                                </span>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </td>
</tr>
"""

EMAIL_FOOTER = """
<!-- Footer -->
<tr>
    <td style="padding: 32px 40px; background-color: #faf8f5; border-top: 1px solid #ede8e3; border-radius: 0 0 16px 16px;">
        <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
                <td style="text-align: center;">
                    <p style="margin: 0 0 16px 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 13px; color: #78716c;">
                        Made with care by the Rereflect team
                    </p>
                    <table cellpadding="0" cellspacing="0" style="margin: 0 auto;">
                        <tr>
                            <td style="padding: 0 8px;">
                                <a href="https://rereflect.ca" style="font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 12px; color: #f97316; text-decoration: none;">Website</a>
                            </td>
                            <td style="color: #ede8e3;">|</td>
                            <td style="padding: 0 8px;">
                                <a href="https://rereflect.ca/privacy" style="font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 12px; color: #f97316; text-decoration: none;">Privacy</a>
                            </td>
                            <td style="color: #ede8e3;">|</td>
                            <td style="padding: 0 8px;">
                                <a href="https://rereflect.ca/terms" style="font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 12px; color: #f97316; text-decoration: none;">Terms</a>
                            </td>
                        </tr>
                    </table>
                    <p style="margin: 16px 0 0 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 11px; color: #a39e99;">
                        © 2025 Rereflect Inc. All rights reserved.
                    </p>
                </td>
            </tr>
        </table>
    </td>
</tr>
"""

# =============================================================================
# TEAM INVITE TEMPLATE
# =============================================================================

TEAM_INVITE_TEMPLATE = {
    "name": "team-invite",
    "subject": "You've been invited to join {{{ORGANIZATION_NAME}}} on Rereflect",
    "html": """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="x-apple-disable-message-reformatting" />
    <title>You're Invited to Rereflect</title>
    <!--[if mso]>
    <style type="text/css">
        table {border-collapse: collapse;}
        .fallback-font {font-family: 'Segoe UI', Arial, sans-serif !important;}
    </style>
    <![endif]-->
</head>
<body style="margin: 0; padding: 0; background-color: #faf8f5; font-family: 'Montserrat', 'Segoe UI', Tahoma, sans-serif; -webkit-font-smoothing: antialiased;">
    <!-- Preview Text -->
    <div style="display: none; max-height: 0; overflow: hidden;">
        {{{INVITER_EMAIL}}} invited you to join {{{ORGANIZATION_NAME}}} – Transform customer feedback into actionable insights
        &#847; &#847; &#847; &#847; &#847; &#847; &#847; &#847; &#847; &#847;
    </div>

    <!-- Email Container -->
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #faf8f5; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 580px; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.06);">

                    <!-- Header -->
                    <tr>
                        <td style="padding: 0;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background: linear-gradient(135deg, #f97316 0%, #ea580c 50%, #dc5407 100%); border-radius: 16px 16px 0 0;">
                                <tr>
                                    <td style="padding: 40px 40px 32px 40px;">
                                        <table cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td style="padding-right: 12px; vertical-align: middle;">
                                                    <div style="width: 44px; height: 44px; background: rgba(255,255,255,0.2); border-radius: 12px; text-align: center; line-height: 44px;">
                                                        <span style="font-size: 22px;">✦</span>
                                                    </div>
                                                </td>
                                                <td style="vertical-align: middle;">
                                                    <span style="font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 26px; font-weight: 700; color: #ffffff; letter-spacing: -0.5px;">
                                                        <span style="opacity: 0.75;">Re</span>reflect
                                                    </span>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Main Content -->
                    <tr>
                        <td style="padding: 48px 40px;">
                            <!-- Invitation Badge -->
                            <table cellpadding="0" cellspacing="0" style="margin-bottom: 24px;">
                                <tr>
                                    <td style="background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); padding: 8px 16px; border-radius: 20px;">
                                        <span style="font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 12px; font-weight: 600; color: #b45309; text-transform: uppercase; letter-spacing: 0.5px;">
                                            ✨ You're Invited
                                        </span>
                                    </td>
                                </tr>
                            </table>

                            <h1 style="margin: 0 0 16px 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 28px; font-weight: 700; color: #3d2f2b; line-height: 1.3;">
                                Join {{{ORGANIZATION_NAME}}}
                            </h1>

                            <p style="margin: 0 0 28px 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 16px; color: #78716c; line-height: 1.7;">
                                <strong style="color: #3d2f2b;">{{{INVITER_EMAIL}}}</strong> has invited you to join their team as a <strong style="color: #f97316;">{{{ROLE}}}</strong>.
                            </p>

                            <!-- Info Card -->
                            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #faf8f5; border-radius: 12px; margin-bottom: 32px;">
                                <tr>
                                    <td style="padding: 24px;">
                                        <table cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td style="padding-bottom: 16px;">
                                                    <table cellpadding="0" cellspacing="0">
                                                        <tr>
                                                            <td style="width: 40px; height: 40px; background: linear-gradient(135deg, #f97316 0%, #ea580c 100%); border-radius: 10px; text-align: center; vertical-align: middle;">
                                                                <span style="font-size: 18px;">🏢</span>
                                                            </td>
                                                            <td style="padding-left: 14px;">
                                                                <p style="margin: 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 11px; color: #a39e99; text-transform: uppercase; letter-spacing: 0.5px;">Organization</p>
                                                                <p style="margin: 2px 0 0 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 15px; font-weight: 600; color: #3d2f2b;">{{{ORGANIZATION_NAME}}}</p>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td>
                                                    <table cellpadding="0" cellspacing="0">
                                                        <tr>
                                                            <td style="width: 40px; height: 40px; background: linear-gradient(135deg, #e5a366 0%, #d49356 100%); border-radius: 10px; text-align: center; vertical-align: middle;">
                                                                <span style="font-size: 18px;">👤</span>
                                                            </td>
                                                            <td style="padding-left: 14px;">
                                                                <p style="margin: 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 11px; color: #a39e99; text-transform: uppercase; letter-spacing: 0.5px;">Your Role</p>
                                                                <p style="margin: 2px 0 0 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 15px; font-weight: 600; color: #3d2f2b; text-transform: capitalize;">{{{ROLE}}}</p>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>

                            <!-- CTA Button -->
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td align="center">
                                        <table cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td style="background: linear-gradient(135deg, #f97316 0%, #ea580c 100%); border-radius: 12px; box-shadow: 0 4px 14px rgba(249, 115, 22, 0.35);">
                                                    <a href="{{{INVITE_URL}}}" style="display: inline-block; padding: 16px 40px; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 16px; font-weight: 600; color: #ffffff; text-decoration: none;">
                                                        Accept Invitation →
                                                    </a>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>

                            <!-- Expiry Notice -->
                            <p style="margin: 28px 0 0 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 13px; color: #a39e99; text-align: center;">
                                This invitation expires in 7 days
                            </p>
                        </td>
                    </tr>

                    <!-- Features Section -->
                    <tr>
                        <td style="padding: 0 40px 40px 40px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="border-top: 1px solid #ede8e3; padding-top: 32px;">
                                <tr>
                                    <td>
                                        <p style="margin: 0 0 20px 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 13px; font-weight: 600; color: #78716c; text-transform: uppercase; letter-spacing: 0.5px;">
                                            What you'll get access to
                                        </p>
                                    </td>
                                </tr>
                                <tr>
                                    <td>
                                        <table cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td style="padding: 8px 0;">
                                                    <span style="font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 14px; color: #3d2f2b;">
                                                        <span style="color: #f97316; margin-right: 8px;">◆</span> AI-powered sentiment analysis
                                                    </span>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0;">
                                                    <span style="font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 14px; color: #3d2f2b;">
                                                        <span style="color: #f97316; margin-right: 8px;">◆</span> Pain point detection & prioritization
                                                    </span>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0;">
                                                    <span style="font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 14px; color: #3d2f2b;">
                                                        <span style="color: #f97316; margin-right: 8px;">◆</span> Feature request tracking
                                                    </span>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0;">
                                                    <span style="font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 14px; color: #3d2f2b;">
                                                        <span style="color: #f97316; margin-right: 8px;">◆</span> Real-time Slack notifications
                                                    </span>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 28px 40px; background-color: #faf8f5; border-top: 1px solid #ede8e3; border-radius: 0 0 16px 16px;">
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td style="text-align: center;">
                                        <p style="margin: 0 0 12px 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 12px; color: #a39e99;">
                                            Didn't expect this? You can safely ignore this email.
                                        </p>
                                        <p style="margin: 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 11px; color: #c4c0bb;">
                                            © 2025 Rereflect · Transform feedback into insights
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>""",
    "variables": [
        {"key": "ORGANIZATION_NAME", "type": "string", "fallback_value": "the team"},
        {"key": "INVITER_EMAIL", "type": "string", "fallback_value": "A team member"},
        {"key": "ROLE", "type": "string", "fallback_value": "member"},
        {"key": "INVITE_URL", "type": "string", "fallback_value": "https://app.rereflect.ca"},
    ]
}


# =============================================================================
# WELCOME TEMPLATE
# =============================================================================

WELCOME_TEMPLATE = {
    "name": "welcome",
    "subject": "Welcome to Rereflect! Let's get started 🎉",
    "html": """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="x-apple-disable-message-reformatting" />
    <title>Welcome to Rereflect</title>
</head>
<body style="margin: 0; padding: 0; background-color: #faf8f5; font-family: 'Montserrat', 'Segoe UI', Tahoma, sans-serif; -webkit-font-smoothing: antialiased;">
    <!-- Preview Text -->
    <div style="display: none; max-height: 0; overflow: hidden;">
        Welcome aboard! Here's everything you need to start transforming customer feedback into insights.
        &#847; &#847; &#847; &#847; &#847;
    </div>

    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #faf8f5; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 580px; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.06);">

                    <!-- Celebratory Header -->
                    <tr>
                        <td style="padding: 0;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background: linear-gradient(135deg, #f97316 0%, #ea580c 50%, #dc5407 100%); border-radius: 16px 16px 0 0;">
                                <tr>
                                    <td style="padding: 48px 40px; text-align: center;">
                                        <!-- Celebration Icon -->
                                        <div style="width: 72px; height: 72px; background: rgba(255,255,255,0.2); border-radius: 20px; margin: 0 auto 20px auto; line-height: 72px;">
                                            <span style="font-size: 36px;">🎉</span>
                                        </div>
                                        <h1 style="margin: 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 32px; font-weight: 700; color: #ffffff;">
                                            Welcome to Rereflect!
                                        </h1>
                                        <p style="margin: 12px 0 0 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 16px; color: rgba(255,255,255,0.85);">
                                            You're now part of <strong>{{{ORGANIZATION_NAME}}}</strong>
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Main Content -->
                    <tr>
                        <td style="padding: 48px 40px 40px 40px;">
                            <p style="margin: 0 0 32px 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 16px; color: #78716c; line-height: 1.7;">
                                We're thrilled to have you! Rereflect helps you transform raw customer feedback into actionable insights using AI-powered analysis.
                            </p>

                            <!-- Getting Started Steps -->
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 36px;">
                                <tr>
                                    <td>
                                        <p style="margin: 0 0 20px 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 14px; font-weight: 700; color: #3d2f2b; text-transform: uppercase; letter-spacing: 0.5px;">
                                            Get started in 3 steps
                                        </p>
                                    </td>
                                </tr>

                                <!-- Step 1 -->
                                <tr>
                                    <td style="padding-bottom: 16px;">
                                        <table cellpadding="0" cellspacing="0" style="background-color: #faf8f5; border-radius: 12px; width: 100%;">
                                            <tr>
                                                <td style="padding: 20px;">
                                                    <table cellpadding="0" cellspacing="0">
                                                        <tr>
                                                            <td style="width: 48px; vertical-align: top;">
                                                                <div style="width: 40px; height: 40px; background: linear-gradient(135deg, #f97316 0%, #ea580c 100%); border-radius: 10px; text-align: center; line-height: 40px;">
                                                                    <span style="font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 16px; font-weight: 700; color: #ffffff;">1</span>
                                                                </div>
                                                            </td>
                                                            <td style="vertical-align: top;">
                                                                <p style="margin: 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 15px; font-weight: 600; color: #3d2f2b;">
                                                                    Submit your first feedback
                                                                </p>
                                                                <p style="margin: 4px 0 0 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 13px; color: #78716c;">
                                                                    Paste any customer feedback to see AI analysis in action
                                                                </p>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>

                                <!-- Step 2 -->
                                <tr>
                                    <td style="padding-bottom: 16px;">
                                        <table cellpadding="0" cellspacing="0" style="background-color: #faf8f5; border-radius: 12px; width: 100%;">
                                            <tr>
                                                <td style="padding: 20px;">
                                                    <table cellpadding="0" cellspacing="0">
                                                        <tr>
                                                            <td style="width: 48px; vertical-align: top;">
                                                                <div style="width: 40px; height: 40px; background: linear-gradient(135deg, #e5a366 0%, #d49356 100%); border-radius: 10px; text-align: center; line-height: 40px;">
                                                                    <span style="font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 16px; font-weight: 700; color: #ffffff;">2</span>
                                                                </div>
                                                            </td>
                                                            <td style="vertical-align: top;">
                                                                <p style="margin: 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 15px; font-weight: 600; color: #3d2f2b;">
                                                                    Connect Slack
                                                                </p>
                                                                <p style="margin: 4px 0 0 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 13px; color: #78716c;">
                                                                    Get real-time alerts when urgent feedback comes in
                                                                </p>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>

                                <!-- Step 3 -->
                                <tr>
                                    <td>
                                        <table cellpadding="0" cellspacing="0" style="background-color: #faf8f5; border-radius: 12px; width: 100%;">
                                            <tr>
                                                <td style="padding: 20px;">
                                                    <table cellpadding="0" cellspacing="0">
                                                        <tr>
                                                            <td style="width: 48px; vertical-align: top;">
                                                                <div style="width: 40px; height: 40px; background: linear-gradient(135deg, #78716c 0%, #5c5650 100%); border-radius: 10px; text-align: center; line-height: 40px;">
                                                                    <span style="font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 16px; font-weight: 700; color: #ffffff;">3</span>
                                                                </div>
                                                            </td>
                                                            <td style="vertical-align: top;">
                                                                <p style="margin: 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 15px; font-weight: 600; color: #3d2f2b;">
                                                                    Explore insights
                                                                </p>
                                                                <p style="margin: 4px 0 0 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 13px; color: #78716c;">
                                                                    Discover pain points, feature requests, and trends
                                                                </p>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>

                            <!-- CTA Button -->
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td align="center">
                                        <table cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td style="background: linear-gradient(135deg, #f97316 0%, #ea580c 100%); border-radius: 12px; box-shadow: 0 4px 14px rgba(249, 115, 22, 0.35);">
                                                    <a href="{{{DASHBOARD_URL}}}" style="display: inline-block; padding: 16px 40px; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 16px; font-weight: 600; color: #ffffff; text-decoration: none;">
                                                        Go to Dashboard →
                                                    </a>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Help Section -->
                    <tr>
                        <td style="padding: 0 40px 40px 40px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); border-radius: 12px;">
                                <tr>
                                    <td style="padding: 24px;">
                                        <table cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td style="width: 48px; vertical-align: top;">
                                                    <span style="font-size: 28px;">💬</span>
                                                </td>
                                                <td>
                                                    <p style="margin: 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 14px; font-weight: 600; color: #92400e;">
                                                        Need help getting started?
                                                    </p>
                                                    <p style="margin: 6px 0 0 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 13px; color: #b45309;">
                                                        Reply to this email – our team reads every message!
                                                    </p>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 28px 40px; background-color: #faf8f5; border-top: 1px solid #ede8e3; border-radius: 0 0 16px 16px;">
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td style="text-align: center;">
                                        <p style="margin: 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 11px; color: #c4c0bb;">
                                            © 2025 Rereflect · Transform feedback into insights
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>""",
    "variables": [
        {"key": "ORGANIZATION_NAME", "type": "string", "fallback_value": "your organization"},
        {"key": "DASHBOARD_URL", "type": "string", "fallback_value": "https://app.rereflect.ca/dashboard"},
    ]
}


# =============================================================================
# PASSWORD RESET TEMPLATE
# =============================================================================

PASSWORD_RESET_TEMPLATE = {
    "name": "password-reset",
    "subject": "Reset your Rereflect password",
    "html": """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="x-apple-disable-message-reformatting" />
    <title>Reset Your Password</title>
</head>
<body style="margin: 0; padding: 0; background-color: #faf8f5; font-family: 'Montserrat', 'Segoe UI', Tahoma, sans-serif; -webkit-font-smoothing: antialiased;">
    <!-- Preview Text -->
    <div style="display: none; max-height: 0; overflow: hidden;">
        Reset your password to regain access to your Rereflect account
        &#847; &#847; &#847; &#847; &#847;
    </div>

    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #faf8f5; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 520px; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.06);">

                    <!-- Header -->
                    <tr>
                        <td style="padding: 40px 40px 0 40px; text-align: center;">
                            <table cellpadding="0" cellspacing="0" style="margin: 0 auto;">
                                <tr>
                                    <td style="padding-right: 12px; vertical-align: middle;">
                                        <div style="width: 44px; height: 44px; background: linear-gradient(135deg, #f97316 0%, #ea580c 100%); border-radius: 12px; text-align: center; line-height: 44px;">
                                            <span style="font-size: 22px;">✦</span>
                                        </div>
                                    </td>
                                    <td style="vertical-align: middle;">
                                        <span style="font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 24px; font-weight: 700; color: #3d2f2b; letter-spacing: -0.5px;">
                                            <span style="color: #78716c;">Re</span>reflect
                                        </span>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Main Content -->
                    <tr>
                        <td style="padding: 40px;">
                            <!-- Lock Icon -->
                            <div style="width: 64px; height: 64px; background-color: #fef3c7; border-radius: 16px; margin: 0 auto 24px auto; text-align: center; line-height: 64px;">
                                <span style="font-size: 32px;">🔐</span>
                            </div>

                            <h1 style="margin: 0 0 16px 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 24px; font-weight: 700; color: #3d2f2b; text-align: center;">
                                Reset your password
                            </h1>

                            <p style="margin: 0 0 32px 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 15px; color: #78716c; line-height: 1.7; text-align: center;">
                                We received a request to reset the password for your account. Click the button below to create a new password.
                            </p>

                            <!-- CTA Button -->
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td align="center">
                                        <table cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td style="background: linear-gradient(135deg, #f97316 0%, #ea580c 100%); border-radius: 12px; box-shadow: 0 4px 14px rgba(249, 115, 22, 0.35);">
                                                    <a href="{{{RESET_URL}}}" style="display: inline-block; padding: 16px 40px; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 16px; font-weight: 600; color: #ffffff; text-decoration: none;">
                                                        Reset Password
                                                    </a>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>

                            <!-- Expiry Notice -->
                            <p style="margin: 28px 0 0 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 13px; color: #a39e99; text-align: center;">
                                This link expires in 1 hour
                            </p>

                            <!-- Divider -->
                            <div style="height: 1px; background-color: #ede8e3; margin: 32px 0;"></div>

                            <!-- Security Notice -->
                            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #faf8f5; border-radius: 10px;">
                                <tr>
                                    <td style="padding: 16px;">
                                        <p style="margin: 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 13px; color: #78716c; text-align: center;">
                                            <strong style="color: #3d2f2b;">Didn't request this?</strong><br />
                                            You can safely ignore this email. Your password won't change.
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 28px 40px; background-color: #faf8f5; border-top: 1px solid #ede8e3; border-radius: 0 0 16px 16px;">
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td style="text-align: center;">
                                        <p style="margin: 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 11px; color: #c4c0bb;">
                                            © 2025 Rereflect · Transform feedback into insights
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>""",
    "variables": [
        {"key": "RESET_URL", "type": "string", "fallback_value": "https://app.rereflect.ca/reset-password"},
    ]
}


# =============================================================================
# WEEKLY DIGEST TEMPLATE
# =============================================================================

WEEKLY_DIGEST_TEMPLATE = {
    "name": "weekly-digest",
    "subject": "Your weekly feedback insights from {{{ORGANIZATION_NAME}}}",
    "html": """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="x-apple-disable-message-reformatting" />
    <title>Weekly Feedback Digest</title>
</head>
<body style="margin: 0; padding: 0; background-color: #faf8f5; font-family: 'Montserrat', 'Segoe UI', Tahoma, sans-serif; -webkit-font-smoothing: antialiased;">
    <!-- Preview Text -->
    <div style="display: none; max-height: 0; overflow: hidden;">
        {{{TOTAL_FEEDBACK}}} new pieces of feedback this week – see what your customers are saying
        &#847; &#847; &#847; &#847; &#847;
    </div>

    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #faf8f5; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.06);">

                    <!-- Header -->
                    <tr>
                        <td style="padding: 0;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background: linear-gradient(135deg, #f97316 0%, #ea580c 50%, #dc5407 100%); border-radius: 16px 16px 0 0;">
                                <tr>
                                    <td style="padding: 32px 40px;">
                                        <table width="100%" cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td>
                                                    <table cellpadding="0" cellspacing="0">
                                                        <tr>
                                                            <td style="padding-right: 12px; vertical-align: middle;">
                                                                <div style="width: 40px; height: 40px; background: rgba(255,255,255,0.2); border-radius: 10px; text-align: center; line-height: 40px;">
                                                                    <span style="font-size: 18px;">✦</span>
                                                                </div>
                                                            </td>
                                                            <td style="vertical-align: middle;">
                                                                <span style="font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 22px; font-weight: 700; color: #ffffff;">
                                                                    <span style="opacity: 0.75;">Re</span>reflect
                                                                </span>
                                                            </td>
                                                        </tr>
                                                    </table>
                                                </td>
                                                <td style="text-align: right;">
                                                    <span style="font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 13px; color: rgba(255,255,255,0.8);">
                                                        📊 Weekly Digest
                                                    </span>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Stats Overview -->
                    <tr>
                        <td style="padding: 40px 40px 32px 40px;">
                            <h1 style="margin: 0 0 8px 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 24px; font-weight: 700; color: #3d2f2b;">
                                Week of {{{WEEK_DATE}}}
                            </h1>
                            <p style="margin: 0 0 28px 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 15px; color: #78716c;">
                                Here's what your customers shared with <strong style="color: #3d2f2b;">{{{ORGANIZATION_NAME}}}</strong>
                            </p>

                            <!-- Stats Grid -->
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <!-- Total Feedback -->
                                    <td width="33%" style="padding: 0 8px 0 0;">
                                        <table cellpadding="0" cellspacing="0" style="background-color: #faf8f5; border-radius: 12px; width: 100%;">
                                            <tr>
                                                <td style="padding: 20px; text-align: center;">
                                                    <p style="margin: 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 28px; font-weight: 700; color: #f97316;">
                                                        {{{TOTAL_FEEDBACK}}}
                                                    </p>
                                                    <p style="margin: 4px 0 0 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 11px; color: #78716c; text-transform: uppercase; letter-spacing: 0.5px;">
                                                        Total Feedback
                                                    </p>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                    <!-- Pain Points -->
                                    <td width="33%" style="padding: 0 4px;">
                                        <table cellpadding="0" cellspacing="0" style="background-color: #fef3c7; border-radius: 12px; width: 100%;">
                                            <tr>
                                                <td style="padding: 20px; text-align: center;">
                                                    <p style="margin: 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 28px; font-weight: 700; color: #b45309;">
                                                        {{{PAIN_POINTS}}}
                                                    </p>
                                                    <p style="margin: 4px 0 0 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 11px; color: #92400e; text-transform: uppercase; letter-spacing: 0.5px;">
                                                        Pain Points
                                                    </p>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                    <!-- Feature Requests -->
                                    <td width="33%" style="padding: 0 0 0 8px;">
                                        <table cellpadding="0" cellspacing="0" style="background-color: #f0fdf4; border-radius: 12px; width: 100%;">
                                            <tr>
                                                <td style="padding: 20px; text-align: center;">
                                                    <p style="margin: 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 28px; font-weight: 700; color: #16a34a;">
                                                        {{{FEATURE_REQUESTS}}}
                                                    </p>
                                                    <p style="margin: 4px 0 0 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 11px; color: #15803d; text-transform: uppercase; letter-spacing: 0.5px;">
                                                        Feature Reqs
                                                    </p>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Sentiment Breakdown -->
                    <tr>
                        <td style="padding: 0 40px 32px 40px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #faf8f5; border-radius: 12px;">
                                <tr>
                                    <td style="padding: 24px;">
                                        <p style="margin: 0 0 16px 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 13px; font-weight: 600; color: #3d2f2b; text-transform: uppercase; letter-spacing: 0.5px;">
                                            Sentiment Breakdown
                                        </p>

                                        <!-- Sentiment Bar -->
                                        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 12px;">
                                            <tr>
                                                <td style="height: 10px; background-color: #22c55e; border-radius: 5px 0 0 5px; width: {{{POSITIVE_PERCENT}}}%;"></td>
                                                <td style="height: 10px; background-color: #78716c; width: {{{NEUTRAL_PERCENT}}}%;"></td>
                                                <td style="height: 10px; background-color: #ef4444; border-radius: 0 5px 5px 0; width: {{{NEGATIVE_PERCENT}}}%;"></td>
                                            </tr>
                                        </table>

                                        <table width="100%" cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td>
                                                    <span style="font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 12px; color: #22c55e;">● {{{POSITIVE_PERCENT}}}% Positive</span>
                                                </td>
                                                <td style="text-align: center;">
                                                    <span style="font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 12px; color: #78716c;">● {{{NEUTRAL_PERCENT}}}% Neutral</span>
                                                </td>
                                                <td style="text-align: right;">
                                                    <span style="font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 12px; color: #ef4444;">● {{{NEGATIVE_PERCENT}}}% Negative</span>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Urgent Items Alert -->
                    <tr>
                        <td style="padding: 0 40px 32px 40px;">
                            <table width="100%" cellpadding="0" cellspacing="0" style="background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%); border-radius: 12px; border-left: 4px solid #ef4444;">
                                <tr>
                                    <td style="padding: 20px;">
                                        <table cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td style="width: 40px; vertical-align: top;">
                                                    <span style="font-size: 24px;">🚨</span>
                                                </td>
                                                <td>
                                                    <p style="margin: 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 14px; font-weight: 600; color: #dc2626;">
                                                        {{{URGENT_COUNT}}} urgent items need attention
                                                    </p>
                                                    <p style="margin: 6px 0 0 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 13px; color: #991b1b;">
                                                        Review high-priority feedback that may indicate churn risk
                                                    </p>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- CTA Button -->
                    <tr>
                        <td style="padding: 0 40px 40px 40px;">
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td align="center">
                                        <table cellpadding="0" cellspacing="0">
                                            <tr>
                                                <td style="background: linear-gradient(135deg, #f97316 0%, #ea580c 100%); border-radius: 12px; box-shadow: 0 4px 14px rgba(249, 115, 22, 0.35);">
                                                    <a href="{{{DASHBOARD_URL}}}" style="display: inline-block; padding: 16px 40px; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 16px; font-weight: 600; color: #ffffff; text-decoration: none;">
                                                        View Full Report →
                                                    </a>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 28px 40px; background-color: #faf8f5; border-top: 1px solid #ede8e3; border-radius: 0 0 16px 16px;">
                            <table width="100%" cellpadding="0" cellspacing="0">
                                <tr>
                                    <td style="text-align: center;">
                                        <p style="margin: 0 0 8px 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 12px; color: #a39e99;">
                                            You're receiving this because you're part of {{{ORGANIZATION_NAME}}}
                                        </p>
                                        <p style="margin: 0; font-family: 'Montserrat', 'Segoe UI', sans-serif; font-size: 11px; color: #c4c0bb;">
                                            © 2025 Rereflect · <a href="{{{UNSUBSCRIBE_URL}}}" style="color: #c4c0bb;">Unsubscribe from digests</a>
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>""",
    "variables": [
        {"key": "ORGANIZATION_NAME", "type": "string", "fallback_value": "your organization"},
        {"key": "WEEK_DATE", "type": "string", "fallback_value": "This Week"},
        {"key": "TOTAL_FEEDBACK", "type": "number", "fallback_value": 0},
        {"key": "PAIN_POINTS", "type": "number", "fallback_value": 0},
        {"key": "FEATURE_REQUESTS", "type": "number", "fallback_value": 0},
        {"key": "POSITIVE_PERCENT", "type": "number", "fallback_value": 33},
        {"key": "NEUTRAL_PERCENT", "type": "number", "fallback_value": 34},
        {"key": "NEGATIVE_PERCENT", "type": "number", "fallback_value": 33},
        {"key": "URGENT_COUNT", "type": "number", "fallback_value": 0},
        {"key": "DASHBOARD_URL", "type": "string", "fallback_value": "https://app.rereflect.ca/dashboard"},
        {"key": "UNSUBSCRIBE_URL", "type": "string", "fallback_value": "https://app.rereflect.ca/settings/notifications"},
    ]
}


# All templates for easy import
ALL_TEMPLATES = [
    TEAM_INVITE_TEMPLATE,
    WELCOME_TEMPLATE,
    PASSWORD_RESET_TEMPLATE,
    WEEKLY_DIGEST_TEMPLATE,
]
