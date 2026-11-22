# D8 Part A：publication_asset 与 list publications 设计矩阵

日期：2026-11-23。基线：`origin/main` `c7b40d2`（PR #69 的合并提交）。

本文件只记录调研和倾向。不改表，不改端口，不改路由，不选字节放在哪里。Part B 及以后的 PR 才落 migration 和代码。

读过的文件：

- `backend/catalog/migrations/V007__publication.sql`
- `backend/catalog/api.py` 的 `Publications`
- `backend/catalog/domain/publication.py`
- `backend/catalog/application/publish_publication.py`
- `backend/catalog/application/retire_publication.py`
- `backend/catalog/application/ensure_publication.py`（函数名是 `ensure_publication_on_both_approved`）
- `backend/catalog/adapters/pg_publications.py`
- `backend/bootstrap/routes_admin.py`
- `docs/adr/0015-publication-and-practice.md`
- `docs/adr/0016-knowledge-and-methods.md`
- `docs/adr/0009-files-and-rows.md`
- `backend/catalog/migrations/V002__catalog_practice.sql` 的 `files`、`papers`、`paper_pages`
- `backend/catalog/migrations/V005__catalog_subtables.sql` 的 `question_asset`、`answer_asset`
- `backend/practice/adapters/pg_files.py`
- `backend/identity/application/queries.py` 的 `list_audit_events` 与 `_bound`
- `backend/identity/migrations/V001__init.sql` 的 `audit_events`
- `ARCHITECTURE.md` 的 R1–R6，`RULES.md` 的 L-05

## 1. 现状盘点

### 1.1 `publication` 当前列

`V007__publication.sql` 建一张表。文件头写明 `publication_asset` 本次不建。

| 列 | 约束 |
| --- | --- |
| `publication_id` | `text` 主键 |
| `question_version_id` | `text NOT NULL` |
| `answer_version_id` | `text NOT NULL` |
| `layout_template_id` | `text NULL` |
| `subject_id` | `text NOT NULL` |
| `status` | `text NOT NULL DEFAULT 'active'` |

约束：

- `publication_status_known`：`status IN ('active', 'retired')`
- `publication_binding_unique`：`UNIQUE (question_version_id, answer_version_id, status)`

没有 `created_at`，没有 `created_by`，没有资产列。

状态词只有 `active` 和 `retired`。`published` 是 `publish_publication` 的返回码，不是列值。本矩阵后面的过滤用 `active|retired`。

两套 id：

- V007 补录：`pub-{question_version_id}-{answer_version_id}`。只复制双方都核准且 `NOT retired` 的 approval。不写 layout，不写审计。
- 显式 `publish_by_binding`：`pub-{question_version_id}-{answer_version_id}-{seq}`。`seq` 是该绑定已有行数加 1。`subject_id` 从 approval 读。layout 去空白，空则 NULL。

`retire_by_binding` 是 `UPDATE publication SET status = 'retired'`，条件是该绑定上的 `active` 行。不是 `DELETE`。已有 retired 行则返回 `already_retired`。没有行则 `not_found`。

`UNIQUE (question_version_id, answer_version_id, status)` 让同一绑定最多一条 `active`、一条 `retired`。第一次 retire 后再 publish，可以并存一条 retired 和一条新的 active。对第二条 active 再 retire 时，UPDATE 会把第二行也变成 `retired`，与已有 retired 行撞这把唯一键。这是 publication 表现状，不是资产表的事。D8 不动这把键。

### 1.2 publish / retire / ensure 的当前签名

端口在 `Publications` 上，不看角色。`request_id` 不进端口。

```python
def publish_by_binding(
    self,
    question_version_id: str,
    answer_version_id: str,
    actor: str,
    layout_template_id: str | None = None,
) -> str:
    """published | already_active | not_approved"""

def retire_by_binding(self, q_vid: str, a_vid: str, actor: str | None) -> str:
    """retired | already_retired | not_found。空 actor 抛 StoreFault invalid_actor。"""
```

用例：

