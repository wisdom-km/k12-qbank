# catalog 与 practice 的一次本机走查

日期：2026-11-18。走查时代码在分支 `feat/c1-catalog-practice-pg` 的工作区，证据页随后写入同一次提交。解释器是 conda 环境 `k12-qbank` 的 Python 3.12.16。进程听 `127.0.0.1:8766`。8765 当时被别的进程占用（PID 34168），没有使用。

库是本机已有的 PostgreSQL，库名 `k12`，角色 `k12`，地址 `127.0.0.1:5432`。连接串用 `.env.example` 里的 `K12_PG_DSN`，不写进本页。这次设置了 `K12_FILE_DIR`，目录在本机临时路径，不进仓库。`files` 表只存编号、用途和校验和，页字节在该目录。这不是试用，也不是 AC-01。默认不设置 `K12_PG_DSN` 的进程仍不连接。

合成老师是 `teacher-synth`。口令用仓库里的合成口令，不写入本页。学生 `student-synth`，学科 `math`，题目 `q-v1`，复核 `rev-1`。请求体里的 `teacher_id` 写成 `teacher-ignored`，服务端没有采用它。

## 命令

走查脚本只留在本机临时目录，不进仓库。它启动 `uvicorn backend.bootstrap.http_app:app --host 127.0.0.1 --port 8766 --no-access-log`，环境带 `K12_PG_DSN`、`K12_FILE_DIR` 和 `K12_LOG_FILE=1`。脚本退出码 0。两次服务进程在走查后被停掉。

| 步骤 | 状态 | 结果 |
| --- | --- | --- |
| 老师登录 | 200 | `role` 是 teacher。用户 `teacher-synth` |
| 发布 `q-v1` | 200 | `question_approved` 为 true |
| 发卷 | 200 | 卷 `6b954cb8f0354575ac3c6b8b1eca2eff`，状态可打印。保存的 `teacher_id` 是 `teacher-synth`。文件 `file-97577607241aefff` |
| 读作答 | 200 | 小问 `sq-1`，复核 `rev-1`，状态 pending。作答编号 `fixture-answer-6b954cb8f0354575ac3c6b8b1eca2eff`。文字是夹具里的待确认文字 |
| 确认 | 200 | 确认 `74fbaa1275f3413594deef8148f449bd`，决定 adopt，计数 1 |
| 读页字节 | 200 | 1087 字节，开头是 PDF |
| 停进程后再启动，再登录 | 200 | 仍是 `teacher-synth` |
| 再读卷列表 | 200 | 计数 1，同一张卷，状态仍是可打印，老师仍是 `teacher-synth` |
| 再读作答 | 200 | 同一作答编号，文字仍是夹具里的待确认文字 |
| 再读确认计数 | 200 | 计数 1 |
| 再读页字节 | 200 | 仍是 1087 字节，开头是 PDF |
| 再读题目 | 200 | `question_approved` 为 false。启动时夹具把核准行写回未发布。卷和确认没有被删 |

库里这次留下 1 行 papers、1 行 paper_pages、1 行 attempts、1 行 confirmations、1 行 files。早先走查留下的 identity 行没有被清掉。

## 文件日志

当日文件在这次进程的日志目录。事件名有 `login_succeeded`、`question_published`、`paper_created`、`adapter_completed`、`page_stored`、`attempt_confirmed`、`http_completed`。合成口令的出现次数是 0，`postgresql://` 的出现次数是 0，`X-K12-CSRF` 的出现次数是 0。因为设置了 `K12_FILE_DIR`，日志里没有 `memory_files`。

`K12_ERROR_WEBHOOK_URL` 在这次进程里是空的。没有外部错误接收方。规范化题目表和答案表仍没有建。
