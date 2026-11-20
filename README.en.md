# k12-qbank

[中文](README.md)

A math question bank and teaching loop for teachers at one institution. The baseline is specification 1.1, dated 2026-11-07, *初中数学题库与教学系统完整需求与架构设计方案*. The original is [docs/source/完整需求与架构设计方案-1.1.md](docs/source/完整需求与架构设计方案-1.1.md). The repository statement of that scope is [PRD.md](PRD.md).

A teacher in Heilongjiang uses a small set of checked questions from the PEP grade-7 first-volume chapter on rational-number operations. On a computer web page and an installable Android app, the teacher checks questions, prints a paper for each student, collects it, confirms the AI suggestion, and assigns the next practice. The scene is one teacher and about 100 students, later perhaps about three teachers and 300 students. Those numbers are a scene, not a capacity guarantee.

This is a long-lived project. It will store real learning records, and teachers will use it. The docs and the checks are in the repository. `catalog` and `practice` can check, issue, open a PDF, and confirm on synthetic data on this machine. Identity and audit are already on PostgreSQL. With `K12_PG_DSN` set, the catalog and practice runtime tables are written there too (see [ADR 0039](docs/adr/0039-catalog-persistence.md)). V004 creates `questions` and `answers`. V005 creates `question_option`, `sub_question`, `question_asset`, `answer_part`, and `answer_asset`. `figure_geometry` and `answer_decision` are still not created. `python scripts/status.py` only prints that status. It does not start the site.

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
2. The first slice is the browser: check a question, issue a paper, and confirm, in `catalog` and `practice`. As of 2026-11-18, `PHASE_SLICES` also lists `identity`. A blank value still falls back to `catalog` and `practice`. See `docs/exec-plans/active/identity-and-audit.md`.
3. Android photo, upload, and missing-page handling come after that slice.
4. A desktop install shell comes later, after the web page can check a question and open a formula PDF on the teacher's computer. The candidate is stable Tauri 2. Electron is not the fallback.

