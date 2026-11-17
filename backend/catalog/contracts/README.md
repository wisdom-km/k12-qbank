# 契约文件

这里是 `k12-question-draft` 第 1 版和 `k12-answer-draft` 第 1 版的 JSON Schema。文件顶部有 `$id` 和 `version`。草稿里的 `schema_version` 用来选择它们。字段含义见 ADR 0013、ADR 0014、ADR 0017 和 ADR 0018。

放在 catalog 下面，是因为 `backend/` 的新目录会被门禁拒绝。核对页仓库 `contracts/` 里有同样的两份文件。改字段时两份一起改。不新增校验用的第三方包。校验器在 `backend/catalog/domain/schema_check.py`，只实现这些文件用到的关键字。