```python
def publish_publication(
    publications: Publications,
    question_version_id: str,
    answer_version_id: str,
    actor: str | None,
    logger: Logger,
    layout_template_id: str | None = None,
    request_id: str | None = None,
) -> str:
```

只有返回码 `published` 才写审计。`action` 为 `publication_published`。`target_kind` 为 `publication`。`target_id` 为当时 active 行的 `publication_id`。`module` 为 `catalog.publication`。`detail_json` 的键：`question_version_id`、`answer_version_id`、`subject_id`、`layout_template_id`、`sequence`、`after.status=active`。

```python
def retire_publication(
    publications: Publications,
    q_vid: str,
    a_vid: str,
    actor: str | None,
    logger: Logger,
    request_id: str | None = None,
) -> str:
```

只有返回码 `retired` 才写审计。`action` 为 `publication_retired`。`detail_json` 的键：`question_version_id`、`answer_version_id`、`subject_id`、`before.status=active`、`after.status=retired`。

```python
def ensure_publication_on_both_approved(
    publications: Publications,
    q_vid: str,
    a_vid: str,
    subject_id: str,
) -> Literal["created", "already_active", "retired_present"]:
```

已有 active 则 `already_active`。已有 retired 则 `retired_present`，不把 retired 改回 active。否则 `put` 一条补录 id，status `active`，无 layout。不写 `publication_asset`。不写审计。

`list_active()` 返回全部 `active` 行，无过滤、无分页、不含 retired。注释写明给契约测试和出卷用的是 `active_of`。它不是管理列表。

### 1.3 现有 admin publication 路由

`backend/bootstrap/routes_admin.py`：

| 方法 | 路径 | 第一句 |
| --- | --- | --- |
| POST | `/api/admin/publications/retire` | `admin_only` |
| POST | `/api/admin/publications/publish` | `admin_only` |

请求体只有绑定。retire：`question_version_id`、`answer_version_id`。publish 多一个可选 `layout_template_id`。actor 只来自 `request.state.actor.user_id`。

同文件里其他 admin 路由，供列表风格对齐：GET `/api/admin/teachers`、GET `/api/admin/students`、GET `/api/admin/grants`、GET `/api/admin/audit`。写操作是 POST。`GET /api/admin/audit` 的查询参数是 `limit=50`、`offset=0`、`action=""`、`actor_user_id=""`。成功正文是 `{"total", "events"}`。成功读取写一条 `admin_read_committed`，`detail_json` 只有 `limit`、`offset` 和过滤字段的名字，不写过滤值。`_bound`：`limit < 1` 变成 1，`limit > 200` 变成 200，`offset < 0` 变成 0。

没有 `GET /api/admin/publications`。

### 1.4 确认没有资产表，也没有列表查询

- 全仓 migration 没有 `CREATE TABLE publication_asset`。`V007` 注释写「不建」。`tests/identity/test_migrations.py` 断言 V007 文本里没有这句。
- `docs/release/E1-release-readiness-2026-11-22.md` 把这两项留在 D8。`docs/implementation-matrix.md` 2026-11-22 行写明资产表仍未做，端口不校验角色。
- 没有 V008。版本在各切片间唯一。已用到 V007。identity 占用 V001 和 V003，catalog 占用 V002、V004–V007。
- `question_asset` / `answer_asset`（V005）是裁图框：`role` 的 CHECK 只有 `crop`，列是 bbox 和 position。不是文件行，不能拿来当 `publication_asset`。
- `files`（V002）只有 `file_id`、`purpose`、`checksum`。`PgFiles` 把 `purpose` 写成常量 `page`，`file_id` 为 `file-` 加 sha256 前 16 位十六进制，字节在 `K12_FILE_DIR`。这是学生卷页，不是发布附件。
- `papers.file_id`、`papers.file_checksum`、`papers.asset_ids`、`paper_pages.asset_ids` 是发出去的卷的快照。

