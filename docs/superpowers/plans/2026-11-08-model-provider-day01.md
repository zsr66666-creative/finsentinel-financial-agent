# Model Provider Day 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a synchronous, typed model provider boundary and a deterministic FakeModel implementation.

**Architecture:** A small protocol defines the provider contract. A response dataclass carries model output and runtime metadata. FakeModel implements the contract without network access so later providers can be substituted without changing workflow consumers.

**Tech Stack:** Python 3.12, dataclasses, typing.Protocol, pytest.

## Global Constraints

- FakeModel is the default and performs no network access.
- Tool definitions are data passed to `generate`; providers do not execute tools.
- Day 1 does not add API keys, external dependencies, or real model calls.

### Task 1: Provider contract

**Files:**
- Create: `backend/app/model_provider.py`
- Test: `backend/tests/test_model_provider.py`

**Interfaces:**
- Produce `ModelResponse` and `ModelProvider` for later providers.

- [ ] Add tests for response fields and protocol-compatible provider.
- [ ] Run `python -m pytest tests/test_model_provider.py -q` and observe failure before implementation.
- [ ] Implement the dataclass and protocol.
- [ ] Run the focused test and expect it to pass.

### Task 2: FakeModel implementation

**Files:**
- Create: `backend/app/providers/__init__.py`
- Create: `backend/app/providers/fake.py`
- Modify: `backend/tests/test_model_provider.py`

**Interfaces:**
- Produce `FakeModelProvider(provider='fake', model='deterministic-demo-v1')`.
- `generate(prompt: str, tools: list[dict] | None = None) -> ModelResponse`.

- [ ] Test deterministic text, metadata, zero token usage, and tool definition pass-through.
- [ ] Implement a deterministic response without network access or tool execution.
- [ ] Run the focused tests and expect all to pass.

### Task 3: Regression and documentation

**Files:**
- Modify: `docs/week17-day01-model-provider.md`

- [ ] Run `python -m pytest -q` from `backend`.
- [ ] Record test count and the fact that no external model call occurs.
- [ ] Commit the provider, tests, and documentation together.
