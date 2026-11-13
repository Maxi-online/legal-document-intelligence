# Synthetic Document Source Mode

This service contains a synthetic response generator for testing the external document-source contract. It provides fictional case/document entries and query variations without requiring a live Casebook account. Mock-source availability does not imply that the rest of the application runs without its own database, queue or model-provider configuration.

## Scope and response structure

The fixtures cover claimant, defendant, third-party, counterparty and mention-like relationships. Generated entries contain case identifiers, court/date metadata, document URLs, parties, document text, mention context, relationship type and ranking metadata. The larger generator creates variations and deliberate duplicate URLs to exercise filtering and deduplication.

These records are synthetic, not a real legal case dataset or a benchmark for legal conclusions. The generator's seed and reference time can be fixed for deterministic checks. The root `offline_demo.py` uses that deterministic boundary and does not call the live source or model providers.

## Running the reproducible checks

From the repository root, using the minimal-check environment:

```bash
.venv/bin/python offline_demo.py
.venv/bin/python -m unittest discover -s tests/offline -v
```

On Windows use `./.venv/Scripts/python.exe`. Output is recorded in `docs/offline-demo-output.json`. The checks cover response items, empty results and query variations, not the complete processing/export workflow.

## Mock selection and configuration

Review `service.py`, `mock_data.py` and the root settings example for the actual source-selection logic. Live credentials are provided locally through environment-backed configuration. A missing source key or a source error must not be mistaken for a successful live search merely because a synthetic response is returned. Check the service log and response provenance when comparing mock and live runs.

The settings loader may reject a missing required environment reference before source-selection logic is reached. Use the documented offline generator for credential-free checks instead of assuming every full-stack entry point falls back automatically.

## Optional full-stack workflow

With a dedicated local database, cache, queue and explicitly configured providers, Compose defines the gateway, source, processing and export services. Validate the effective configuration before starting it:

```bash
docker compose config --quiet
docker compose up -d
docker compose ps
docker compose logs --tail=100 pravo_api_service
```

Synthetic source documents may still pass through a live model-processing stage if that stage is enabled. Source mocking alone does not make all downstream processing offline or free of provider costs. No full-stack provider call is made by the root synthetic replay.

## Switching to a live source

Supply an authorized source account/key and the configured source endpoint through ignored local settings/environment references. Keep the source adapter's request/response contract separate from tenant account details. Restart the relevant service after configuration changes, then verify provenance, error handling and source access independently of model quality.

For application evaluation, use an approved corpus with document relevance, extraction fields and source-span labels. Measure retrieval and extraction quality, citation correctness, duplicate handling and unsupported answers. A realistic-looking mock response is not evidence of real-source availability or legal accuracy.