相邻表故意不进本设计：`knowledge_point`、`question_knowledge`、`method`、`question_method`、错因建议（ADR 0016：建议不是发布记录）。`practice_item`、`attempts`、`paper_pages` 留在 practice。

## 2. publication_asset 设计矩阵

ADR 0015 的最小列是 `publication_id` 加文件标识，文件本体仍按 ADR 0009。ADR 0009：行里记稳定标识、用途、校验值和关联。先把字节放稳并核对，再登记引用。行里不写路径。本批不选择字节放在哪一种存储里。

下面的 CREATE 是草案，本批不落地。

```sql
CREATE TABLE publication_asset (
    publication_asset_id text PRIMARY KEY,
    publication_id text NOT NULL REFERENCES publication (publication_id) ON DELETE RESTRICT,
    file_id text NOT NULL,
    kind text NOT NULL,
    checksum text NOT NULL,
    size_bytes bigint NOT NULL,
    mime_type text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL,
    CONSTRAINT publication_asset_kind_check
        CHECK (kind IN ('image', 'pdf')),
    CONSTRAINT publication_asset_checksum_check
        CHECK (checksum ~ '^[0-9a-f]{64}$'),
    CONSTRAINT publication_asset_size_check
        CHECK (size_bytes >= 0),
    CONSTRAINT publication_asset_mime_check
        CHECK (mime_type <> ''),
    CONSTRAINT publication_asset_file_id_check
        CHECK (file_id ~ '^pubfile-[0-9a-f]{16}$'),
    CONSTRAINT publication_asset_actor_check
        CHECK (created_by <> ''),
    CONSTRAINT publication_asset_publication_checksum_key
        UNIQUE (publication_id, checksum)
);
```

没有 `uri`。没有 `storage_backend`。没有 `retired`。没有 `student_id`、姓名、文件名、`bytea`、bbox。`file_id` 不引用 `files(file_id)`。

`publication_asset_id` 由端口生成，不接受调用方传入：`pa-` + `publication_id` + `-` + `checksum` 前 16 位。同一 `(publication_id, checksum)` 因此只有一个 id。

### a. 挂在 publication 上，不挂在绑定上

倾向：一行资产只属于一个 `publication_id`。

理由：ADR 0015 写的就是 `publication_id` 加文件标识。retire 后再 publish 会插入新的 `publication_id`（在唯一键还允许插入的前提下）。旧 id 上的资产必须留在旧 id，不能跟着绑定流到新的 active 行。同一道题出现在多次发布里，资产行不共用。字节若相同，是两行各自带同一个 `checksum`。共用发生在校验值这一层，不发生在资产行这一层。

替代：挂在 `(question_version_id, answer_version_id)` 上，让再次 publish 继承旧资产。不采用。那会把旧发布的历史拷到新的 active 行，和 `ensure_publication_on_both_approved` 的 `retired_present` 不复活语义相反。

### b. 列：要 file_id 和 checksum；不要 uri，不要 retired

倾向：上表这些列。任务清单里的 `id` 具体化为 `publication_asset_id`。任务清单里的 `sha256` 具体化为 `checksum`，值是 64 位小写十六进制，算法与 `PgFiles` 的 `hashlib.sha256().hexdigest()` 相同。任务清单里的 `uri` 不建。`retired` 不建。

理由：

- 现有 `files.checksum` 和 `papers.file_checksum` 已经用这个名字存 sha256。隐私守卫要拿 `checksum` 和这两列对照。另起 `sha256` 列名会让对照写成两套字段。
- ADR 0009 禁止在行里放路径或 URL。`uri` 无论写成盘符、对象键还是 URL，都是路径。
- 本表是新表，没有旧行。`created_at timestamptz NOT NULL DEFAULT now()` 不会把迁移时刻写进历史行。`publication` 本身已有补录行，所以那里不能用同样的默认值冒充发布时间。两张表分开看。
- `created_by` 存 actor 的 `user_id`，不存显示名。
- `retired` 列会和 `publication.status` 各写各的。retire 今天只 UPDATE 父行。子行再维护一份状态，就会出现父行 retired、子行仍标 active。

