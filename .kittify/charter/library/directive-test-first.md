# Directive: Test-First Development

- ID: `TEST_FIRST`
- Source: `/Users/kentgale/.local/pipx/venvs/spec-kitty-cli/lib/python3.13/site-packages/doctrine/directives/test-first.directive.yaml`
- Summary: Require test-first behavior across acceptance and implementation layers, selecting tactics based on scope and risk.

## Raw Definition

```yaml
schema_version: '1.0'
id: TEST_FIRST
title: Test-First Development
intent: Require test-first behavior across acceptance and implementation layers,
  selecting tactics based on scope and risk.
tactic_refs:
- acceptance-test-first
- tdd-red-green-refactor
- zombies-tdd
enforcement: required
```
