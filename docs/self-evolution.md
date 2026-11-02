# The self-evolving harness

Most agent systems improve when *you* tune them. Glaux tunes **itself** — and the
design guarantees it cannot silently get worse.

Every self-modification obeys three rules:

1. **Gated** — applied only when the evidence supports it.
2. **Signed** — written to the ledger as `EVOLVE_HARNESS`.
3. **Reversible** — one command undoes it.

```bash
glaux evolution        # what it has learned
glaux evolve           # run one pass (every operator, each independently gated)
glaux evolution revert # roll back the most recent change
```

## What it learns from

Every finished task becomes an **episode**: the directive, the tier that ran it, whether
it succeeded, and how many specialists worked it. Each dispatched specialist also records
its own outcome (iterations used, whether it hit its cap, the failure signature).

## The operators

### 1. Tier routing
Glaux routes each directive to `fast`, `medium`, or `full`. From an outcome it infers
the tier that *should* have run — a fast/medium run that failed was under-powered; a full
run one specialist finished cleanly was over-powered. Mis-tiered directives become
learned exemplars for the router.

**Gate:** replay every recorded episode through the router with the candidate exemplars.
Commit only on a net accuracy gain. (Measured 0% → 100% on a mis-tiered set.)

### 2. Iteration budgets
A specialist that keeps hitting its iteration cap *and* failing gets more room; one that
always finishes early gets less.

**Gate:** at least 4 dispatches, plus the cap-hit and failure rates.

### 3. Prompt lessons
When a role fails the same way repeatedly, the harness appends a lesson to its system
prompt — "you have repeatedly failed with X; handle it explicitly."

**Gate:** the same failure signature at least 3 times.

### 4. Playbook distillation
A successful multi-specialist run is distilled into a reusable playbook (the directive
plus the ordered roles that solved it), so similar work starts from a known-good plan.

**Gate:** success, at least 2 specialists, and no duplicate.

### 5. Skill promotion
A synthesized skill that has proven itself is **pinned** as a permanent, always-offered
tool — so the swarm reuses it instead of re-synthesizing it.

**Gate:** promoted status, ≥5 uses, ≥80% success rate. Reverse with
`glaux evolution unpin <id>`.

### 6. Specialist retirement
A specialist the router keeps dispatching to that almost always fails is retired from the
roster. Never retires an unused or new specialist, and never drops the roster below a
floor. Reverse with `glaux evolution unretire <role>`.

## Auto-evolve

Off by default. Turn it on to run every operator automatically:

```bash
glaux evolution auto on --every 20   # after every 20 recorded episodes
```

Each change is still gated and signed, so an automatic pass carries the same guarantees
as a manual one.

## Auditing it

Every accepted mutation appears in the ledger and in `glaux evolution`, with the metric
before and after. Because the ledger is hash-chained and signed, the record of how your
agent changed itself is as tamper-evident as the work it did.