替代：只建 ADR 0015 的两列 `publication_id` 和 `file_id`，把 checksum、大小、mime 挪到扩写后的 `files`。不采用。那要改 `files`，而 `PgFiles` 把 `purpose` 固定为 `page`，并且 `ON CONFLICT` 会覆盖 `purpose`。发布附件和学生页会写进同一张用途表。

### c. kind 先只有 image 和 pdf，用 CHECK

倾向：`CHECK (kind IN ('image', 'pdf'))`。不要 `audio`、`video`、`attachment`、`other`。

理由：ADR 0015 的规则是没有真实写入就不做空的通用枚举。`publication_status_known` 和 `question_asset` 的 `role = 'crop'` 都是收紧的 CHECK。`other` 和 `attachment` 没有边界，整页学生照片可以用这两个值挂进来。现在没有音频或视频的写入者。以后要加值，用一次新 migration 放宽 CHECK。放宽是加行之前的事。先放进六个值，再想删掉已有行，才难回退。

替代：任务清单里的六值枚举，或开放字符串只加非空 CHECK。不采用。六值里的 `other` 等于没有枚举。开放字符串连 CHECK 都守不住第 h 条。

### d. 行里只存 file_id，不存 uri，不存 storage_backend

倾向：不建 `uri`，不建 `storage_backend`。字节不在这行里。本批不选择字节放在本地目录、对象存储还是别的介质。

理由：ADR 0009 的行只记稳定标识、用途、校验值和关联。`storage_backend` 本身就是在行里写下介质种类，等于本批做了选型。`files.purpose = 'page'` 和 `K12_FILE_DIR` 的页写入器不能借来当发布附件的存储。`file_id` 的 CHECK 要求 `pubfile-` 加 16 位十六进制，用来和页文件的 `file-` 前缀错开。这是标识形状，不是介质选型。

`file_id` 不加指向 `files(file_id)` 的外键。那条外键会迫使每个发布附件先成为 `purpose = 'page'` 的行，或迫使去改 `PgFiles`。两件事都越出本表。

替代：现在就写对象键或本地路径。不采用。那就是在本批选定介质。

和 ADR 0009 顺序的衔接：先放稳字节并核对，再登记引用。因此 D8-A 的端口可以插入资产行，供契约测试使用合成 `pubfile-` 标识。D8-A 不提供上传字节的 HTTP，也不提供管理端的挂接路由。等以后的存储批次先核对字节，再调用这个端口，然后才加 HTTP。那一批才选介质。

### e. checksum 不是全局唯一；同一 publication 不能挂两份相同 checksum

倾向：`UNIQUE (publication_id, checksum)`。不同 publication 可以各有一行相同的 checksum。同一 publication 第二次挂上同一 checksum 时，端口返回 `already_attached`，不插第二行，不写第二条审计。本批不加 `position`。

理由：同一幅图出现在两次发布里，是两行，retire 其中一次不能删掉另一次的行。全局 `UNIQUE (checksum)` 会把无关发布绑在一起。ADR 0015 没有 position。同一份字节在同一次发布上出现两次，本批不表示成第二行。

替代：全局唯一 checksum，或加上 position 允许同 checksum 两行。不采用。全局唯一和「retire 不带走别的发布」冲突。position 是另一套排序语义，ADR 0015 没列，管理列表也不读它。

### f. publication retire 时资产留在原 publication_id

倾向：retire 只改 `publication.status`。不 UPDATE 资产行，不 DELETE 资产行。按这个 `publication_id` 去读，retired 之后仍然读到这些资产。新的 publish 得到新的 `publication_id`，上面零条资产。不从旧 id 复制。`ensure_publication_on_both_approved` 仍然不写资产，仍然在见到 retired 时返回 `retired_present`。

外键是 `ON DELETE RESTRICT`。今天没有删除 publication 行的路径。不用 `ON DELETE CASCADE`。

