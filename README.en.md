# k12-qbank

[中文](README.md)

A junior high school mathematics practice and diagnosis system for institutional teachers.  
It is built on a structured, verified question bank, starts from classroom teaching objectives, is grounded in student answer evidence, and treats teacher confirmation as the sole source of formal teaching conclusions.

It is neither a pure OCR tool nor a system that lets large models freely generate exam papers. Its main value is to reduce teachers’ repetitive work in organizing questions, assembling papers, collecting answers, performing initial analysis, and selecting follow-up practice, while preserving teachers’ control over teaching content and student conclusions.

Baseline document: *Junior High School Mathematics Question Bank and Teaching System Requirements and Architecture Design V2.0* (2026-11-10).  
The repository currently contains architecture constraints, domain models, and check scripts. The teaching service is not yet implemented.

## Five Core Problems This System Solves

| Problem | V2.0 Decision |
|---------|---------------|
| How does homework correspond to “what was taught in this lesson”? | Add classroom, class, and teaching objectives; link the assignment directly to the classroom and its objective snapshot |
| When five students do the same set of questions, how is individual focus expressed? | Three-layer mechanism: shared required questions + personal focus markers + post-grading consolidation plans |
| How does AI analysis automatically form the next set of questions? | Automatically generate constrained consolidation-plan drafts by selecting only from the approved question bank; teacher reviews before release |
| How to avoid permanently labeling a student from a single wrong answer? | Introduce learning evidence and revisable mastery states that distinguish insufficient evidence, pending review, and confirmed issues |
| How to see commonalities and differences among five students? | Provide class-level views of knowledge points, error causes, questions, and consolidation effects — not just average scores |

The most important system boundary: **recognition failure, missing evidence, and student error are three distinct states.**

## Complete Business Closed Loop

Classroom and teaching objectives → Shared assignment with personal focus → Paper or online answering → Photo collection and evidence check → Recognition, scoring, and error-cause suggestions → Teacher review and confirmation → Student feedback, correction, and self-explanation → Learning evidence and mastery states → Consolidation plan draft → Teacher review and release → Re-practice and delayed retest → Evidence feedback.

The system also supports analysis of class commonalities and individual differences.

First-version success is defined as completing this real closed loop (including a five-student shared assignment with personal focus and different consolidation-plan drafts), not merely “how many pages were recognized.”

## Architecture

The first version uses a **modular monolith**, PostgreSQL, controlled file storage, a persistent job table, and background workers. The web interface and Android app share the same HTTPS API entry point.

Core modules and responsibilities:
- `classroom`: Record lessons, teaching objectives, example questions, and teacher observations
- `catalog`: Question import, verification, versioned release, and retrieval
- `practice`: Shared assignments, per-student instances, paper snapshots, submissions, and evidence collection
- `analysis`: AI analysis runs, suggestion generation, and structural validation
- `remediation`: Learning evidence, mastery states, consolidation-plan drafts, and effect recording
- `delivery`: Paper PDF and report generation
- `identity`: Users, roles, responsibility relationships, and permission checks

Key principles:
- Original PDFs, page images, question crops, and student answer photos remain fully traceable
- Questions and answer explanations are verified and versioned separately; formal release requires approval
- When the same assignment is given to multiple students, each student receives an independent instance and historical snapshot
- AI produces only suggestions; formal teaching conclusions require teacher confirmation
- Issued assignments, photos, suggestions, and evaluation revisions cannot be overwritten in place
- Permissions, privacy, audit, cost control, and backup/recovery are implemented from the first version

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed layering and invariants.

## Technology Stack and Deployment (Candidates)

| Component | Candidate | Notes |
|-----------|-----------|-------|
| Backend | Python + FastAPI | Modular monolith |
| Database | PostgreSQL | Relational data and transactional constraints |
| File storage | Local directory / object storage | Immutable asset management |
| Web | React or Vue + MathJax | Complex verification and review prioritized on web |
| Android | Flutter or React Native | Photo upload and lightweight confirmation |
| AI | Multimodal / language model adapters | Staged, discardable, and human-fallback capable |
| Deployment | Institution computer + controlled LAN | Pilot phase |

Final choices will be recorded as ADRs after pilot data and institutional confirmation. See [docs/adr/](docs/adr/).

The first version begins with a 1–2 week vertical validation (approved questions → create assignment → upload → suggestions → teacher confirmation) before estimating the full MVP schedule. Microservices are not built early.

## Current Repository Status

The teaching service is not yet implemented.  
`python scripts/status.py` only reports skeleton status. It does not generate papers or start a server.

## Commands

| Name | Command |
|------|---------|
| Show skeleton status | `python scripts/status.py` |
| Document smoke | `python scripts/smoke_docs.py` |
| Full check | `bash scripts/check` or PowerShell script |

Remote checks: [GitHub Actions](https://github.com/wisdom-km/k12-qbank/actions).

## Read First

- [PRD.md](PRD.md) — What to build and what is explicitly out of scope
- [ARCHITECTURE.md](ARCHITECTURE.md) — Layers, invariants, and interfaces
- [docs/exec-plans/active/](docs/exec-plans/active/) — Execution plans
- [docs/adr/](docs/adr/) — Architecture decision records

## License

Upstream notes suggest MIT. This repository currently has no license file.
