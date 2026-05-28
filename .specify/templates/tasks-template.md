# Tasks: [Feature Name]

Spec: `../spec.md`
Plan: `../plan.md`
Status: Pending | In Progress | Done
Updated: YYYY-MM-DD

## Conventions

- Tasks are executable units, scoped to a single PR ideally.
- `[P]` marks tasks that can be done in parallel with the previous task.
- Each task names exact files to touch and what to assert.
- Tests come BEFORE implementation. Failing test then make it pass.

## Tasks

### T-01 [P] Write failing tests for AC-1

File: `tests/test_NNN_feature.py`

Add tests asserting [acceptance criterion 1]. They must fail before T-02.

### T-02 Implement AC-1

Files: `orchestrator/lib/X.py`, `orchestrator/app/routers/Y.py`

Make T-01 tests pass. No other behavior changes.

### T-03 [P] Write failing tests for AC-2

…

## Done when

- [ ] All AC-N tests pass
- [ ] No constitution rule violations introduced
- [ ] Audit log entries verified by manual inspection
- [ ] PRD/ROADMAP updated if scope changed
- [ ] Diagram updated if architecture changed
