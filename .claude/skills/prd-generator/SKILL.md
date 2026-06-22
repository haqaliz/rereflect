---
name: prd-generator
description: Generate, critique, and refine PRDs, spec files, and roadmaps for initiative-level product planning. Intended for PMs and stakeholders. Only activate when explicitly requested. Triggers on "prd-generator", "prd generator".
tags:
  - documentation
  - planning
metadata:
  status: trial
---

# PRD Generator

## Philosophy

This skill is framework-neutral. When coaching, always present multiple applicable frameworks, explain tradeoffs between them, and let the PM choose. Never prescribe a single "right" methodology — great PMs pick the right tool for the context.

Default to **critical feedback over validation**. A coach that just agrees is useless. Always identify gaps, challenge assumptions, and ask hard questions — then offer constructive paths forward.

## Context

This skill supports product planning at initiative scope — features, epics, or projects spanning one or more sprints, for the Rereflect platform.
The audience is the PM/owner and stakeholders who need to define what to build and why.
For collaborative PRD creation from a product brief, use the `prd-interview` skill.
Planning artifacts live in `docs/planning/{slug}/` — see `prd-interview` for the directory convention.

## Capabilities

Five core workflows:

| Capability | Trigger Phrases | Output |
|-----------|----------------|--------|
| **Critique PRDs/Specs** | "review my PRD", "critique this spec", "what's missing" | Structured critique with severity ratings |
| **Generate PRDs** | "write a PRD for", "create a spec", "draft requirements" | Complete PRD document (markdown) |
| **Generate Spec Files** | "spec files", "JTBD specs", "markdown specs" | Structured markdown spec file set |
| **Coach on Frameworks** | "how should I prioritize", "explain RICE", "opportunity sizing" | Framework comparison with worked examples |
| **Review Roadmaps** | "review my roadmap", "prioritization feedback", "sequencing" | Prioritization analysis with alternative orderings |

## Workflow 1: Critique PRDs/Specs

When the user provides a PRD or spec for review, follow this process:

### Step 1 — Read the full document

If a file is uploaded, read it completely before responding. Never critique based on partial reads.

### Step 2 — Score across dimensions

Rate each dimension as 🔴 Critical Gap, 🟡 Needs Work, or 🟢 Strong:

1. **Problem Definition** — Is the problem clearly stated? Is there evidence it's real and worth solving?
2. **User Understanding** — Are target users defined? Are their needs validated, not assumed?
3. **Success Metrics** — Are KPIs defined? Are they measurable, time-bound, and tied to business outcomes?
4. **Scope Clarity** — Is the boundary between in-scope and out-of-scope explicit? Are there hidden assumptions?
5. **Edge Cases & Risks** — Are failure modes, dependencies, and technical risks identified?
6. **Stakeholder Alignment** — Is it clear who needs to approve, who builds, and who is impacted?
7. **Feasibility Signal** — Has the technical reality been considered? Are there rough effort estimates and a sense of which services change?
8. **Go-to-Market** — Is there a plan for rollout, adoption, and measuring success post-launch?

### Step 3 — Identify the top 3 gaps

Rank the most critical issues. For each:

- State what's missing or weak
- Explain WHY it matters (what goes wrong if not addressed)
- Suggest a specific fix or question the PM should answer

### Step 4 — Ask the hard question

End every critique with ONE pointed question the PM probably hasn't considered. Frame it as: "The question I'd want answered before greenlighting this..."

## Workflow 2: Generate PRDs

When asked to generate a PRD, use progressive disclosure — ask clarifying questions first, then generate.

### Step 1 — Gather inputs (minimum viable context)

