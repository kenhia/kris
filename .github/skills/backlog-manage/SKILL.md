---
name: backlog-manage
description: "Manage the project backlog: add new entries, move entries into active
  sprints, archive completed items, and review backlog status. Use when the user wants
  to capture work for later, promote backlog items to a sprint, or get a backlog overview."
---

# Backlog Management Skill

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## File Locations

- **Active backlog**: `specs/backlog.md`
- **Archive**: `specs/backlog-archive.md`
- **Active sprint specs**: `specs/<feature-branch>/` (e.g. `specs/001-mvp-core/`)

## Operations

Determine which operation the user is requesting from their input:

### 1. Add a New Entry

1. **Read `specs/backlog.md`** — find the `## Agent Instructions` section at the top to get the current **Highest Bxxx Entry** number.
2. **Assign the next ID**: increment by 1 (e.g. if highest is B006, the new entry is B007).
3. **Write the entry** at the end of `specs/backlog.md` using this template:

   ```markdown
   ---

   ## Bxxx — <Short descriptive title>

   **Origin**: <Where this was observed or why it matters>

   <Description of the problem, current behavior, and desired behavior.
   Include code references, log output, or error messages as appropriate.>

   **Priority**: <High | Medium | Low> — <brief rationale>
   ```

4. **Update the `Highest Bxxx Entry`** counter in the `## Agent Instructions` section.
5. **Do NOT commit** — backlog additions are uncommitted working changes unless the user explicitly asks for a commit.

### 2. Move Entry to Active Sprint (and Archive)

This is a two-part operation: incorporate the item into the active sprint, then archive it from the backlog.

1. **Read the backlog entry** being moved (e.g. B006).
2. **Add to sprint plan** (`specs/<branch>/plan.md`):
   - Add a new Phase section at the end of the phases list.
   - Summarize the work with components list.
3. **Add to sprint tasks** (`specs/<branch>/tasks.md`):
   - Add a new Phase section with actionable tasks (T-numbered, continuing from the highest existing task number).
   - Include a commit task (CT-numbered).
4. **Remove the entry from `specs/backlog.md`**.
5. **Append the entry to `specs/backlog-archive.md`** with a note about where it was moved:
   - Add `(moved to <branch> Phase N)` to the heading.
   - Add a `**Moved**: <date>` line at the end.
6. **Update the `Highest Bxxx Entry`** counter if needed (it should stay the same — the number is never reused).

### 3. Review / List Backlog

When the user asks to see the backlog, review status, or get a summary:

1. Read `specs/backlog.md` and `specs/backlog-archive.md`.
2. Present a summary table:

   | ID | Title | Priority | Status |
   |----|-------|----------|--------|

   Where Status is `active` (in backlog.md) or `archived → <destination>` (in backlog-archive.md).

### 4. Update an Existing Entry

When the user wants to modify, extend, or reprioritize an existing backlog item:

1. Read the current entry from `specs/backlog.md`.
2. Apply the requested changes.
3. If priority changed, note the change in the entry.

### 5. Remove / Close an Entry

When an item is no longer relevant (not moved to sprint, just dropped):

1. Remove from `specs/backlog.md`.
2. Add to `specs/backlog-archive.md` with `(closed — <reason>)` in the heading and a `**Closed**: <date>` line.
3. Update `Highest Bxxx Entry` counter if needed (numbers are never reused).

## Entry Format Guidelines

- **Title**: Short, descriptive, action-oriented (e.g. "Parallelize Rust scanner", not "Scanner is slow").
- **Origin**: Where the issue was discovered — phase number, user observation, log output, etc.
- **Body**: Describe current behavior, desired behavior, investigation notes, code references, options to explore. Use code blocks for log output or code snippets.
- **Priority**:
  - **High** — blocks user workflows or causes significant pain.
  - **Medium** — improves experience but has workarounds.
  - **Low** — nice-to-have, cosmetic, or speculative.

## Important Rules

- **B-numbers are never reused.** Even if an entry is archived or closed, its number is permanently consumed.
- **Always update the counter** in the `## Agent Instructions` section of `specs/backlog.md` after any operation that assigns a new B-number.
- **Cross-reference sprint tasks** when moving items. The task IDs in the sprint should reference the original B-number for traceability (e.g. in the Phase heading: "Phase 10: GPU Embedding Performance (B006)").