挂接不看 `status`。active 和 retired 的 `publication_id` 都可以挂接。不存在的 id 返回 `not_found`。挂到 retired 行上不改变 `publication.status`，所以不是把 retired 复活。

移除只删 `publication_asset` 这一行。不删字节，因为字节放在哪还没选，本端口也不扫描任何目录。不改 `papers`。以后若有存储批次要删字节，先确认没有任何 `publication_asset.checksum` 或 `papers.file_checksum` 仍指向它。那是那一批的规则，不是本批的介质选型。

理由：D6 的 retire 是父行 UPDATE。资产若跟着标 retired 或被删掉，父行状态和子行会分叉，已发出卷若只靠 checksum 对账也会丢掉目录侧的引用。新 active 行从零开始，避免旧发布的文件出现在新 id 上。

替代：retire 时把每条资产标 retired，或连字节一起删。不采用。标 retired 是第 b 条已经拒绝的第二状态。删字节在介质未选时没有对象可删，也会删掉仍可能被旧 publication_id 引用的历史。

### g. 真实的挂上和卸下才进 audit_events

倾向：进。动作名 `publication_asset_attached` 和 `publication_asset_removed`。`target_kind` 为 `publication_asset`。`target_id` 为 `publication_asset_id`。`actor_user_id` 是 `created_by`。`module` 为 `catalog.publication`。`request_id` 仍不进端口，由路由写入，和 publish 一样。

`already_attached` 不写第二条审计。卸下一个不存在的 id 返回 `not_found`，不写审计。

`detail_json` 只允许这些键：

- `publication_id`
- `publication_asset_id`
- `file_id`
- `kind`
- `checksum`
- `size_bytes`
- `mime_type`
- 挂上时 `after: {"attached": true}`
- 卸下时 `before: {"attached": true}`

不写 uri、字节、文件名、学生标识、显示名。

理由：publish 和 retire 已经是「只有真实状态变化才审计」。资产的挂上和卸下是同类变化。等管理界面再补审计，中间的端口调用会没有痕迹。detail 的键和 publish 一样，只放目录标识和这次变化，不放文件内容。

替代：等管理 UI 再审计。不采用。端口一旦能写行，审计就该在同一次用例里。

### h. 隐私守卫：列、CHECK、以及三次拒绝

R1–R6 的句子本身没有写学号、姓名或整页照片。本设计不改这六条的语义。学号、姓名、照片的禁令在 `RULES.md` L-05、`ARCHITECTURE.md` F-08，以及 ADR 0015 第 8 条（学生作答、缺页、照片、模型建议不进这些 catalog 表）。下面的守卫落实这三处，不把它们写进 R1–R6。

字段和 CHECK：

- 表上没有 `student_id`、姓名、显示名、题干、文件名、`bytea`、bbox。这些值没有列可写。
- `created_by` 只存 `user_id`。
- `kind` 不能是 `page`、`attempt` 或任何「整页」值。只有 `image` 和 `pdf`。
- `file_id` 的 CHECK 拒绝 `^file-[0-9a-f]{16}$`。那是 `PgFiles` 页文件的标识形状。

用例在插入前再拒绝，命中则不写行、不写审计：

1. `file_id` 已存在于 `files` 且该行 `purpose = 'page'`。
2. `file_id` 等于任一 `papers.file_id`。
3. `checksum` 等于任一 `papers.file_checksum`，或等于任一 `files.checksum` 且该行 `purpose = 'page'`。

挂接和卸下都不 UPDATE `papers`、`paper_pages`、`papers.asset_ids`、`paper_pages.asset_ids`。R2 现有语义是改题库不改已发出的卷。这里不改写 R2，只是资产用例不去碰那些列。

学生页的归属仍在 `papers` / `paper_pages`（R4 的现有语义：页和作答对应学生卷）。资产行不复制 `student_id`。

D8-A 没有上传字节的 HTTP。不存在「先交一张整页照片，再挂到发布上」这条入口。能写入的只有：一个已经满足 `pubfile-` CHECK、且没有撞上上面三次拒绝的标识。