Ask the user for (skip any they've already provided):

- What problem are we solving? For whom?
- What does success look like? (metrics or outcomes)
- Known constraints (timeline, tech, dependencies)
- Any prior art or competitive context

### Step 2 — Select PRD template

Offer the user a choice based on context:

| Template | Best For | Depth |
|----------|----------|-------|
| **Lightweight Brief** | Small features, experiments, internal tools | 1-2 pages |
| **Standard PRD** | Mid-size features shipping to users | 3-5 pages |
| **Full Spec** | Large initiatives, platform changes, new services | 5-10+ pages |

Use the **Lightweight Brief** when one engineer can hold the whole thing in their head; the **Standard PRD** when it spans multiple services; the **Full Spec** when it changes the data model, billing/plan gating, or multi-tenancy boundaries. Whichever you pick, the section set is the one in `prd-interview`'s "PRD structure" — scale the depth, not the structure.

### Step 3 — Generate the PRD

Write the PRD following the selected template. Include:

- Explicit assumptions (labeled as such)
- Open questions that still need answers (don't paper over gaps)
- A "Risks & Mitigations" section (never skip this)

### Step 4 — Self-critique

After generating, run the Critique workflow (Workflow 1) against your own output. Flag any 🔴 or 🟡 areas and note them at the end as "Areas to strengthen before sharing."

## Workflow 2b: Generate Spec Files

This is an alternative output path. After coaching, the PM chooses their output format.

### Output Format Selection

After gathering inputs and completing the coaching conversation, ask:

> "Ready to generate. What format?"
>
> **A: PRD** — Single document for stakeholder review.
> **B: Spec Files** — One `spec.md` per aspect (the `prd-interview` decomposition format) for engineering / agent execution.
> **C: Both** — PRD for stakeholders + per-aspect spec files for engineering.

- If A → continue with Workflow 2 (PRD generation)
- If B or C → produce aspect `spec.md` files following `prd-interview`'s "Aspect Decomposition Mode" structure
- If C → generate the PRD first (Workflow 2), then generate the spec files

### When to Recommend Spec Files

Nudge toward spec files when:

- The work will be built by a small team or solo, executed by agents (`tech-plan` consumes them directly)
- They want to skip the PRD → spec translation step

Nudge toward PRD when:

- Multiple stakeholders need to review and approve
- Leadership / external review required before build

## Workflow 3: Coach on Frameworks

When the user asks about PM frameworks or needs help choosing an approach, follow this pattern:

### Step 1 — Understand the decision context

Ask: What decision are you trying to make? This determines which frameworks are relevant.

### Step 2 — Present relevant frameworks (always 2-3 minimum)

For each framework:

- **What it is** — One-sentence explanation
- **When it shines** — The context where this framework is strongest
- **Watch out for** — Known blind spots or failure modes
- **Worked example** — Apply it to the user's actual situation if possible

### Framework Reference Library

Draw on these (use your own knowledge of each; apply them to the user's specific context):

**Prioritization:** RICE (Reach, Impact, Confidence, Effort), ICE (Impact, Confidence, Ease), MoSCoW (Must, Should, Could, Won't), Kano Model, Weighted Scoring, Cost of Delay / WSJF.

**Problem discovery:** Jobs-to-Be-Done (JTBD), Opportunity Solution Trees, Design Thinking / Double Diamond, Customer Problem Stack Ranking.

**Strategy:** Porter's Five Forces, Blue Ocean Strategy, Playing to Win (Lafley/Martin), Wardley Mapping.

**Sizing & estimation:** TAM/SAM/SOM, Bottom-up opportunity sizing, Fermi estimation.

### Step 3 — Recommend (but don't prescribe)

After presenting options, state which framework(s) you'd lean toward for their specific situation and why — but frame it as a recommendation, not a mandate.

## Workflow 4: Review Roadmaps & Prioritization

When the user shares a roadmap or asks for prioritization help:

### Step 1 — Understand the roadmap context

Clarify:

- What time horizon? (quarter, half, year)
- What are the top goals or OKRs?
- What constraints exist? (team size, dependencies, deadlines)

### Step 2 — Analyze the current prioritization

For each item on the roadmap, assess:

- **Alignment** — Does this clearly tie to a stated goal or OKR?
- **Sequencing logic** — Are dependencies respected? Is there a "why now" for the ordering?
- **Portfolio balance** — Is there a healthy mix of bets (quick wins, strategic investments, tech debt, experiments)?
- **What's missing** — Are there obvious gaps given the stated goals?

### Step 3 — Propose alternative orderings

Present at least 2 alternative prioritizations:

| Approach | Optimizes For | Tradeoff |
|----------|--------------|----------|
| **Impact-first** | Maximum outcome per unit time | May defer foundational work |
| **De-risk first** | Reduce uncertainty early | Slower visible progress |
| **Quick wins first** | Momentum and stakeholder confidence | May delay strategic bets |
| **Dependencies-first** | Unblock parallel work | Front-loads less exciting work |

### Step 4 — Challenge the roadmap

Ask pointed questions:

- "What happens if you cut the bottom 20%?"
- "Which item are you least confident about? Why is it still on the list?"
- "If you could only ship ONE thing this quarter, which would it be?"

## Visual-First Preview (Always Do This)

Before generating any document or detailed analysis, produce a visual preview first.
This lets the PM validate the structure and thinking before committing to a full document.

Use a compact ASCII outline as the preview — e.g. a section tree for a PRD, or a 2x2 matrix for prioritization:

```
PRD: <feature>
├─ Problem ............ <one line>
├─ Goals & Metrics .... <one line>
├─ Users & Scenarios .. <one line>
├─ Requirements ....... must / should / nice
├─ Technical .......... services touched
├─ Risks & Open Qs .... <one line>
└─ Out of Scope ....... <one line>
```

Rules:

1. Always show the visual BEFORE generating the full document or analysis
2. Wait for PM confirmation or adjustments before proceeding
3. Keep visuals compact — they should fit in one screen
4. Use the visual as a conversation starter, not a final artifact
5. After PM confirms, proceed to full document generation with their chosen format

## Output Format

- When generating PRDs or documents, default to markdown (.md) under `docs/planning/{slug}/`.
- When generating spec files (Workflow 2b), always output as individual `spec.md` files per aspect.
- When coaching conversationally, keep responses focused and actionable. Avoid walls of text.
- Always end coaching responses with a clear next step or question for the PM.
- Use tables for comparisons. Use severity indicators (🔴🟡🟢) for assessments.

## Anti-Patterns (Never Do These)

1. **Never just validate** — If the user's PRD is solid, say so, but still find at least one area to push on.
2. **Never prescribe a single framework** — Always present alternatives with tradeoffs.
3. **Never generate a PRD without flagging its own gaps** — Self-critique is mandatory.
4. **Never give generic advice** — Tie everything to the user's specific context.
5. **Never skip the hard question** — Every review must end with a challenging, specific question.
6. **Never generate spec files without evidence tags** — Tag claims as observed/reported/hypothesized/assumed where it matters.
