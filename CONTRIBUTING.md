# Contributing to DCAToolBox

Thank you for your interest in improving DCAToolBox! This project aims for the
quality of a bank quant codebase, so a few conventions keep it maintainable.

## Golden rules

1. **Never put strategy-specific logic in the engine.** Strategies are plug-ins;
   the engine, broker, portfolio and metrics must stay generic.
2. **Type everything.** Full type hints and Google-style docstrings on every
   public function, method and class.
3. **Keep it small and DRY.** Functions stay short (≈40 lines max unless
   justified); factor shared logic instead of duplicating it.
4. **No look-ahead bias.** Strategies only ever use the `MarketContext` they are
   given.

## Development setup

```bash
pip install -e ".[dev,web,report]"
```

## Quality gate

Run this before opening a pull request — CI runs the same checks:

```bash
ruff check .            # lint
ruff format --check .   # formatting
pytest --cov=dcatoolbox # tests + coverage (target ≥ 95%)
```

## Adding a strategy

1. Create one self-contained module under `dcatoolbox/strategies/`.
2. Subclass `Strategy` (or `BudgetDeploymentStrategy`) and decorate it with
   `@register_strategy`.
3. Import it from `dcatoolbox/strategies/builtin.py`.
4. Add unit tests covering its signal logic.

No other file should need to change.

## Commit messages

Use clear, imperative messages (e.g. "Add Bollinger Bands strategy"). Group
related changes into focused commits.
