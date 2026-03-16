# Outreach Tracking

**Goal**: 10 signups in 4 weeks via LinkedIn outreach
**Time Budget**: ~1 hour/week
**Primary Channel**: LinkedIn DMs
**Incentive**: 3 months free Pro plan
**Start Date**: 2026-02-17
**Last Updated**: 2026-03-17

> **Note:** Outreach paused while focusing on content marketing and SEO. Will resume when blog traffic generates warm leads.

---

## Current Metrics

| Metric | Week 1 | Week 2 | Week 3 | Week 4 | Total |
|--------|--------|--------|--------|--------|-------|
| Prospects researched | - | - | - | - | 0 |
| LinkedIn DMs sent | - | - | - | - | 0 |
| DM replies received | - | - | - | - | 0 |
| Follow-up emails sent | - | - | - | - | 0 |
| Demos booked | - | - | - | - | 0 |
| Signups | - | - | - | - | 0 |

**Target reply rate**: >20% (LinkedIn DMs typically outperform cold email)
**Target signup rate**: >30% of replies

---

## Weekly Playbook (1 Hour/Week)

With only 1 hour/week, every minute counts. Here's the optimized routine:

### Monday (30 min): Research + Send DMs

1. **Find 5-7 prospects** (15 min)
   - Search LinkedIn: "Head of Product" OR "Founder" + "SaaS" + seed/series A
   - Check Product Hunt recent launches (founders are active on LinkedIn)
   - Browse #buildinpublic on X, find their LinkedIn profiles
   - Look at Indie Hackers "launched" section

2. **Send personalized DMs** (15 min)
   - Use Template A or B below
   - Personalize the first line (mention their product/recent post)
   - Log each prospect in the tracker below

### Thursday (20 min): Follow Up + Engage

1. **Reply to any responses** (10 min)
   - Answer questions, offer demo or direct signup link
   - Send follow-up email to anyone who showed interest (use rereflect.ca email)

2. **Follow up on Monday's DMs** (10 min)
   - If no reply after 3 days, send a brief follow-up (Template C)
   - Don't follow up more than once

### Friday (10 min): Log Results

1. Update the metrics table above
2. Note what worked/didn't in Weekly Learnings below
3. Add any new prospect sources discovered

---

## LinkedIn DM Templates

### Template A: Recent Launch / Active Founder

```
Hey [Name]! Just came across [Product] — really cool what you're building.

Quick question: how are you currently handling customer feedback as you scale?

I built Rereflect (rereflect.ca) — it uses AI to auto-categorize feedback into pain points, feature requests, and churn risk alerts.

Happy to give you 3 months of Pro free if you'd try it and share honest feedback. No strings attached.
```

### Template B: Product Hunt / Indie Hackers Founder

```
Hey [Name], saw your launch on [Product Hunt / Indie Hackers] — congrats on the traction!

Now that users are rolling in, are you finding it hard to keep track of all the feedback?

I'm working on Rereflect — it auto-analyzes customer feedback (pain points, feature requests, churn signals). Takes 30 seconds to upload a CSV and see results.

Offering 3 months free Pro to early adopters who share feedback. Want to give it a spin?
```

### Template C: Follow-Up (3 days later, if no reply)

```
Hey [Name], just bumping this in case it got buried. No pressure at all!

If feedback management isn't a pain point right now, totally get it. But the offer for 3 months free Pro stands if you ever want to try it: app.rereflect.ca/signup?promo=EARLYPRO3
```

### Template D: Post-Interest Reply (move to email)

```
Awesome, glad you're interested! I'll send you the details to your email so it's easier to find.

What email should I use? Or I can send to the one on your LinkedIn profile.
```

### Follow-Up Email (from ali@rereflect.ca)

```
Subject: Your 3-month Pro access to Rereflect

Hi [Name],

Great chatting on LinkedIn! As promised, here's your free Pro access:

1. Sign up at https://app.rereflect.ca/signup
2. Use promo code EARLYPRO3 at checkout (or applied automatically via link)
3. Upload a CSV of customer feedback and see the AI analysis in action

Your Pro plan includes:
- 2,500 feedback items/month
- Slack integration
- Trend analytics
- Data export
- Priority support

I'd love to hear what you think after you try it. Feel free to reply to this email or book a 15-min call: [BOOKING_LINK]

Cheers,
Ali
```

