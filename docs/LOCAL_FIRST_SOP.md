# Erasmus Local-First SOP

## Default

Implement features with the Python standard library or installed, permissively licensed open-source packages. Keep source, indexes, tests, credentials, and runtime state local.

## Do not require by default

- Paid APIs or subscriptions.
- API keys for core functionality.
- Hosted microservices.
- Cloud storage or remote telemetry.
- External authentication providers.

## Approved local capabilities

- Tree-sitter grammar packages for code indexing.
- Local LSP servers such as rust-analyzer, Pyright, and TypeScript language server.
- Local adversarial REST test servers.
- Local Acumatica adapter tests with deterministic fakes.
- Local MCP servers over stdio.
- Contract, authority, resolver, provenance, and state-packet enforcement.

## External services

External services such as Context7 may be documented as optional adapters, but must remain disabled unless the operator explicitly enables them and supplies credentials.

## Completion gate

A feature is locally complete when it has a deterministic implementation, negative-path tests, Windows smoke coverage where relevant, and no paid or remote dependency in the default path.
