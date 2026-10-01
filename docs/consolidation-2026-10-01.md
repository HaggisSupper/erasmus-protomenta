# Guarded mission consolidation

The guarded-repository-mission branch is integrated with current main. Published main migrations 17 (knowledge policy) and 18 (source registry) remain unchanged. Mission tables are migration 19, with an upgrade adapter and regression test for legacy branch databases. Both immutable-contract hashing APIs remain available. The current bounded advisory worker remains authoritative and does not grant execution authority merely by returning a result.

Validation: 455 tests passed, one optional test skipped; guarded mission fixture passed declared and worker modes, local bare-remote branch evidence and offline rollback checks. New modules pass Ruff, and the wheel includes the mission schema.
