---
title: Felix — kg-automation
doc_type: readme
status: approved
owners:
  - '@kentonium3'
last_validated: '2026-04-08'
last_updated: '2026-04-08'
---

<p align="center">
  <img src="docs/assets/felixhead.gif" width="180" alt="Felix the Cat"/>
</p>

<h1 align="center">Felix</h1>
<p align="center"><em>A personal AI operating system — built on kg-automation</em></p>

<p align="center">
  <img src="https://img.shields.io/badge/status-active-brightgreen" alt="active"/>
  <img src="https://img.shields.io/badge/spec--kitty-3.x-orange" alt="spec-kitty"/>
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Ubuntu-blue" alt="platform"/>
</p>

---

Named after Felix the Cat and his magical bag of tricks — the idea that
the right tool appears at exactly the right moment. Felix is a growing
network of specialist agents handling executive assistant work, task
intelligence, habit tracking, escalation, and business operations.
Distant cousin of [spec-kitty](https://github.com/Priivacy-ai/spec-kitty).
Built with [OpenClaw](https://openclaw.io) as the agent runtime.

## What Felix does today

| Capability | Status |
|---|---|
| Inbox processing and task capture | Live |
| Task intelligence and enrichment | Live |
| Daily habit check-in via WhatsApp | Live |
| Observation layer — agent activity digest | Live |
| Escalation engine — proactive task insistence | Live |
| Google Calendar skill (gog) | In progress |
| Voice interaction | Planned |
| Email inbox management | Planned |

## Architecture

Felix runs on a MacBook Pro (primary) and a Ubuntu 24.04 office server
(office2), connected via Tailscale mesh. Agents operate at three autonomy
levels: Assisted (human-in-the-loop), Observed (autonomous with distilled
reporting), and Autonomous (full autonomy).
