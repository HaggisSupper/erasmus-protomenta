# Mission Contract

Every mission declares:

- objective;
- success condition;
- current state;
- constraints;
- capabilities allowed;
- authority granted;
- evidence required;
- risk classification;
- stopping condition;
- rollback path;
- immune trigger conditions.

A mission may not silently broaden its own scope or permissions.

The machine-readable version is [`contracts/mission.schema.json`](../contracts/mission.schema.json).
Version 1.0.0 executes one committed step at a time through the capability
runtime and supports these durable states: draft, proposed, authorized,
running, blocked, awaiting_approval, completed, failed, cancelled, and
rolled_back. Planning prose is never an executable transition record.
