---
name: code-review
description: Review PR feedback (e.g. Copilot), apply sensible fixes, run tests, and update the PR with clear follow-ups.
compatibility: opencode
metadata:
  workflow: github
  focus: pr-review
---

# Code Review Skill

## When to use

Use this skill when the user asks for a PR review pass or to address automated review feedback, for example:
- "check the code review"
- "review the PR"
- "check copilot feedback"
- "another round of code review"

## What I do

This skill describes a repeatable workflow for processing PR review feedback (especially GitHub Copilot PR review comments):

1) Gather PR context (diff, checks, comments)
2) Triage review feedback (fix vs skip with justification)
3) Apply changes with minimal scope
4) Run tests
5) Commit using clean messages (no AI branding)
6) Push to the PR branch
7) Comment on the PR with what changed + test results

## Workflow

### 1) Fetch PR feedback

Commands:

```bash
gh pr view <PR_NUMBER> --comments
gh api repos/OWNER/REPO/pulls/<PR_NUMBER>/comments
gh pr checks <PR_NUMBER>
```

If needed:

```bash
gh pr diff <PR_NUMBER>
```

### 2) Fix issues (when it makes sense)

For each review comment:
- Understand the intent (style/readability/safety/correctness/tests/docs)
- Prefer the smallest change that resolves the concern
- Skip suggestions that would break behavior, conflict with repo conventions, or add complexity without benefit

### 3) Tests

- Run the repo's test suite (or the relevant subset)
- If CI is failing, reproduce and fix locally when possible

### 4) Commit rules

Critical:
- Do not include "Claude", "AI", "Copilot", or assistant branding in commit messages
- Prefer one commit per feedback round

Example commit message:

```
Address review feedback for <topic>

- Fix <issue 1>
- Add <test/doc update>
```

### 5) Push and document the changes

```bash
git push
```

Add a PR comment describing:
- Which review comments were addressed
- Any suggestions intentionally skipped and why
- Test command(s) and results

## Optional: re-request review

If the workflow needs to trigger a fresh automated review, remove and re-add the reviewer:

```bash
gh pr edit <PR_NUMBER> --add-reviewer "copilot-pull-request-reviewer[bot]"
```

If removal is required:

```bash
gh api -X DELETE repos/OWNER/REPO/pulls/<PR_NUMBER>/requested_reviewers --input - <<'EOF'
{
  "reviewers": ["copilot-pull-request-reviewer"]
}
EOF
```

## Success criteria

- All actionable review comments are addressed (or explicitly skipped with reasoning)
- Tests pass locally and checks are green (or known failures are explained)
- PR has a clear update comment with what changed and how it was verified
