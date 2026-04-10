# Workflow Phases — Question, Research, Structure, Plan, Implement

This is the full reference for the QRSPI workflow. The `workflow_phase_reminder.py` hook injects a brief phase-specific reminder on each prompt; this document is the deep reference when that reminder is not enough.

## 1) Question

**Goal:** Surface design decisions as explicit choices before any research begins.

- Do NOT read code yet — work only from the user's description.
- Identify every decision point that will shape the solution.
- Present numbered options for each design decision:
  - "What approaches exist for X? (1) [option] (2) [option] (3) [option]"
  - "Which trade-off matters for Y? (a) performance (b) simplicity (c) consistency"
- Ask clarifying questions about scope, constraints, and non-goals.
- Record confirmed answers as the research frame.

**Outputs:**
- Explicit design questions with numbered alternatives
- Confirmed scope boundaries (in-scope / out-of-scope)
- Research target list — specific questions code reading must answer

**Gate:** Do not proceed to Research until design questions are answered or scoped out.

## 2) Research

**Goal:** Targeted investigation to answer each question from phase 1. No broad exploration.

- Map each research question to specific files and code paths.
- Read only what is needed.
- For each question, provide an answer with code evidence (file:line references).
- Capture findings in `DISCOVERY.md`:
  - Current state analysis
  - Gaps, constraints, or risks identified
  - Data model and API coverage analysis

**Outputs:**
- `DISCOVERY.md` — each question answered with evidence
- Code path inventory with file references
- Constraint list (what cannot change)

**Gate:** Every question from phase 1 must be answered or explicitly deferred with rationale.

## 3) Structure

**Goal:** Phased breakdown of what gets built in what order. NOT implementation details.

- Decompose the work into phases (P1, P2, P3…).
- For each phase, identify:
  - What capability it delivers
  - What it depends on (dependency graph)
  - What it enables for later phases
- Identify the critical path — which phase unblocks others.
- Surface risks: what could cause a phase to fail or expand in scope.

**Outputs:**
- Phase breakdown with dependency graph
- Critical path identified
- Risk register per phase
- Draft structure section in `PLAN.md`

**Gate:** Structure must be reviewed before detailed planning begins.

## 4) Plan

**Goal:** Produce a concrete, granular implementation plan ready for approval.

Each step must be executable in 2–5 minutes by a focused agent. `PLAN.md` must contain:

- **Target repos and file paths** — every file to be touched
- **Structure** — phase breakdown from phase 3
- **Ordered implementation steps** — atomic steps with exact paths
- **Risks and assumptions**
- **Verification steps** — test/lint/build/manual check per step
- **Traceability** — map each discovery finding to a plan step
- **Git strategy** — branch name, commit checkpoints, PR title and body

Each step that introduces new behavior must follow RED-GREEN:

1. Write failing test for the desired behavior.
2. Confirm it fails for the right reason (missing behavior, not syntax error).
3. Write minimal production code to pass.
4. Confirm GREEN — full suite passes.

Config, docs, generated code, and infrastructure are exempt.

### Plan Quality Principles

- **Be extremely accurate** — verify every claim by reading actual code. No guessing.
- **Proactively recommend improvements** — suggest optimizations the user did not request.
- **Call out misconceptions** — correct incorrect assumptions explicitly.
- **Tell the user when they are wrong** — flawed approaches must be challenged, not accommodated.

### Approval Gate

- Present the plan clearly.
- **Wait for explicit user approval** before implementing.
- Iterate on feedback; re-confirm after significant changes.

## 5) Implement

**Goal:** Execute the plan with minimal, traceable diffs.

- Do NOT modify code until the plan is approved.
- Execute one step at a time; confirm GREEN before moving on.
- Keep diffs minimal and traceable to plan steps.
- Update `SESSION.md` as work progresses.

RED-GREEN-REFACTOR per behavioral step:

1. **RED** — Write the failing test. Run it. Confirm the failure matches the missing behavior.
2. **GREEN** — Write the minimal code to pass. Run the full suite.
3. **REFACTOR** — Clean up without adding behavior. Confirm the suite stays green.

### Phase-Boundary After-Action

At the end of each phase, pause:

1. What succeeded as planned?
2. What deviated and why?
3. What carries forward into the next phase?

Record answers in `SESSION.md` before continuing.

### Post-Implementation

Before committing:

- Run the full test suite as a final confirmation.
- Verify each repository independently (tests/build/lint).
- Consider running `/code-review` to validate changes against requirements.

## Common Pitfalls

**NEVER:**
- Skip phase 1 — jumping to code reading misses design decisions.
- Research broadly without a question list.
- Write implementation steps before structure is agreed.
- Start implementing without an approved plan.
- Stay silent on flawed approaches.
- Make changes on `main`/`master` without explicit consent.
- Write production code before a failing test exists for a behavioral step.

**ALWAYS:**
- Surface design decisions before reading code.
- Answer each phase-1 question with code evidence.
- Define structure before detailing steps.
- Verify every claim by reading actual code.
- Give every step an exact file path and a verification action.
- Call out misconceptions directly.
- Wait for explicit approval before implementing.
- Apply RED-GREEN-REFACTOR to behavioral steps.
- Run after-action reviews at phase boundaries.

Do not push to main without approval.
