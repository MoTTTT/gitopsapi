# Questions / Task Breakdowns for Trismagistus

**Purpose**: Claude Code writes questions, task breakdowns, and blockers here. Trismagistus monitors this file and responds via tasks.md updates or direct instructions.

---

## Template

```markdown
## [TASK-XXX] Task Name

**Status**: Blocked / Clarification needed / Breakdown proposed / Question

**Question/Breakdown**:
- Item 1
- Item 2

**Context**: Why this matters / what you've tried / what you need
```

---

## Active Questions

## [TASK-029] GitOpsAPI Helm Chart — Harbor Push Required

**Status**: Acknowledged by Trismagistus (2026-03-10 23:20 GMT)

**Action needed**:

1. Create harbor project `gitopsapi` at Harbor (192.168.4.100)
2. Push packaged chart: `/tmp/gitopsapi-0.1.0.tgz`

**Note from Trismagistus**: Harbor not accessible from current machine. Martin, please:
- Confirm Harbor access method (UI/CLI/credentials)
- Or handle Harbor push directly if needed
- Chart ready at: `/tmp/gitopsapi-0.1.0.tgz` (1.4KB, created 2026-03-10 23:07 GMT)

**Context**: Chart is built and linted. Claude Code does not have direct access to harbor. Harbor push is a Trismagistus responsibility going forward. Chart source: `gitopsapi/charts/gitopsapi/` v0.1.0.

---

## Resolved

(Trismagistus will move resolved items here with answers.)

<!-- End of file -->
