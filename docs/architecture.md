# Architecture

The v0.1 system uses a FastAPI service, SQLite, a Next.js workbench, deterministic financial tools, BM25 evidence retrieval and a bounded workflow. LangGraph and model providers are adapters added after the deterministic path is tested.

Data flow: official-source metadata and local documents enter the ingestion boundary; parsed pages and metrics enter the relational store; tools return typed values and evidence IDs; the workflow records every node and tool call; the frontend displays citations and review state.

Synthetic fixtures and real corpus records are separated by `DATA_MODE`.
