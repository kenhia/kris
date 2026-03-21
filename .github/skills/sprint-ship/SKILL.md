---
name: sprint-ship
description: "Ship a completed sprint: run pre-commit checks, update docs, commit
  remaining changes, push branch, create and merge PR, then reset local to main. Use
  when all sprint work is done and the user wants to land the branch."
---

# Sprint Ship Skill

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Overview

This skill ships a completed sprint branch to GitHub. It walks through
pre-commit validation, documentation freshness, final commit, push, PR
creation, squash-merge, and local cleanup — in that order, gated at each
stage.

## Prerequisites

- All sprint tasks in `specs/<branch>/tasks.md` are marked complete.
- The working tree is on the sprint's feature branch (e.g. `001-mvp-core`).

## Context Discovery

Before starting, gather context needed throughout the workflow:

1. **Identify the feature branch**: run `git branch --show-current`.
2. **Identify the GitHub remote**: run `git remote -v` — extract `owner` and `repo` from the origin URL (e.g. `git@github.com:kenhia/kris.git` → owner=`kenhia`, repo=`kris`).
3. **Read `specs/<branch>/spec.md`** — extract the feature title from the `# Feature Specification: <title>` heading. This becomes the PR title prefix.
4. **Read `specs/<branch>/tasks.md`** — confirm all tasks and commit-tasks are marked complete (`[x]`). If any are not, **stop and inform the user** before proceeding.

---

## Phase 1: Pre-Commit Checks

### Step 1.1 — Run `just check`

Run the full validation suite:

```bash
just check
```

This executes: format check → lint → tests (both Rust and Python).

- **If it passes**: proceed to Phase 2.
- **If it fails**: stop and fix the failures before continuing. Do not skip failures or use `--no-verify` workarounds.

---

## Phase 2: Documentation Freshness

Review documentation to ensure it reflects what was actually built in this sprint.

### Step 2.1 — Identify docs to review

The core documentation files are:

| File | Purpose |
|------|---------|
| `docs/architecture.md` | System design, component diagram, tech stack |
| `docs/usage.md` | CLI commands, examples, workflows |
| `docs/setup.md` | Installation, configuration, prerequisites |
| `docs/specification.md` | Functional spec / feature overview |

Additionally, check for **addendum files** (`docs/addendum-*.md`). These are
interim documents capturing changes that haven't been folded into the base
docs yet. For each addendum:

1. Read it — understand what it documents.
2. Integrate its content into the appropriate base doc(s).
3. Delete the addendum file once its content is incorporated.

### Step 2.2 — Review each base doc

For each base doc:

1. Read the file.
2. Read `specs/<branch>/spec.md` and `specs/<branch>/plan.md` to understand what was built.
3. Check for obvious staleness:
   - New commands or flags not documented in `usage.md`.
   - Architecture changes not reflected in `architecture.md`.
   - New setup steps or dependencies not in `setup.md`.
   - Features described in the spec that aren't in `specification.md`.
4. Update any stale sections. Keep the existing style and structure.
5. If uncertain whether something needs updating, **ask the user** rather
   than guessing.

### Step 2.3 — Confirm with user

After making updates, briefly summarize what was changed (or confirm that
docs are already current). Wait for user acknowledgement before proceeding.

---

## Phase 3: Final Commit

### Step 3.1 — Stage and commit remaining changes

Check for uncommitted changes:

```bash
git status --short
```

If there are uncommitted changes:

1. Stage everything: `git add -A`
2. Commit with the sprint prefix convention:

   ```
   docs(<branch-number>): update docs for sprint ship
   ```

   For example: `docs(001): update docs for sprint ship`

   If the changes include non-doc work (e.g. late fixes found during
   `just check`), adjust the prefix and message accordingly — e.g.
   `fix(001): resolve lint warning in embed.py` or
   `chore(001): pre-ship cleanup`.

3. If nothing to commit, proceed to Phase 4.

### Step 3.2 — Final verification

Run `just check` one more time after any commit to confirm nothing broke.
If this was already the state from Step 1.1 and no new changes were made,
this step can be skipped.

---

## Phase 4: Push and Create PR

### Step 4.1 — Push branch to GitHub

```bash
git push -u origin <branch>
```

If the branch has never been pushed before, this sets up tracking. If it
has been pushed before, this pushes new commits.

### Step 4.2 — Create Pull Request

Use the `mcp_github_create_pull_request` tool:

- **owner / repo**: from context discovery.
- **title**: follow the commit prefix pattern —
  `feat(<branch-number>): <Feature Title>`.
  Example: `feat(001): MVP Core — Local Scan, Index, Embed, Query`
- **head**: the feature branch name (e.g. `001-mvp-core`).
- **base**: `main`.
- **body**: a brief description covering:
  - One-sentence summary of what the sprint delivered.
  - Link to the spec: `[Specification](specs/<branch>/spec.md)`
  - Link to the tasks: `[Task Breakdown](specs/<branch>/tasks.md)`
  - Optionally, a short bullet list of highlights if the sprint covered
    multiple phases or themes.
- **draft**: `false`.

### Step 4.3 — Report PR to user

Tell the user the PR number and URL. Wait for confirmation to proceed with
the merge.

---

## Phase 5: Merge PR

> **CI Note**: This repository does not currently have a CI workflow. When
> a CI pipeline is added, this phase must be updated to wait for CI checks
> to pass before merging. For now, the `just check` run in Phase 1/3
> serves as the local validation gate.

### Step 5.1 — Squash and merge

Use the `mcp_github_merge_pull_request` tool:

- **owner / repo**: from context discovery.
- **pullNumber**: the PR number from Step 4.3.
- **merge_method**: `squash`.
- **commit_title**: same as the PR title —
  `feat(<branch-number>): <Feature Title>`.
- **commit_message**: the PR body (or a trimmed version of it).

### Step 5.2 — Confirm merge

Verify the merge succeeded. Report the result to the user.

---

## Phase 6: Local Cleanup

### Step 6.1 — Switch to main and pull

```bash
git checkout main
git pull origin main
```

### Step 6.2 — Delete local feature branch

```bash
git branch -d <branch>
```

The remote branch is intentionally **not** deleted — it serves as a
historical record of the sprint's development timeline on GitHub.

### Step 6.3 — Confirm ready state

Run `git log --oneline -3` to show the user that `main` is up to date
with the squash-merged commit. Confirm the workspace is ready for the
next sprint.

---

## Error Handling

- **`just check` fails**: Fix issues before continuing. Never bypass checks.
- **Push fails**: Check for authentication issues or remote conflicts. Report to user.
- **PR creation fails**: Check if a PR already exists for the branch.
  If so, report and ask user how to proceed.
- **Merge fails**: Check for merge conflicts. Report to user — this
  should not happen for a branch based on main with no concurrent work,
  but handle gracefully.
- **Branch delete fails**: The branch may have unmerged commits (e.g. if
  the squash merge produced a different history). Use `git branch -D` only
  after confirming with the user.

## Important Rules

- **Never force-push.** The branch history should be preserved on GitHub.
- **Never skip `just check`.** It is the quality gate.
- **Always wait for user confirmation** before merging the PR. The user
  may want to review the PR on GitHub first.
- **Squash merge only.** This keeps `main` history clean with one commit
  per sprint.
- **Keep the remote branch.** It provides a timeline record of how the
  project arrived at its current state.