---

## Prospect Tracker

### Qualification Criteria
- SaaS company (B2B or B2C)
- 5-50 employees
- Has a live product with users
- Founder/PM is active on LinkedIn
- Shows signs of growth (recent launch, hiring, funding)

### Prospect List

> **Paused** — focusing on inbound marketing channels first. Will activate outreach when we have case studies and social proof to reference.

| # | Name | Company | Role | LinkedIn | Status | DM Sent | Replied | Signed Up | Notes |
|---|------|---------|------|----------|--------|---------|---------|-----------|-------|
| 1 | | | | | | | | | |
| 2 | | | | | | | | | |
| 3 | | | | | | | | | |
| 4 | | | | | | | | | |
| 5 | | | | | | | | | |
| 6 | | | | | | | | | |
| 7 | | | | | | | | | |
| 8 | | | | | | | | | |
| 9 | | | | | | | | | |
| 10 | | | | | | | | | |

**Status values**: `researched` → `dm_sent` → `replied` → `interested` → `signed_up` → `activated` | `no_reply` | `not_interested`

---

## Prospect Sources (Where to Find People)

| Source | How | Time | Quality |
|--------|-----|------|---------|
| LinkedIn Search | "Head of Product" + "SaaS" + Seed/A | 2 min/prospect | High |
| Product Hunt (recent) | Browse /topics/saas, find founders on LinkedIn | 3 min/prospect | High |
| Indie Hackers | Browse /products, check milestones | 2 min/prospect | Medium |
| Twitter/X #buildinpublic | Find founders, check LinkedIn | 3 min/prospect | Medium |
| r/SaaS active posters | Check post history, find LinkedIn | 4 min/prospect | Medium |

---

## Engineering Tasks (Required)

### Stripe: 3-Month Free Pro Promo Code
- [x] Create Stripe coupon: 100% off for 3 months on Pro plan ($29/mo)
- [x] Create promo code: `EARLYPRO3` linked to the coupon (50 max redemptions, first-time only)
- [x] Add promo code redemption to checkout/signup flow
- [x] Promo-aware signup page: `app.rereflect.ca/signup?promo=EARLYPRO3`
- [x] Dashboard activation banner for promo users
- [x] Auto-apply promo at Stripe Checkout (no card required)
- [x] Promo analytics tracking (Mixpanel: Promo Signup, Promo Checkout Started)
- [x] Admin promo management UI at `/system/promo-codes` (create, list, deactivate, delete)
- [x] System admin user management (`/system/users`): list/search/filter, edit org+role+system admin, delete with FK cleanup
- [x] System admin org management (`/system/organizations`): list/search, detail view, delete empty orgs
- [x] FK constraint fixes for user/org deletion (migration + 11 model updates)
- [x] Auto-migration on deploy (Dockerfile runs `alembic upgrade head`)
- [x] Test end-to-end: signup → activate Pro → verify 3 months free → auto-downgrade (11 tests in test_promo_flow.py)

**Live link**: https://app.rereflect.ca/signup?promo=EARLYPRO3

### Optional Improvements
- [x] Create a direct signup link with promo auto-applied
- [ ] Add a "Redeem promo code" field in billing settings
- [ ] Set up Calendly or Cal.com for demo booking link

---

## Weekly Learnings

### Week 1 (Feb 17-21)
- *(Add what worked, what didn't, response patterns)*

### Week 2 (Feb 24-28)
-

### Week 3 (Mar 3-7)
-

### Week 4 (Mar 10-14)
-

---

## Outreach Rules

1. **Always personalize the first line** — mention their product, a recent post, or something specific
2. **Never copy-paste the exact template** — adjust tone to match their vibe
3. **Don't pitch in connection requests** — connect first, DM after they accept
4. **One follow-up max** — if no reply after follow-up, move on
5. **Track everything** — update the prospect table after every session
6. **Quality over quantity** — 5 great DMs beat 20 generic ones
7. **Be genuinely helpful** — if their problem isn't feedback, don't push it

---

## References

- [SALES-TRACKING.md](SALES-TRACKING.md) — Overall sales strategy and growth targets
- [DEV-TRACKING.md](DEV-TRACKING.md) — Development roadmap
