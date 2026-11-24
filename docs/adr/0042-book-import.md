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
