# Sys Eden — Local Model Integration Audit

> **Document role:** Milestone 4 implementation audit  
> **Status:** Completed on 2026-09-22  
> **Scope:** Replaceable model contracts, local Ollama adapter, routing, context,
> structured diagnostics, and CLI integration

## Implemented boundary

Core depends on the asynchronous `ModelProvider` protocol rather than Ollama.
The protocol exposes health, installed-model discovery, and generation through
typed Pydantic request/response objects. A deterministic fake provider remains
available for unit tests and offline development.

The initial `OllamaProvider` uses the loopback API only. It disables environment
proxy inheritance and redirects, applies bounded health and generation timeouts,
and returns stable model error codes. The provider checks installed metadata
before inference and refuses cloud-managed model entries. It does not pull models
implicitly.

## Context and output controls

The context builder includes only the supplied concern, targeted snapshot, and
explicitly selected historical capsules. Sections are bounded and labeled as:

- `USER_STATEMENT`
- `LOCAL_SYSTEM_EVIDENCE`
- `HISTORICAL_REPORT`
- `PUBLIC_RESEARCH`

All section content is described to the model as untrusted data rather than an
instruction source. The current diagnostic flow supplies no public research and
does not claim that an action or verification occurred.

The model must return a JSON object matching the Pydantic-generated
`DiagnosticAssessment` schema. Eden validates observations, hypotheses,
unknowns, recommended next checks, five-dimensional confidence, and the
conversational explanation before showing the result.

## Routing and runtime

The basic router filters for:

- local installation,
- required text and structured-output capabilities,
- estimated context fit,
- optional configured model preference,
- and speed/balanced/strong preference.

The development machine uses Ollama 0.34.3 with `qwen3.5:9b`, a roughly 6.6 GB
Q4 model, stored under `C:\AI\models`. This fits the configured 12 GB model
budget. The model is a development default, not a permanent architecture choice.

## CLI surface

```text
eden model health
eden model list
eden chat [CONCERN] [--component COMPONENT]
eden chat [CONCERN] --snapshot FILE [--json]
```

`eden chat` performs read-only evidence collection and inference. It cannot
mutate the system. Planning, approval, execution, and durable task recovery are
later roadmap milestones.

## Validation

Automated coverage includes provider availability, missing models, invalid
structured responses, loopback configuration, cloud-model blocking, metadata,
routing, context bounds and trust labels, diagnostic schema validation, and CLI
surfaces. The final validation result is recorded in the roadmap checkpoint.

## Provider references

- [Ollama list-models API](https://docs.ollama.com/api/tags)
- [Ollama generate API](https://docs.ollama.com/api/generate)
- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