日志和 `detail_json` 不包含字节或文件名。L-05 仍约束那一行 log。契约测试断言 detail 的键集合就是第 g 条列出的那些。

路由一旦加上，第一句是 `admin_only`。这沿用 D7 的路由门。不把 R6 改写成「老师可以列出全部学科」。R6 仍是学习记录按学科和授权，未授权就拒绝。

替代：只在文档里写「后续考虑隐私」。不采用。上面的 CHECK 和三次拒绝就是本批的守卫。

## 3. list publications 查询端口

### a. 端口签名

倾向：加在 `Publications` 上。用例做分页夹紧并写读审计。用例不调用 `admin_only`。路由调用。

```python
def list_page(
    self,
    *,
    question_version_id: str | None = None,
    answer_version_id: str | None = None,
    subject_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[tuple[Publication, ...], int]:
    """返回 (这一页, 过滤后的总行数)。"""
```

夹紧放在 `backend/catalog/domain/publication.py` 的一个函数里，Memory 和 Pg 都调用它。数字与 `queries._bound` 相同：`limit < 1` 变为 1，`limit > 200` 变为 200，`offset < 0` 变为 0。catalog 不 import `identity.application.queries`。

`status` 不是 `None`、`active`、`retired` 三者之一时，端口在查询前抛 `StoreFault("invalid_status")`。路由把它映成 HTTP 400，`error_response` 的 code 为 `invalid_status`。这不是 `invalid_actor` 那种 500：空 actor 是会话坏了，坏的查询参数是调用方写错。

空字符串与 `None` 相同，表示这个过滤不生效。`GET /api/admin/audit` 的空 `action` 就是这样。

`offset` 大于等于总行数时，返回空页和原来的 `total`。

成功 HTTP 正文：

```json
{"total": 0, "publications": []}
```

每条只有 `publication_id`、`question_version_id`、`answer_version_id`、`subject_id`、`status`、`layout_template_id`。不连 `approvals.stem`。

成功读取写一条 `admin_read_committed`。`target_kind` 为 `publication`。`detail_json` 只有 `limit`、`offset`，以及实际生效的过滤字段名（`question_version_id`、`answer_version_id`、`subject_id`、`status` 中的名字）。不写这些字段的值。与 `list_audit_events` 的 `_filters` 相同。

替代：在端口里调用 `admin_only`。不采用。D7 已经把 publication 端口做成与角色无关，角色门在路由。`list_audit_events` 在用例里调用 `admin_only`，那是 identity 的旧做法，不搬进 catalog。

### b. 四个过滤都可选；没有时间和创建者

倾向：`question_version_id`、`answer_version_id`、`subject_id`、`status` 都可选。两个版本号可以只填一个。两个都填则是 AND。`status` 只接受 `active` 或 `retired`。全空则返回全部行的一页，含 retired。这是管理员名册。路由仍是 `admin_only`。

不按时间范围过滤。不按创建者过滤。

理由：`publication` 没有 `created_at`，也没有 `created_by`。补录行没有审计。`audit_events` 补不出创建者，因为 `ensure_publication_on_both_approved` 不写审计，而 `publication_published` 只覆盖显式 publish。给 `publication` 加 `created_at timestamptz NOT NULL DEFAULT now()` 会把迁移时刻写进每一条补录行，那个时刻不是发布时间。

若以后真要这两个过滤：单独的 migration 加 `published_at timestamptz NULL` 和 `created_by text NULL`，不回填。只有这两列有值的行才能被这两个条件命中。那不是本列表端口的一部分，也不占用 V008。

省略 `status` 时包含 retired。理由：管理列表要看见 `retired_present` 挡住的那条历史。默认只给 active，管理界面会看不见为什么旧行没有复活。

替代：时间范围和创建者作为必选过滤。不采用。表上没有能诚实回答这两个问题的列。

### c. offset + limit

倾向：offset + limit。默认 50。最大 200。夹紧规则见第 a 条。不用 cursor。

