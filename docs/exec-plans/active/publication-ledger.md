# 执行计划：publication 发布账本

状态：进行中。2026-11-21。这一段只覆盖发布账本的落库和出卷前的存在检查。多题练习停在 [practice-item.md](practice-item.md)。

## 决定

- 表按 ADR 0015 的 publication 条目。列是 `publication_id`、`question_version_id`、`answer_version_id`、`layout_template_id`、`subject_id`、`status`。`status` 只接受 `active` 和 `retired`。
- `layout_template_id` 本批可空，没有读写。版面绑定以后再做。
- 不建 `publication_asset`。不提供 retire 动作，也不改已有行的 `status`。
- 迁移 V007 给双方都已核准、且 `retired` 不为 true 的 approval 补一条 `active`。`approvals.retired` 是 `boolean NOT NULL`，条件写成 `AND NOT retired`。
- retired approval 不作 grandfather。若该 binding 未来被重新核准，走正常 publish 路径产生新的 publication，不由迁移兜底。
- 正式写入前要有一条 `active` 发布。多题在 `_is_item_approved` 四分支之后检查。单题在 `issue_paper` 拿到核准结果之后、`add_paper` 之前检查。拒绝码是 `no_active_publication`。
- 不传发布账本的旧单题写入保持原样。开卷、渲染、复核不回查 publication。

## 完成线

`publication` 表存在。grandfather 不复活 retired。两条 compose 路径在传入账本时拒绝没有 active 发布的 binding。旧卷仍能打开。

2026-11-21：端口、内存适配器、PostgreSQL 适配器和出卷前检查已接上。契约见 `tests/catalog/test_publications_contract.py` 和 `tests/practice/test_practice_item_contract.py`。空库核对见 `docs/evidence/publication-table-2026-11-21.md`。

2026-11-22：HTTP 出卷传入 `publications`。`retire_by_binding` 落地，只在真正撤销时写审计。端口不校验角色。

2026-11-22：管理员路由 `POST /api/admin/publications/retire` 与 `POST /api/admin/publications/publish`。路由第一句是 `admin_only`，401 和 CSRF 仍在 `http_gate`。显式 publish 的 `subject_id` 从 approvals 读，空串是 `invalid_subject`。`layout_template_id` trim 后非空才写入。`publication_id` 是 `pub-{question}-{answer}-{seq}`。只在 outcome 为 `published` 时写 `publication_published`。端口仍不校验角色。issue #66 仍开，等 PR。

## 还不做

- `publication_asset`。
- `layout_template_id` 绑定到出卷。显式 publish 只保存字符串。
- 把 retired 行改回 active。再次 publish 另插一条 active，序号加一。
- 端口里的角色校验。路由用 `admin_only`。issue #66 仍开。
- knowledge 的 PostgreSQL 表、`figure_geometry`、`answer_decision`。
- M-14 的外部接收方。issue #47 仍开着，本批不关闭、不改标签。
