#!/usr/bin/env bash
#
# Honesty gates for the CRM churn-label docs (docs-and-tracking, AC-4 / AC-5).
#
# Two independent checks over the five surfaces that describe this feature:
#
#   AC-4  no churn-accuracy claims          -> DIFF-SCOPED (added lines only)
#   AC-5  confirm-required stated everywhere -> whole-file (a surface must SAY it)
#
# Why AC-4 is diff-scoped and not tree-wide:
#   services/landing-web/components/landing/BentoFeatures.tsx:197 ("Honest accuracy
#   tracking included.") and FAQ.tsx:41 are PRE-EXISTING and out of scope for this
#   branch. A tree-wide gate fails on day one, and a gate that fails on day one gets
#   disabled -- a disabled gate is worse than no gate. So AC-4 judges only what THIS
#   branch adds (`git diff $BASE..HEAD`, lines starting with '+').
#
# Usage:  bash scripts/check_docs_honesty.sh [base-ref]     (default base: master)

set -uo pipefail

BASE="${1:-master}"
cd "$(dirname "$0")/.."

SURFACES=(
  "docs/SELF_HOSTING.md"
  "CHANGELOG.md"
  "AI-TRACKING.md"
  "README.md"
  "services/landing-web"
)

fail=0

# Phrases that mean "this surface is describing THIS feature". Deliberately narrow:
# 'churn labels' alone matches pre-existing long-form content (landing-web/lib/blog.ts
# discusses churn labels generally), which would PASS AC-5 on a false positive.
FEATURE='churn[- ]label suggestion|churn suggestion|lost renewal'

# --- AC-4: no accuracy / ML claims in ADDED lines -----------------------------
# Each pattern is a claim this feature must never make. This feature produces
# LABELS; whether more labels improve the model is M5.3's open question.
BANNED='improves? accuracy|accuracy (gain|lift|improvement|boost)|more accurate|better (churn )?predictions?|\bAUC\b|automatically detects churn|auto-confirm|machine learning model predicts churn'

# Diff the merge-base against the WORKING TREE (not ...HEAD): an author needs the
# gate to fail on prose they just wrote, before it is committed. `BASE...HEAD` only
# sees committed content and would greenlight an uncommitted accuracy claim.
MERGE_BASE="$(git merge-base "$BASE" HEAD 2>/dev/null || echo "$BASE")"

echo "== AC-4: no accuracy claims (added lines only, ${BASE}...working tree) =="
added="$(git diff "${MERGE_BASE}" -- "${SURFACES[@]}" 2>/dev/null \
          | grep -E '^\+' | grep -Ev '^\+\+\+' || true)"

if [ -z "$added" ]; then
  echo "   (no added lines on the doc surfaces -- nothing to check)"
else
  hits="$(printf '%s\n' "$added" | grep -EIin "$BANNED" || true)"
  if [ -n "$hits" ]; then
    echo "   FAIL -- this branch ADDS accuracy/ML claims:"
    printf '%s\n' "$hits" | sed 's/^/     /'
    fail=1
  else
    echo "   PASS -- no accuracy/ML claims added."
  fi
fi

# --- AC-5: confirm-required stated on every surface ---------------------------
# Every surface that describes the feature must say, in its own words, that a
# human confirms. Matched as (human|operator|you) near (confirm|review).
CONFIRM='(human|operator|reviewer|you)[^.]{0,80}(confirm|review)|(confirm|review)[^.]{0,80}(by (a )?(human|operator|reviewer))|human-confirmed|operator-confirmed|human-reviewed|confirm each'

echo
echo "== AC-5: confirm-required stated on each surface =="
for s in "${SURFACES[@]}"; do
  if [ ! -e "$s" ]; then
    echo "   FAIL -- surface missing: $s"
    fail=1
    continue
  fi
  # Only consider files that actually mention this feature.
  # Vendor/build dirs are excluded: node_modules ships minified bundles that
  # match anything and would silently PASS the gate on a false positive.
  if [ -d "$s" ]; then
    scope="$(grep -rlIiE "$FEATURE" "$s" \
              --exclude-dir=node_modules --exclude-dir=.next \
              --exclude-dir=dist --exclude-dir=build 2>/dev/null || true)"
  else
    scope="$(grep -lIiE "$FEATURE" "$s" 2>/dev/null || true)"
  fi

  if [ -z "$scope" ]; then
    echo "   FAIL -- $s never mentions CRM churn-label suggestions."
    fail=1
    continue
  fi

  if printf '%s\n' "$scope" | xargs grep -lIiE "$CONFIRM" >/dev/null 2>&1; then
    echo "   PASS -- $s states confirm-required."
  else
    echo "   FAIL -- $s describes the feature but never says a human confirms."
    fail=1
  fi
done

echo
if [ "$fail" -ne 0 ]; then
  echo "RESULT: FAIL"
  exit 1
fi
echo "RESULT: PASS"
