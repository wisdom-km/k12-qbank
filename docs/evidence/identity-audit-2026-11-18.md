# 登录、授权和审计的一次本机走查

日期：2026-11-18。走查时 `main` 是 `0514e25`（PR #46）。解释器是 conda 环境 `k12-qbank` 的 Python 3.12.16。进程听 `127.0.0.1:8766`。8765 当时被别的进程占用，没有使用。

库是本机已有的 PostgreSQL，库名 `k12`，角色 `k12`，地址 `127.0.0.1:5432`。连接串用 `.env.example` 里的 `K12_PG_DSN`，不写进本页。题目和答案仍在进程内存里。identity 与审计写入该库。这不是试用，也不是 AC-01。默认不设置 `K12_PG_DSN` 的进程仍不连接。

合成账号是 `admin-b6` 和 `teacher-b6`。口令长度 10，含字母和数字，不写入本页。学生用夹具里的 `student-synth`。学科 `math`，题目 `q-v1`。请求体里的 `teacher_id` 写成 `teacher-b`，服务端没有采用它。

## 命令

走查脚本只留在本机临时目录，不进仓库。它启动 `uvicorn backend.bootstrap.http_app:app --host 127.0.0.1 --port 8766 --no-access-log`，环境带 `K12_PG_DSN`、`K12_LOG_FILE=1`、`K12_BOOTSTRAP_ADMIN_USERNAME` 和 `K12_BOOTSTRAP_ADMIN_PASSWORD`。退出码 0。

| 步骤 | 状态 | 结果 |
| --- | --- | --- |
| 管理员登录 | 200 | `role` 是 admin。用户 `04459d2e-902a-4d42-8bb2-0fff7f998dd1` |
| 创建老师 `teacher-b6` | 200 | 用户 `1fc64a72-eb84-4dc6-9b11-6acfaac99844`，status active |
| 老师登录 | 200 | `role` 是 teacher。`actor_teacher_id` 等于上面的用户编号 |
| 核准并发布 `q-v1` | 200 | 内存题目。重启后核准不会留下 |
| 授权前发卷 | 409 | `code` 是 `unauthorized` |
| 管理员授权 `student-synth` / `math` | 200 | `teacher_id` 是会话里的老师编号 |
| 老师发卷 | 200 | 卷 `9a07a7f282b146b49c1c8ced2da2f721`，状态可打印。保存的 `teacher_id` 是会话用户，不是请求体里的 `teacher-b` |
| 管理员撤销 | 200 | 同一老师、学生、学科 |
| 撤销后再发卷 | 409 | `code` 是 `unauthorized` |
| 管理员读审计 | 200 | `total` 14。动作有 `bootstrap_admin:ok`、`create_teacher:ok`、`grant_teacher:ok`、`revoke_grant:ok`、`login:ok`、`logout:ok` |

`K12_ERROR_WEBHOOK_URL` 在这次进程里是空的。没有外部错误接收方。

## 文件日志

当日文件是 `runtime-20261118.jsonl`。事件名有 `login_succeeded`、`session_revoked`、`question_published`、`paper_created`、`use_case_refused`、`http_completed`、`adapter_completed`、`page_stored`。标准输出和这个文件里，两枚合成口令的出现次数是 0，`postgresql://` 的出现次数是 0，`X-K12-CSRF` 的出现次数是 0。

按日的文件名来自当天日期。生产上限是 50MB，这一次文件没有那么大，所以服务进程自己没有再切。同一脚本用 `FileLog` 把上限降到 120 字节，时钟固定在 2026-11-18T12:00:00Z，写出 `runtime-20261118-120005.jsonl` 和仍在写入的 `runtime-20261118.jsonl`。新的当日文件里有事件 `log_rotation`。

这次进程停掉之后，内存里的卷就没了。库里留下 `admin-b6`、`teacher-b6`、已撤销的授权和审计行。