理由：`GET /api/admin/audit` 已经是这套数字。cursor 需要稳定的单调列。本表没有 `created_at`，`publication_id` 是文本，补录 id 和带 seq 的 id 不是同一套时间顺序。用 id 做 cursor 会假装它是时间。

替代：cursor。不采用。没有可做游标的单调列。

### d. 只按 publication_id 升序

倾向：`ORDER BY publication_id ASC`。调用方不能传排序字段。

理由：`list_active` 和 `rows_for` 已经 `ORDER BY publication_id`。两个适配器沿用同一句，页的顺序才稳定。没有 `created_at` 可排。开放排序字段会让 Memory 和 Pg 各写一套，也会把不存在的列暴露成查询参数。

替代：允许 `status` 或 `subject_id` 做排序键。不采用。管理列表要的是稳定翻页。状态过滤已经由第 b 条的 `status` 参数完成。

### e. 端口不看角色；路由 admin_only；老师不走这条列表

倾向：与 D7 相同。端口不看角色。`GET` 路由第一句是 `admin_only`。老师不获得这份全表。老师出卷仍走已有的 `active_of`，一次只查一个绑定。

理由：全表列出每个 `subject_id`。那比 `teacher_grants` 宽。R6 仍只约束学习记录，本条不改写 R6。未登录请求仍由现有 `http_gate` 返回 401 `unauthenticated`，到不了路由。已登录老师得到 403 `permission_denied`。管理员得到 200。GET 沿用现有规则，不要求 `X-K12-CSRF`。

替代：老师只读，并在端口里按 grant 滤学科。不采用。那是把角色语义放进端口，也要新的 grant 查询。D7 没有这么做。本列表是管理员名册。

### f. GET，查询参数，不走 POST

倾向：

`GET /api/admin/publications?question_version_id=&answer_version_id=&subject_id=&status=&limit=&offset=`

理由：同文件的列表都是 GET，`GET /api/admin/audit` 用查询参数。POST 留给 `/api/admin/publications/retire` 和 `/publish`。过滤值不进 body，也就不进一条需要 CSRF 的写请求。

替代：POST 加 JSON body。不采用。那和现有 admin 读路由不一致，还会给一次只读套上 CSRF。

## 4. Migration 和契约测试怎么拆

拆成两个以后的 PR。本批不开 PR。

| 顺序 | 名称 | 内容 | migration |
| --- | --- | --- | --- |
| 先 | D8-B list | `list_page`、夹紧、两个适配器、`GET` 路由、读审计、OpenAPI 用现有脚本重写 | 无 |
| 后 | D8-A asset | 上表、挂接/卸下端口、第 h 条守卫、审计 | `V008__publication_asset.sql` 与 `V008__publication_asset.down.sql` |

依赖：列表不读资产表。资产不读列表。两者都会改 `Publications` 和 `routes_admin.py`，所以不并行开两条分支，也不合成一个 PR。D8-A 从合入 D8-B 之后的 main 拉出来。

先做列表的理由：它不新增表，用现有列就能给管理界面翻页。资产表的唯一键、外键和 CHECK 一旦有行就难改。把难回退的表放在第二个 PR。

不把 V008 花在给 `publication` 加 `created_at`。若第 3.b 条的可空 `published_at` / `created_by` 以后被点名要做，那是再下一号 migration（V009），并且不回填。本矩阵不建议现在做。

D8-A 的 down 只 `DROP TABLE publication_asset`。不改 `publication` 的列。`tests/identity/test_migrations.py` 里的版本列表要加上 `V008`。V007 文本仍然不得包含 `CREATE TABLE publication_asset`。这是 D8-A 那次要改的测试，本批不动。

契约测试沿用 `tests/catalog/test_publications_contract.py`：Memory 每次都跑，Pg 在 `K12_PG_DSN` 有值时跑同一组断言。scratch 库仍用 `k12_d5_schema`，不碰本机库 `k12`。

资产，每个适配器 8 条：

