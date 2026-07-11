# Authority Boundaries

A capability may only perform actions explicitly declared in its contract.

Authority classes:

- `observe`: read state without mutation.
- `propose`: create a candidate change.
- `quarantine`: isolate suspicious content or state.
- `mitigate`: apply reversible bounded correction.
- `promote`: move reviewed state into canonical use.
- `execute`: perform an external side effect.

Only the Protomentat may authorize irreversible or materially consequential execution unless a specific standing delegation exists.