A reviewed question file is `.questions.json` from [md-json-review](https://github.com/wisdom-km/md-json-review). The contract is `k12-question-draft` version 1. The bank parses that file once and stores it. It does not convert the stem into a second JSON shape. See [docs/adr/0013-draft-and-geometry.md](docs/adr/0013-draft-and-geometry.md).

An OCR answer is one file in `{stem}.answers/` from the review tool. The contract is `k12-answer-draft` version 1. `import_answer_draft` parses that file once and stores it. It does not convert the answer into a second JSON shape. A scanned key, a model candidate, and a teacher edit share this contract. The source is `origin`. See [docs/adr/0014-answer-versions.md](docs/adr/0014-answer-versions.md).

Each schema file has `$id` and `version`. Each draft file has `schema_version`. An unknown version stays `not_draft` and the message names the version that arrived. See [docs/adr/0018-schema-version.md](docs/adr/0018-schema-version.md).

## Compatibility

This main and [md-json-review](https://github.com/wisdom-km/md-json-review) main share the two contracts below. The annotated tag `draft-contract-1` points at the main commit that contains this table. An earlier commit does not represent this contract.

| Contract | File version | Draft schema_version | $id |
| --- | --- | --- | --- |
| k12-question-draft | 1 | 1 | https://github.com/wisdom-km/k12-qbank/contracts/k12-question-draft.v1.schema.json |
| k12-answer-draft | 1 | 1 | https://github.com/wisdom-km/k12-qbank/contracts/k12-answer-draft.v1.schema.json |

The review tool is the producer. It copies the two JSON Schema files from `backend/catalog/contracts/` and writes an integer `schema_version`. This repository is the consumer. `import_question_draft` and `import_answer_draft` dispatch on `$id` and `schema_version`.

Job `review-import` installs the review tool's main and imports both drafts from a synthetic page. The fixture is not a textbook page.

The server and the web page adopt Python 3.12, FastAPI, PostgreSQL, and React. See [docs/adr/0012-adopt-stack.md](docs/adr/0012-adopt-stack.md). The local synthetic path uses FastAPI and React. An empty `K12_PG_DSN` does not connect. A set value connects and migrates identity, audit, catalog, and practice. Page bytes use `K12_FILE_DIR`. `K12_ENV` defaults to development. production exits when the DSN or `K12_FILE_DIR` is empty. V004 creates `questions` and `answers`. V005 creates the five child tables. `figure_geometry` and `answer_decision` are still not created. The Android device, the install channel, where the service runs, the recognition and model vendor, backup timing, how a handwritten name is masked, and the detailed permissions for a second subject still have no trial data. Institution decisions DEC-01 through DEC-06 are still blank. The Android UI is still a candidate. See [docs/adr/0010-stack-and-deploy.md](docs/adr/0010-stack-and-deploy.md) and [docs/adr/0011-web-and-desktop.md](docs/adr/0011-web-and-desktop.md).

## Current implementation

| Part | State |
| --- | --- |
| Docs (PRD, architecture, rules, ADRs, gates) | Done |
| Business code `catalog` / `practice` | On synthetic questions it refuses an unapproved issue, writes a one-page PDF, and confirms one answer by operation key |
| Teaching service | Local synthetic HTTP now has a session. The default process does not connect. There is no public release. The pages are `/login`, `/`, and `/admin` |
| Login | Page `/login`. A signed-out visit to `/` or `/admin` goes to the login page. The session cookie is `k12_sid`. Writes send `X-K12-CSRF` |
| Admin | Page `/admin`. An admin creates teachers and students, grants and revokes, and reads audit and errors. A teacher sees permission_denied |
| PostgreSQL connected | The process connects and migrates identity, audit, catalog, and practice only when `K12_PG_DSN` is set. Page bytes use `K12_FILE_DIR`. `K12_ENV` defaults to development; production exits when the DSN or the page-byte directory is empty. The default process and the unit tests do not connect. The CI `postgres` job runs migrate up, down, and up, plus the identity and catalog/practice contracts and the migration lock |
| Run mode | `K12_ENV` defaults to development. production exits when the DSN or `K12_FILE_DIR` is empty. development with an empty DSN stays in memory |
| Catalog PG | A set `K12_PG_DSN` writes the V002 runtime tables, V004 `questions` and `answers`, and the five V005 child tables. `figure_geometry` and `answer_decision` are still not built |
| Practice PG | A set `K12_PG_DSN` writes papers, attempts, and confirmations. Page bytes use `K12_FILE_DIR` |
| Stack | Python 3.12, FastAPI, and React are pinned. PostgreSQL connects and migrates when `K12_PG_DSN` is set |
| Question draft import | Accepts `k12-question-draft` version 1. Stored in memory. Not issuable |
| Answer draft import | Accepts `k12-answer-draft` version 1. Stored in memory. Not issuable. A running approval can also write V004 `answers` plus V005 `answer_part` and `answer_asset`. `answer_decision` is still not created |
| Contract check | JSON Schema in `backend/catalog/contracts/`. No new package. See [docs/adr/0017-contract-schema.md](docs/adr/0017-contract-schema.md) |
| Publication, knowledge, multi-item papers | Columns are in ADR 0015. Tables are not created. A paper still holds one question |
| Methods and error causes | Columns are in [docs/adr/0016-knowledge-and-methods.md](docs/adr/0016-knowledge-and-methods.md). The catalog is stored. An error cause is a suggestion. Tables are not created |

## Commands

Install: Python is in `.python-version` (3.12). Run `python -m pip install -r requirements.txt`, then `npm ci --prefix apps/web` and `npm run build --prefix apps/web`. The secret scan also needs gitleaks on `PATH`. Config is in `.env.example`. Copy it to `.env` and keep that file on the machine. The synthetic HTTP log goes to that process's stdout.

Start the local synthetic site (an empty `K12_PG_DSN` does not connect; a set value connects and migrates):

```text
python -m uvicorn backend.bootstrap.http_app:app --host 127.0.0.1 --port 8765 --no-access-log
```

The default access log is off. Structured logs that include `request_id` still go to stdout. This port is the same as the md-json-review check page. Do not start this server while that page is running. The two processes must not both listen on `127.0.0.1:8765`.

Open `http://127.0.0.1:8765/login`. A signed-out visit lands on the login page. After login, a teacher is at `/` and an admin is at `/admin`. The issue actor comes from the session cookie. The synthetic account is still `teacher-synth`. development reads `docs/fixtures/rational-number-min.json` and clears both approval flags. There is no separate load command. `K12_ENV=production` does not load this synthetic fixture and does not create the synthetic account. The second synthetic student, `student-synth-2`, is only in the server grant. It does not add a seventh fixture block.

When the site is already listening on port 8765, run `python scripts/smoke_http.py` in another window. To re-check:

```text
python -W error::ResourceWarning -m unittest discover -s tests -v
npm test --prefix apps/web
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1
git diff --check
```

`RECORD` in the check output means the command is written here. `DOCS` means the document smoke. Neither means the teaching service started, and neither means AC-01 through AC-09 pass.

Remote checks are the [Actions job named check](https://github.com/wisdom-km/k12-qbank/actions). Acceptance is in [the PRD](PRD.md#acceptance): M1 is the partial check, M3 is the trial, and M4 is the model measurement.

| Name | Command |
| --- | --- |
| Show skeleton status | `python scripts/status.py` |
| Document smoke | `python scripts/smoke_docs.py` |
| Minimal core tests | `python -m unittest discover -s tests -v` |
| Full check | `powershell -ExecutionPolicy Bypass -File scripts/check.ps1` |
| Full check, clean environment | `bash scripts/check` |

## Read first

| File | What it holds |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Short index and the mandatory checks for implementation |
| [PRD.md](PRD.md) | What to build, and what is explicitly out of scope |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Layers, invariants, logging, and gates. Port, data, and log-event tables are in [docs/arch/](docs/arch/) |
| [RULES.md](RULES.md) | Commits, tests, and the forbidden list |
| [docs/exec-plans/active/rational-number-loop.md](docs/exec-plans/active/rational-number-loop.md) | The first loop: local synthetic web. PostgreSQL and Android are not in yet |
| [docs/implementation-matrix.md](docs/implementation-matrix.md) | Where each of the six slices stands: ports, adapters, and tests |

## License

[MIT](LICENSE). Copyright wisdom-km, 2026.
