# k12-qbank

[中文](README.md)

A math question bank and teaching loop for teachers at one institution. The baseline is specification 1.1, dated 2026-11-07, *初中数学题库与教学系统完整需求与架构设计方案*. The repository statement of that scope is [PRD.md](PRD.md).

A teacher in Heilongjiang uses a small set of checked questions from the PEP grade-7 first-volume chapter on rational-number operations. On a computer web page and an installable Android app, the teacher checks questions, prints a paper for each student, collects it, confirms the AI suggestion, and assigns the next practice. The scene is one teacher and about 100 students, later perhaps about three teachers and 300 students. Those numbers are a scene, not a capacity guarantee.

This is a long-lived project. It will store real learning records, and teachers will use it. The repository today holds architecture constraints and check scripts. The teaching service is not implemented. `python scripts/status.py` only prints that status. It does not build a paper and it does not start a site.

## The loop the teacher completes

1. Workbook pages stay traceable. The teacher checks the stem, the answer, the worked solution, and the knowledge point. A question can be issued only after both the question version and the applicable answer are approved.
2. The teacher selects by knowledge point, chapter, item type, and difficulty, then generates a separate paper for one or more students. The printed PDF shows a student number and page numbers. It does not print the student's name.
3. Pages come back by photo or by choosing an image. A missing page is flagged. A later upload keeps the history.
4. The AI returns a per-question suggestion and the evidence for it. The teacher confirms, corrects, or marks by hand. A suggestion is not an official result until the teacher confirms it.
5. Confirmed records stay available. The teacher then chooses the same question, a similar one, or a mixed one.

A paper that has already been issued keeps the question and answer from that moment. Later edits to the bank do not change the old paper. A model failure, an unreadable page, or a missing page is not "the student got it wrong."

## Not in the first batch

Online answering, student accounts, parent accounts, parent weekly or monthly reports, knowledge-card editing and printing, editable slides, iOS, a mobile browser standing in for the Android app, cross-institution access, one comparable ability score, a vector database, microservices, offline marking, and a normal path that issues a paper without the check.

## The order of work now

The trial still needs both the web page and Android to finish the loop. The code is narrower than that:

1. The server holds the rules for issuing a paper and for the teacher's confirmation.
2. The first slice is only the browser: check a question, issue a paper, and confirm. The only new directories are `catalog` and `practice`.
3. Android photo, upload, and missing-page handling come after that slice.
4. A desktop install shell comes later, after the web page can check a question and open a formula PDF on the teacher's computer. The candidate is stable Tauri 2. Electron is not the fallback.

These are not chosen yet, because there is no trial data: framework versions, the Android device, the install channel, where the service runs, the recognition and model vendor, backup timing, how a handwritten name is masked, and the detailed permissions used when a second subject is added. Institution decisions DEC-01 through DEC-06 are still blank. FastAPI, PostgreSQL, React, and Flutter are still candidates. See [docs/adr/0010-stack-and-deploy.md](docs/adr/0010-stack-and-deploy.md) and [docs/adr/0011-web-and-desktop.md](docs/adr/0011-web-and-desktop.md).

## Commands

Install: there is no dependency manifest yet. Python is in `.python-version` (3.12). The secret scan also needs gitleaks on `PATH`. Config is in `.env.example`. Copy it to `.env` and keep that file on the machine. The teaching service has no runtime log yet.

`RECORD` in the check output means the command is written here. `DOCS` means the document smoke. Neither means the teaching service started, and neither means AC-01 through AC-09 pass.

Remote checks are the [Actions job named check](https://github.com/wisdom-km/k12-qbank/actions). Acceptance is in [the PRD](PRD.md#acceptance): M1 is the partial check, M3 is the trial, and M4 is the model measurement.

| Name | Command |
| --- | --- |
| Show skeleton status | `python scripts/status.py` |
| Document smoke | `python scripts/smoke_docs.py` |
| Full check | `powershell -ExecutionPolicy Bypass -File scripts/check.ps1` |
| Full check, clean environment | `bash scripts/check` |

## Read first

| File | What it holds |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Short index and the mandatory checks for implementation |
| [PRD.md](PRD.md) | What to build, and what is explicitly out of scope |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Layers, invariants, logging, and gates |
| [RULES.md](RULES.md) | Commits, tests, and the forbidden list |
| [docs/exec-plans/active/rational-number-loop.md](docs/exec-plans/active/rational-number-loop.md) | The first loop, not started yet |

## License

The upstream note suggests MIT. This repository has no license file yet. That suggestion is unverified, so no license text is added here.