1. 对已有 publication 挂接，返回生成的 `publication_asset_id`。
2. 同一 checksum 再挂一次，返回 `already_attached`，行数不变，审计不增加。
3. 未知 `publication_id` 返回 `not_found`，不写行。
4. `kind` 不是 `image` 或 `pdf` 时，在插入前拒绝。
5. `file_id` 或 `checksum` 撞上 `files.purpose = 'page'`、`papers.file_id` 或 `papers.file_checksum` 时拒绝，不写行。
6. retire 之后资产仍在旧 `publication_id` 上；新 publish 出来的 id 上是零条。
7. `ensure_publication_on_both_approved` 仍不写资产，见到 retired 仍返回 `retired_present`。
8. 一次真实挂接和一次真实卸下各写一条审计，detail 键只有第 2.g 条列出的那些，没有学生字段。

列表，每个适配器 6 条：

1. 过滤全空时返回一页和 `total`，`total` 含 retired。
2. 四个可选过滤各自收窄结果；版本号可以只填一个。
3. `status` 不是 `active` 或 `retired` 时拒绝。
4. `limit` 0 和 10000 夹成 1 和 200。
5. `offset` 小于 0 夹成 0；`offset` 大于等于 `total` 时得到空页和原来的 `total`。
6. 顺序是 `publication_id` 升序，两个适配器一致。

HTTP 另测，不算进上面的 8 和 6：管理员 GET 200；已登录老师 403 `permission_denied`；未登录由现有 gate 返回 401，路由函数不是返回 401 的那一层；非法 `status` 为 400 `invalid_status`；成功读取恰好一条 `admin_read_committed`，detail 里是过滤字段名。D8-B 若因此要重写 OpenAPI 和 `api.types.ts`，只用 `scripts/export_openapi.py` 和 `scripts/check_api_types.py --write`。

举例只用合成标识，例如 `q-d8-1`、`a-d8-1`、`pub-q-d8-1-a-d8-1-1`、64 位小写十六进制的校验值、`pubfile-` 加 16 位十六进制。不写真实学号、姓名或整页照片。

## 5. 风险

难回退：

- `UNIQUE (publication_id, checksum)` 和外键 `ON DELETE RESTRICT` 一旦有行，改键要先搬数据。
- `kind` 的 CHECK 收成两值之后，已有行会挡住再收紧。放宽要新 migration。
- `file_id` 的 `pubfile-` CHECK 一旦有行，就不能改前缀。
- 给 `publication` 补 `NOT NULL DEFAULT now()` 的时间列，无法事后变成真实发布时间。本矩阵不建这列。

本批故意留下、等拍板的不确定：

1. 行里没有 `uri`，没有 `storage_backend`。D8-A 不提供上传 HTTP。介质是再下一批的事。若 Part B 在资产行里加路径，就推翻 ADR 0009 和本矩阵第 2.d 条。
2. 同一 publication 不允许两行相同 checksum，也没有 position。管理界面若必须在同一次发布上把同一份字节放两次，这把唯一键要改。
3. 列表不能按时间或创建者过滤，除非另做可空列且不回填。本矩阵不把这件事放进 D8-B。

和其他切片的边界：

- practice：`papers`、`paper_pages`、`papers.asset_ids`、`files.purpose = 'page'`、`attempts`、`practice_item` 都不改。资产守卫只读 `files` 和 `papers` 来拒绝撞车。
- knowledge：知识点、做法、错因建议不进 `publication`，也不进 `publication_asset`。
- `question_asset` / `answer_asset` 继续只做裁图框。
- `publication` 的 `UNIQUE (question_version_id, answer_version_id, status)` 本批不改。它已经让同一绑定只有一条 retired。第二次 retire 会撞这把键。要修的话单独开切片，不塞进 D8-A 或 D8-B。

## 6. 本批不做

- 不改 schema、代码、测试、`requirements.txt`、CI。
- 不改两份 waiver 文档，不改 issue #70、#71、#73，不改 PR #72。
- 不选存储介质。
- 不开 PR。
