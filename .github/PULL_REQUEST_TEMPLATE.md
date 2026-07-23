## What this changes

<!-- The behaviour change, in a sentence or two. Link the issue if there is one. -->

## Why

<!-- The problem it solves. -->

## How it was verified

<!-- Tests you added, and anything you exercised by hand. -->

```
# paste the relevant test output
```

## Checklist

- [ ] Tests ship with the change, and the full suite passes (`pytest -q`)
- [ ] The CLI and the dashboard stay at parity, if this adds a capability
- [ ] No safety boundary is weakened — or, if one changes, it's called out below
- [ ] Any new self-modification stays gated, ledger-signed, and reversible
- [ ] Docs updated if behaviour or configuration changed

## Safety boundaries

<!-- Delete if not applicable. Otherwise: which boundary, what changed, and why it's safe. -->
