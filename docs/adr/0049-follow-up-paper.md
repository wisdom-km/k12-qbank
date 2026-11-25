# ADR 0049 从已确认批改再出一份练习

状态：accepted

## 背景

老师闭环已经能核验入库、出卷排版、拍照收卷、看 AI 建议并确认结论。批改页确认之后，还不能针对这张卷里没完全掌握的题，给同一个学生再出一份巩固练习，并记下新卷来自哪张原卷。

按知识点推荐同类新题属于路线图 B 级，试用后再做。本批只从原卷已确认的错题、部分对和空白再出。

## 选项

1. 老师在选题页手工再挑一遍同样的题。来源卷号没有地方记。
2. 把未采用的 AI 建议也算进再练范围。
3. 只依据未作废的 `teacher_decision`。默认再出 `incorrect`、`partial`、`blank`。新卷用可空的 `source_paper_id` 记下原卷。复用现有出卷、排版、公式、二维码和学号印制。

## 决定

选 3。

### 数据

V019 给 `papers` 增加可空的 `source_paper_id text`。无外键，不回填旧行。写入时空字符串存成 NULL。读出 NULL 时映射为 `""`。

老的出卷调用不传这个字段，新卷的来源是空。

### 规则

`POST /api/practice/papers/{paper_id}/follow-up`。

请求体可选 `order_nos` 和 `review_version_id`。省略或空的 `order_nos` 由服务端选出当前结论为 `incorrect`、`partial` 或 `blank` 的题，按 `order_no` 升序。显式传入时可以去掉部分错题，也可以带上已确认的 `correct`。省略 `review_version_id` 时沿用原卷的复核版本。出卷老师只取会话，不读请求体里的老师编号。

没有当前 `teacher_decision` 的题是未确认。AI 建议不是结论。有建议、没有老师结论的题不入选。

原卷不存在是 404 `not_found`。会话老师不是这张卷的出卷老师，或对该学生和学科已无有效授权，是 403 `permission_denied`。重复、非正整数或原卷没有的 `order_no` 是 409 `invalid_order_no`。指定的题还没有当前结论是 409 `decision_required`。最终一题都没有是 409 `no_retry_items`。

一道题走 `open_paper`，两道及以上走 `open_multi_paper`。学生、学科沿用原卷。版式是 `flow`。二维码开关、印在卷上的学号、公式排版沿用现有出卷。production 下不绑定合成作答。

题后来被停用、公式不支持或一整页放不下，沿用现有 409。停用的码是 `retired`。这些拒绝不写出新卷。

不改原卷、原卷快照、收卷照片、AI 运行和老师结论。

列表、出卷和再出卷的响应都带 `source_paper_id`。没有来源时是空字符串。

审计事件 `follow_up_paper_issued`，模块 `practice.follow_up`。明细只有 `source_paper_id`、`paper_id`、`item_count`。不带学号、姓名、题干、答案。

### 页面

批改页列出已有老师结论的题。默认勾选 `incorrect`、`partial`、`blank`。老师可以取消，也可以加选已确认的 `correct`。尚未确认的题不能勾。一题都没勾时，按钮禁用，并写「暂无可再练的已确认错题」。

成功后页面给出新卷号、题数、打开 PDF 和正式发放。老师页卷列表在来源非空时标明「再练自」加上原卷号。

## 后果

按知识点推荐同类新题仍不做。一次给多名学生出同一份卷仍不做。按课时自动配对答案仍不做。R6a 的真实样张实测仍未做。
