# ADR 0042 整书导入

状态：accepted

## 背景

核对页的题目键是「大题序号:题号」，只在一页内唯一。题库若直接拿它当全局键，多页导入会在三层撞上：`questions` 按 key 记版本，`answers` 按 `question_key` 只许一条 applicable，`approvals` 用键生成 `qv-` / `av-`。答案集中在书后时，也无从知道一条答案属于哪一页的题。

导入规则若散落在脚本和网页里，两边会分叉。核对页继续不连题库、不连数据库。

## 选项

1. 继续一次导入一页，由调用方自己改键。
2. 规则只放在题库后端的整书导入。脚本和以后的上传页只读目录、登录、调用接口、展示报告。

## 决定

选 2。

- `book_id` 匹配 `^[a-z0-9][a-z0-9-]{0,23}$`。它是书的编号，不是学号。
- 键是 `{book_id}.p{pdf_page:04d}:{原键}`。题目例：`rj-math-7a.p0012:1:1`。属于该题页的答案例：`rj-math-7a.p0012:1:1:ocr:1`。页码至少四位，更长不截断。超长或含非法字符返回 `key_too_long`，不截断。版本 ID 仍是 `qv-` / `av-` 加上把冒号换成连字符的键。
- 答案草稿的 `source.pdf_page` 保持答案页页码。
- 命名空间只在应用层入口做一次。存储适配器不改。已有不带命名空间的行不改写。
- 接口是 `POST /api/admin/catalog/books/{book_id}/import`。管理员，要 CSRF。请求体是 `subject_id`、`dry_run`、`pages`、`pairing`。
- 书清单 `import-book.json` 的字段是 `book_id`、`subject_id`、`pairs`。出现未定义字段，服务端返回 `unknown_field`，整本拒绝。
- 每道题只有 `staged`、`kept`、`skipped`、`conflict`。`kept` 是已存在且题干、选项、答案文本、`type` 相同，任何一层都不新增版本行。`conflict` 是已存在但内容不同，整本不写。`dry_run` 走完校验，报告与真写入相同，但不写任何一行。页级错误或 `conflict` 时，真写入也不写。
- 旧路由 `POST /api/admin/catalog/drafts` 已删除。
- 三个存储各自打开连接。本批不做跨存储事务。核准快照写上之后，再导入同一本书是 `kept`。快照还没写上时重跑可能再记一版。
- 请求体上限仍是 1 MB。超过先返回 `payload_too_large`，不进入导入规则。
- 审计事件 `import_book` 只带 `book_id`、页数和四种计数。

## 后果

核对页保持离线。以后的管理后台上传页调用同一个接口，规则不进网页。导入后要改内容，走核准页。改了题干再导入同一本 `book_id` 会得到 `conflict`，整本不写。答题区大小和公式排版不在本决定里。

## 状态

采纳。2026-11-24。

## 修订（2026-11-24，R4d）

书清单和请求体增加可选字段 `answer_space`。一项是 `page`、`key`、`space`。`key` 是核对页原键，`page` 是题目页页码。服务端按上面的命名空间换成带书号的键。取值只有 `letter`、`blanks`、`small`、`medium`、`large`、`full`。

这一列不是题目内容。重导时只有它变了，结果是 `space_changed`，只更新 `approvals.answer_space`，不新增题目、答案或核准版本。报告和合计带上这个计数。再导入时不写这项覆盖，会把以前的覆盖清回空，同样记 `space_changed`。题干、选项、答案文本或 `type` 不同仍是 `conflict`，整本不写，答题区也不改。

指不到题是 `no_question`。取值不在列表里是 `invalid_answer_space`。同一道题写两次是 `duplicate_answer_space`。都是整本拒绝、零写入。上文「只有四种结果」和审计「四种计数」是当时的决定，不删。审计现在在四种计数之后加上 `space_changed`，仍不记题干。
