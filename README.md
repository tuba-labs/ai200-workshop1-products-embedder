# ProductsEmbedder

Python 3.12 / Azure Functions v4. Event Grid-backed Blob trigger; reads immutable product manuals, chunks them, embeds them and commits vectors/ready status atomically in PostgreSQL.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-test.txt
python -m pytest tests -q
python package.py --output dist/function.zip
```

Deploy the ZIP with remote Linux build enabled; do not package a Windows virtual environment. Flex Consumption needs the host/deployment storage identities, VNet integration and Event Grid subscription supplied by the workshop infrastructure. There is no Dockerfile for this hosting path.

`rag_core/` is vendored runtime source, also included in ProductsChat. Keep both copies consistent. Direct requirements and resolved constraints are included; no parent repository is required to package or test this app.

The trigger verifies product/manual IDs and checksum. Ready duplicates skip indexing; failures persist and are retried. Settings/secrets load at cold/startup; restart for changes. Local model tests use deterministic fixtures, not Azure calls.

Provisioning, deployment and end-to-end integration tests: https://github.com/tuba-labs/ai200/tree/main/workshop
