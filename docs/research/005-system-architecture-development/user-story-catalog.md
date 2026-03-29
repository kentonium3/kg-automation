# User Story Catalog: Felix System Architecture

**Date**: 2026-03-29
**WP**: WP05 — User Story Catalog (Deliverable 1)
**Status**: Complete

**Format**: As [persona], I want [capability], so that [outcome].
**Personas**: Kent (primary), Felix (the system acting on Kent's behalf)

---

## Capability Area A: Core Hub — System Infrastructure

### Core Stories

**A-01** As Kent, I want to add a new integration to the system by describing what I want, so that Felix can research, propose, implement, and validate it without me writing code.

**A-02** As Kent, I want to know the current capabilities and configuration of the system at any time, so that I can make informed decisions about what to build next.

**A-03** As Felix, I want to know my own configuration and what I am able to do, so that I can accurately report my capabilities and limitations to Kent.

**A-04** As Felix, I want all agent actions logged centrally with team, action type, and autonomy gate level, so that Kent can audit what the system did and when.

**A-05** As Kent, I want to advance an agent from Human In The Middle to Human Monitored after it demonstrates reliable performance, so that I spend less time approving routine operations.

**A-06** As Felix, I want to stop and alert Kent when asked to do something outside my defined scope or that I don't know how to do, so that I never fail silently or act beyond my boundaries.

**A-07** As Kent, I want system health checks running on a schedule (service status, backup verification, security baseline), so that I am alerted to problems before they become failures.

**A-08** As Kent, I want new agents onboarded through a defined process (propose, configure, test, deploy, monitor), so that the system grows safely and predictably.

**A-09** As Felix, I want to route inbound messages to the correct team agent based on intent classification, so that each message is handled by the most appropriate agent.

**A-10** As Kent, I want gate transitions logged and auditable, so that I can track how agent autonomy has evolved over time.

### Enhancement Stories

**A-11** As Kent, I want the system to self-diagnose common issues (service down, credential expired, sync stalled) and propose remediation, so that routine maintenance doesn't require my investigation.

**A-12** As Felix, I want to coordinate multi-team requests (e.g., "prepare for tomorrow's prospect meeting" touches calendar, CRM, and content), so that Kent can issue high-level directives without micro-managing.

---

## Capability Area B: SuperAdmin — Executive Digital Assistant

### Core Stories

**B-01** As Kent, I want to dictate a voice note and have it automatically classified, routed, and actioned, so that I can capture thoughts without being at a computer.

**B-02** As Kent, I want a daily briefing delivered to my WhatsApp each morning, so that I start the day with clear priorities.

**B-03** As Kent, I want overdue commitments escalated to me persistently until I resolve them, so that important work doesn't quietly expire.

**B-04** As Kent, I want to schedule a meeting by describing it in natural language, so that my calendar is updated without manual entry.

**B-05** As Kent, I want my email triaged and summarized, so that I can process communications efficiently.

**B-06** As Kent, I want my to-do list and calendar coordinated and updated, so that priorities are given time on the calendar for work to be done.

**B-07** As Kent, I want interactive alerting and negotiation of tasks, conflicting priorities, and oversubscribed commitments, so that the most important decisions and tasks get done.

**B-08** As Kent, I want to be reminded of repeating tasks and appointments on my phone via WhatsApp (meditation, exercise, physical therapy, meetings, calls), and I want to mark them as complete, rescheduled, or "will not do."

**B-09** As Kent, I want to track and get reports on my track record of getting things done when I say they will be done, so that I can improve my reliability.

**B-10** As Kent, I want goal context (constitution docs) informing every priority decision, so that daily actions align with declared life and business priorities.

**B-11** As Kent, I want email drafts prepared for my review before sending, so that I maintain quality and voice while saving time on composition.

**B-12** As Kent, I want a weekly review that surfaces deferred tasks, checks constitution freshness, and highlights upcoming commitments, so that nothing important quietly expires.

### Enhancement Stories

**B-13** As Kent, I want calendar conflict detection before scheduling, so that I never double-book or overcommit time.

**B-14** As Kent, I want task-to-calendar linking (tasks with calendar events store the event ID), so that time blocks and tasks stay synchronized.

**B-15** As Kent, I want "process my inbox now" via WhatsApp to trigger immediate Obsidian inbox processing, so that I can get captured thoughts actioned without waiting for the hourly poll.

**B-16** As Kent, I want unknown requests handled gracefully (Felix declares its limits and offers to learn), so that capability boundaries are transparent.

### Cross-Team Stories

**B-17** As Kent, I want SuperAdmin to request content from Content Creation when materials are needed (e.g., "prepare a one-pager for tomorrow's meeting"), so that I don't have to manage the handoff myself.

**B-18** As Kent, I want SuperAdmin to check my business pipeline status from BizOps when preparing briefings, so that my morning briefing includes business context.

---

## Capability Area C: Development — Application & System Development

### Core Stories

**C-01** As Kent, I want to describe a new feature for the Intentional website and have it researched, designed, and implemented, so that the site evolves without me managing every detail.

**C-02** As Kent, I want to build the Intentional Index tool with AI assistance, so that I can offer it to prospects without needing to code it entirely myself.

**C-03** As Kent, I want development workflows orchestrated through Felix (spec-kitty specify → plan → tasks → implement → review → merge), so that the development process is consistent and tracked.

**C-04** As Kent, I want the metal casework visual designer tool developed with AI assistance, so that the product concept can be validated with real users.

### Enhancement Stories

**C-05** As Kent, I want development status updates included in my daily briefing (PRs open, CI status, blocked tasks), so that I have situational awareness of development progress.

**C-06** As Felix, I want to trigger Claude Code sessions for implementation work and receive completion notifications, so that development can proceed asynchronously.

### Cross-Team Stories

**C-07** As Kent, I want Development to request content from Content Creation when documentation or marketing pages are needed for a project, so that content is part of the development workflow.

---

## Capability Area D: Content Creation

### Core Stories

**D-01** As Kent, I want to describe a blog post idea and have a draft produced, so that I can focus on review and refinement rather than generation.

**D-02** As Kent, I want a presentation created from a brief, so that I can deliver professional materials without spending hours in PowerPoint.

**D-03** As Kent, I want different versions of a topic generated that are appropriate as a blog post, LinkedIn teaser post, white paper, Instagram post, or email, so that one idea produces content for all channels.

**D-04** As Kent, I want any videos I generate made available to post on LinkedIn or Instagram, so that video content supports marketing campaigns.

**D-05** As Kent, I want to describe conceptual diagrams and graphics and have a few versions generated so I can iterate with AI assistance until satisfied, so that visual content doesn't require design skills.

**D-06** As Kent, I want content generated with the correct brand identity (personal, Intentional, or metal casework) based on context, so that tone, visual identity, and messaging are consistent per brand.

**D-07** As Kent, I want white papers and professional PDFs generated from briefs, so that I can produce polished documents for prospects and clients.

### Enhancement Stories

**D-08** As Kent, I want a content review and approval workflow (Felix drafts, Kent approves, then published), so that nothing is published without my review.

**D-09** As Kent, I want content assets organized and retrievable (Canva for visuals, second brain for text, office2 for PDFs), so that previously created content can be reused or referenced.

### Cross-Team Stories

**D-10** As BizOps, I want to request content from Content Creation with specifications (topic, format, audience, brand), so that marketing materials are produced without manual coordination.

**D-11** As SuperAdmin, I want to request one-pagers or briefing materials from Content Creation for upcoming meetings, so that Kent has professional materials ready.

---

## Capability Area E: BizOps — Business Operations

### Core Stories

**E-01** As Kent, I want new leads from my website automatically entered into my CRM with context, so that no prospect falls through the cracks.

**E-02** As Kent, I want to describe a marketing campaign and have the plan generated along with materials for my review and approval before it is executed, so that campaigns are professional and controlled.

**E-03** As Kent, I want to describe a series of blog posts and have the system schedule versions of them to appear on my personal website, LinkedIn, Instagram, and in email to target audiences, so that content distribution is automated.

**E-04** As Kent, I want a weekly business report delivered to my WhatsApp, so that I have situational awareness without pulling reports manually.

**E-05** As Kent, I want deal pipeline status tracked and visible, so that I know where every prospect stands.

**E-06** As Kent, I want prospect communications managed (follow-ups, check-ins, nurture sequences), so that relationships are maintained even when I'm busy.

### Enhancement Stories

**E-07** As Kent, I want invoices generated and sent from a description of the work completed, so that billing doesn't require manual entry.

**E-08** As Kent, I want customer support inquiries routed and tracked, so that client issues are resolved promptly.

**E-09** As Kent, I want order management for metal casework (when the business is active), so that product orders are tracked from placement to fulfillment.

**E-10** As Kent, I want campaign performance tracked and reported (open rates, click rates, lead conversion), so that I can iterate on marketing effectiveness.

### Cross-Team Stories

**E-11** As BizOps, I want to request content for campaigns from Content Creation with audience and channel specifications, so that marketing has professional materials.

**E-12** As BizOps, I want to request development of business tools (e.g., Intentional Index) from Development, so that sales tools are built as part of the business workflow.

---

## Cross-Team Interaction Matrix

| Requesting Team | Providing Team | Interaction Type | Example |
|----------------|---------------|-----------------|---------|
| SuperAdmin (B) | Content Creation (D) | Request materials | "Prepare a one-pager for tomorrow's meeting" |
| SuperAdmin (B) | BizOps (E) | Query pipeline | "What's the status of the Acme deal?" |
| BizOps (E) | Content Creation (D) | Request campaign content | "Create LinkedIn posts for the new service announcement" |
| BizOps (E) | Development (C) | Request tool development | "Build the Intentional Index assessment tool" |
| Development (C) | Content Creation (D) | Request documentation | "Write the user guide for the new feature" |
| Core Hub (A) | All teams | Route messages | Classify inbound → delegate to correct team |
| All teams | Core Hub (A) | Report status | Action logs, health checks, gate transitions |

## Summary

| Area | Core Stories | Enhancement Stories | Cross-Team Stories | Total |
|------|-------------|--------------------|--------------------|-------|
| Core Hub (A) | 10 | 2 | — | 12 |
| SuperAdmin (B) | 12 | 4 | 2 | 18 |
| Development (C) | 4 | 2 | 1 | 7 |
| Content Creation (D) | 7 | 2 | 2 | 11 |
| BizOps (E) | 6 | 4 | 2 | 12 |
| **Total** | **39** | **14** | **7** | **60** |

All seed stories from the research brief (including Kent's additions) are
incorporated. Stories expanded using findings from WP01 (audit), WP02
(OpenClaw capabilities), WP03 (integration needs), and WP04 (data/privacy/
identity).
