# publication 二次 retire 撞 UNIQUE

日期：2026-11-23。基线 `origin/main` `2b9ffad`（PR #76 的合并提交，祖先包含 D8-A `07fa6bb`）。跟踪 [issue #74](https://github.com/wisdom-km/k12-qbank/issues/74)。

本文件只定方案。不改表，不改代码，不改测试。表名是 `publication`，不是 `publications`。`status` 不是 PostgreSQL ENUM，是 `text` 加 CHECK。

## 1. 现状复核

`V007__publication.sql` 建表。列是：

| 列 | 约束 |
| --- | --- |
| `publication_id` | `text` 主键 |
| `question_version_id` | `text NOT NULL` |
| `answer_version_id` | `text NOT NULL` |
| `layout_template_id` | `text NULL` |
| `subject_id` | `text NOT NULL` |
| `status` | `text NOT NULL DEFAULT 'active'` |

两条约束：

- `publication_status_known`：`status IN ('active', 'retired')`。状态空间只有这两个值。
- `publication_binding_unique`：`UNIQUE (question_version_id, answer_version_id, status)`。

对固定的 `(question_version_id, answer_version_id)`，每个 status 至多一行，所以至多两行。合法状态只有四个：没有行；只有 active；只有 retired；一条 active 加一条 retired。两条 active 非法。两条 retired 非法。

`V008__publication_asset.sql` 的外键是：

```sql
publication_id text NOT NULL REFERENCES publication (publication_id) ON DELETE RESTRICT
```

资产行没有 retired 列，没有 generation。`publication_asset_id` 由 `sha256(publication_id + 换行 + checksum)` 的前 16 位十六进制生成。同一 publication 上 checksum 唯一。retire 不改资产行。新 publication 行开始时没有资产。挂到 retired 行上会被拒绝。卸下不看 publication 是不是 retired。

没有别的表外键指向 `publication`。`papers` 不引用它。出卷门闩读的是 `active_of`，只看当前 active 行。

### 谁会插入 publication 行

全库 `INSERT INTO publication` 只有三处。线上会走出新行的只有前两处。

| 入口 | 调用链 | 已有 retired 时会不会再插 active |
| --- | --- | --- |
| `ensure_publication_on_both_approved` | `publish_version._ensure_publication`。两边都核准时调用 | 不会。任一 retired 行就返回 `retired_present`，不调用 `put`。id 形如 `pub-{q}-{a}`，没有序号 |
| `publish_by_binding` | `publish_publication`，HTTP `POST /api/admin/publications/publish` | 会。只拒绝「已经有 active」。序号 `seq = COUNT(*) + 1`，id 形如 `pub-{q}-{a}-{seq}` |
| V007 的祖父 `INSERT` | `migrate up` 一次 | 不会。只抄 `approvals` 里两边都核准且 `approvals.retired = false` 的行。id 形如 `pub-{q}-{a}` |

另外两处不是线上入口：

- `MemoryPublications.fill_grandfather`：测试用，过滤条件和 V007 的 INSERT 相同。
- `Publications.put`：ensure 和测试直接插入。PostgreSQL 的 `_insert` 会撞上三列 UNIQUE。ensure 在 `put` 之前先看过行。

`retire_by_binding` 不插入。它把这一对上 `status = 'active'` 的那一行改成 `retired`。HTTP 是 `POST /api/admin/publications/retire`。没有 active 但已有 retired 时返回 `already_retired`。两行都没有时返回 `not_found`。

内存适配器不执行这条 UNIQUE。`retire_by_binding` 在内存里只是改字段。同一对上两条 retired 在内存里可以同时存在。撞键只发生在 PostgreSQL。

已有测试 `test_publish_by_binding_increments_sequence_after_retire` 停在第二次 publish。它断言一对上同时有 `pub-…-1` retired 和 `pub-…-2` active。它没有做第二次 retire，所以 CI 是绿的，这条失败路径没有被测到。

### 撞键的那一步

第二次 publish 已经成功，状态是「一条 retired 加一条 active」。第二次 retire 执行：

```sql
UPDATE publication
SET status = 'retired'
WHERE question_version_id = %s
  AND answer_version_id = %s
  AND status = 'active'
```

新的 `(qv, av, retired)` 和已有 retired 行重复。PostgreSQL 抛出 `psycopg.errors.UniqueViolation`。`_run` 的事务回滚。active 行保持 active。路由没有捕获这个异常，也没有把它收成 `already_retired`。客户端得到 500。

`retire_publication` 只有在返回码是 `retired` 时才写审计。异常发生在返回之前，所以这次失败不会留下 `publication_retired`。

审计在成功时的取行方式，留到方案里写。代码是 `rows_for` 按 `publication_id` 排序后，取第一条 `status == 'retired'` 的行当作 `target_id`。今天一对上至多一条 retired，所以取到的就是刚改的那一行。这个前提在约束拿掉之后不成立。

## 2. 复现路径

下面是伪代码，不实现，不运行。占位标识是 `q-74`、`a-74`、`subj-74`、`actor-74`。

它只在 PostgreSQL 适配器上稳定失败。内存适配器会返回 `retired`，并留下两条 retired，因为内存不执行 UNIQUE。

```python
def test_second_retire_hits_binding_unique(self) -> None:
    question_id, answer_id = "q-74", "a-74"
    self._approve(question_id, answer_id, "subj-74")
    self.assertEqual(
        self.publications.publish_by_binding(question_id, answer_id, "actor-74"),
        "published",
    )
    self.assertEqual(
        self.publications.retire_by_binding(question_id, answer_id, "actor-74"),
        "retired",
    )
    self.assertEqual(
        self.publications.publish_by_binding(question_id, answer_id, "actor-74"),
        "published",
    )
    # 这里状态是 pub-q-74-a-74-1 retired，pub-q-74-a-74-2 active。
    with self.assertRaises(UniqueViolation):
        self.publications.retire_by_binding(question_id, answer_id, "actor-74")
    rows = self.publications.rows_for(question_id, answer_id)
    by_status = {row.status: row.publication_id for row in rows}
    self.assertEqual(by_status["retired"], "pub-q-74-a-74-1")
    self.assertEqual(by_status["active"], "pub-q-74-a-74-2")
```

`_approve` 的形状和 `tests/catalog/test_publications_contract.py` 里现有的核准桩相同：两边都核准，`approvals.retired` 为 false。不要走 `ensure_publication_on_both_approved`。那条路在第一次 retire 之后返回 `retired_present`，根本不会插入第二行，也就到不了这次撞键。

## 3. 三套方案

八问的答案都按当前代码写死。不留「看数据再定」。

### 方案 A：UNIQUE 改成只约束 active

a. DDL 是一份 V009。不改 V007、V008 的文件。执行语句：

```sql
ALTER TABLE publication DROP CONSTRAINT publication_binding_unique;

CREATE UNIQUE INDEX publication_one_active
    ON publication (question_version_id, answer_version_id)
    WHERE status = 'active';
```

部分唯一索引不能写成表上的 `UNIQUE` 约束，所以用 `CREATE UNIQUE INDEX`。down 是：

```sql
DROP INDEX publication_one_active;

ALTER TABLE publication
    ADD CONSTRAINT publication_binding_unique
    UNIQUE (question_version_id, answer_version_id, status);
```

down 不删除任何行。已经有两条 retired 的绑定会让 `ADD CONSTRAINT` 失败，整个 down 事务回滚。

b. 不更新现有行。旧的三列 UNIQUE 已经保证每个绑定至多一条 active、至多一条 retired。这些行都满足部分索引。V009 里没有 `UPDATE`，也没有 `DELETE`。

c. `ensure_publication_on_both_approved` 不改。见到任一 retired 仍返回 `retired_present`，不插入、不把旧行改回 active。自动核准路径继续「retired 不复活」。

d. `publish_by_binding` 的插入条件不改。它今天已经能在一条 retired 旁边插入新的 active，序号仍是 `COUNT(*) + 1`。部分索引继续挡住第二行 active。

e. `retire_by_binding` 的 `UPDATE` 可以成功，返回码仍是 `retired`。一对上仍至多一条 active，`rowcount == 1` 这个判断不用改。审计必须改：成功之后按 `publication_id` 取第一条 retired，会取到更早的那一行。`pub-q-74-a-74-1` 排在 `pub-q-74-a-74-2` 前面。两次 `publication_retired` 会指向同一个旧 id。Part B 让这次 `UPDATE … RETURNING publication_id`，审计的 `target_id` 用返回的这个 id。

f. 外键保持 `ON DELETE RESTRICT`，不改 V008。旧 publication 行还在，资产留在原来的 `publication_id` 上。新行开始时资产是空的。再挂到任一 retired 行上仍是 `publication_retired`。

g. `list_page` 的过滤和 `ORDER BY publication_id` 不改。`status=retired` 时，同一个绑定可以出现多行，`total` 把它们都算进去。字典序不是数字序：`…-10` 排在 `…-2` 前面。这一批不改排序。

h. 能。每一次 retire 留下自己的行和它上面的资产。历史是多行 publication，不是一行上的状态来回改。

### 方案 B：只留最新一条 retired，旧 retired 行物理删除

名字来自题目。动作不是软删除。旧行从 `publication` 里 `DELETE` 掉。

a. 无 DDL。不建 V009。`publication_binding_unique` 保持。

b. 迁移时刻不改现有行。以后每次 retire，在把 active 改成 retired 之前，先删掉同一绑定上已有的 retired 行。以今天的约束，那个绑定至多有一条旧 retired，所以一次二次 retire 删的就是那一条。

c. ensure 不改。删完之后表里仍有一条 retired（刚改过来的那条），下一次自动核准仍是 `retired_present`。

d. `publish_by_binding` 不改。它仍能在剩下的那一条 retired 旁边插入新的 active。序号仍按当时的行数加一。被删掉的旧 id 不会复用，因为序号只增、不回收。

e. retire 的顺序必须是：先删旧 retired 行，再 `UPDATE` active。倒过来会先撞上仍在的 UNIQUE。返回码仍是 `retired` / `already_retired` / `not_found`。审计只给刚从 active 改成 retired 的那一行写 `publication_retired`。被删掉的旧行不再有新的审计。

f. 外键是 `ON DELETE RESTRICT`，而且 `publication_id` 是 `NOT NULL`。直接 `DELETE` 有资产的 publication 会失败。方案 B 在同一事务里先 `DELETE FROM publication_asset WHERE publication_id = 旧 id`，再 `DELETE` 那条 publication。不把外键改成 `CASCADE`。不把 `publication_id` 改成可空。所以不会留下 publication_id 为空的资产，也不会靠数据库级联悄悄删。这些资产删除不写 `publication_asset_removed`。

g. 列表过滤和 `ORDER BY publication_id` 不改。每个绑定在表里仍至多一条 retired，`total` 的形状和今天一样。已经被删掉的 `publication_id` 再调用列资产，会得到 `publication_not_found`，因为 publication 行没了，`list_assets` 对缺行返回 `None`。

h. 不能。表里只留最新一条 retired。更早的 `publication_id` 和它的资产都没了。`audit_events` 里第一次 retire、第一次 attach 的 `target_id` 还在，但已经对不上行。

### 方案 C：加 generation，UNIQUE 带上它

a. DDL 是一份 V009。执行语句：

```sql
ALTER TABLE publication ADD COLUMN generation integer;

UPDATE publication AS p
SET generation = src.n
FROM (
    SELECT publication_id,
           ROW_NUMBER() OVER (
               PARTITION BY question_version_id, answer_version_id
               ORDER BY CASE status WHEN 'retired' THEN 0 ELSE 1 END,
                        publication_id
           ) AS n
    FROM publication
) AS src
WHERE p.publication_id = src.publication_id;

ALTER TABLE publication ALTER COLUMN generation SET NOT NULL;

ALTER TABLE publication DROP CONSTRAINT publication_binding_unique;

ALTER TABLE publication
    ADD CONSTRAINT publication_binding_generation
    UNIQUE (question_version_id, answer_version_id, generation);

CREATE UNIQUE INDEX publication_one_active
    ON publication (question_version_id, answer_version_id)
    WHERE status = 'active';
```

只加 `(qv, av, generation)` 会允许两条 generation 不同的 active。所以部分唯一索引是这份 DDL 的一部分，不是可选项。down 先删索引和 `publication_binding_generation`，再丢掉 `generation` 列，然后把三列 UNIQUE 加回去。已经有两条 retired 时，加回三列 UNIQUE 会失败，down 回滚。down 不删除行。

b. 要回填，但规则是死的。旧约束下每个绑定只有三种非空形态。只有一行时 `generation = 1`。一行 retired 加一行 active 时，retired 是 1，active 是 2。上面的 `ORDER BY` 只为了在 SQL 里做出这个赋值。它不表示一种通用的时间史。

c. ensure 只在零行时插入，那次写入 `generation = 1`。`retired_present` 和 `already_active` 的判断不改，函数仍不复活旧行。

d. `publish_by_binding` 把已经算好的 `seq = COUNT(*) + 1` 写入 `generation`，id 仍是 `pub-{q}-{a}-{seq}`。不另做一套序号。

e. retire 只把 status 从 active 改成 retired，不改 generation。两条 retired 的 generation 不同，三列 UNIQUE 已经拿掉，所以不撞键。部分索引保证改完之后没有第二条 active。审计和方案 A 一样，不能再取 retired 列表的第一行，必须用 `RETURNING publication_id`。

f. `publication_asset` 不加 generation。资产继续只外键到 `publication_id`，`ON DELETE RESTRICT` 不改。一行 publication 已经是一个 generation，资产挂在这行上就挂在这个 generation 上。再在资产上存一份 generation 会和父行各写各的。

g. 这一批不把 `generation` 放进 `Publication` 或 `PublicationItem`。`list_page` 仍 `ORDER BY publication_id`。`status=retired` 时同一绑定可以有多行，和方案 A 的列表一样。字典序问题还在：没有用 `generation` 排序。

h. 能。每一行有整数 generation，retired 行都留着，资产留在各自的 `publication_id` 上。

generation 怎么生成：用 `publish_by_binding` 已有的递增整数 `COUNT(*) + 1`。ensure 的第一行用 1。不用时间戳。`now()` 在一个事务里不变，也给不出连续版次。不用 UUID。它不能当作版次，也不能代替发布审计里已经写入的 `sequence`。

## 4. 隐含影响

### audit_events

方案 A：失败的第二次 retire 今天没有审计，这点保持。成功之后，若不改取行，两条 `publication_retired` 的 `target_id` 都是 `publication_id` 较小的那条旧行，刚退役的那一行在审计里看不见。和 `RETURNING` 一起改之后，每次真实 retire 一条事件，`target_id` 是那一行，行还在，可以对上。

方案 B：刚退役的那一行仍有一条 `publication_retired`。更早的 publication 行和它的资产被删掉，旧的 `publication_retired` 和 `publication_asset_attached` 还在 `audit_events` 里，`target_id` 悬空。资产删除本身没有 `publication_asset_removed`。读审计的人会看到「挂过文件」，表里已经没有那些文件。

方案 C：和方案 A 相同。generation 不进审计 detail。`target_id` 仍是 `publication_id`。版次要靠行上的 generation 列，或者靠 id 后缀，不能从现有 detail 里读。

### publication_asset

方案 A：同一个 `qv+av` 的多条 retired publication 各挂各的资产。资产不搬家，不删除。`UNIQUE (publication_id, checksum)` 仍按行分开。新 publication 的资产集合是空的。

方案 B：资产跟着被删，不是孤立。步骤是先删 `publication_asset`，再删 `publication`。外键继续 `RESTRICT`。不存在 `publication_id` 为空的资产行。被删的 checksum 可以出现在以后的新 publication 上，因为唯一约束是按 `publication_id` 的。旧的 `publication_asset_id` 不会复用，除非有人用同一个 `publication_id` 和同一个 checksum 再算一次哈希。方案 B 不复用已删的 `publication_id`。

方案 C：资产不加 generation。每个 generation 是自己的 publication 行，资产的归属就是那一行的 `publication_id`。

### ADR 0015

方案 A：列清单不动。补一段：一个绑定至多一条 `active`；`retired` 可以有多行；资产留在被挂上的那个 `publication_id`。不改「第一次发布才建表」那条决定。

方案 B：列清单不动，但要改语义。写明第二次 retire 会物理删除更早的 retired publication，并先删除它的资产。这和 V008 文件里「retire 不改这些资产行」相撞。那句说的是「不要在 retire 时去改当前行的资产」。方案 B 删的是上一行的资产。ADR 必须把这句收窄，否则以后的实现会把它理解成「资产一行都不能删」。修订量比方案 A 大。

方案 C：表里的列清单要加上 `generation`。这是对已采纳列清单的直接修改，再加「至多一条 active」和「资产不带 generation」。修订量是三套里最大的。

### OpenAPI

`PublicationItem` 今天是 `publication_id`、`question_version_id`、`answer_version_id`、`subject_id`、`status`、`layout_template_id`。

方案 A：schema 不变。`GET /api/admin/publications` 在 `status=retired` 时，同一个绑定可以返回多条 item。没有新路径。资产三条路由的 schema 不变。

方案 B：schema 不变。每个绑定在表里仍至多一条 retired，所以这项过滤的行数形态和今天一样。变化在已被删掉的 id：资产列表从「有 items」变成 404 `publication_not_found`。

方案 C：按上面的 DDL 决定，`generation` 不进 `PublicationItem`，所以 schema 不变，行数变化和方案 A 一样。若以后要在响应里加 `generation`，那是另一次契约提交，不是关掉 #74 的必要条件。

## 5. 推荐方案

推荐方案 A。

第二次手动 publish 已经在插入新的 publication 行，测试也已经把「一条 retired 加一条 active」订成了当前行为。缺的只是 retired 不再占唯一键。D8-A 把资产挂在 `publication_id` 上，并规定 retire 不动这些行、新行从空资产开始。方案 A 让这个规定在第二次 retire 之后仍然成立。方案 B 为了保住旧唯一键，删掉上一行和它的资产。方案 C 要解决的撞键，最后仍靠方案 A 那条部分索引；generation 是多出来的列。

方案 A 比另外两套差的地方：

- 表按 republish 次数长行。方案 B 每个绑定始终至多两行。
- 列表在 `status=retired` 下会出现同一个绑定的多行。今天的调用方如果假定至多一条，会看到更多 item。方案 B 没有这个变化。
- 没有整数版次。`publication_id` 字典序在第 10 次之后是错的。方案 C 有 `generation`，可以按数字排。方案 A 这一批不排。
- 祖父行的 id 是 `pub-{q}-{a}`，手动 publish 的 id 是 `pub-{q}-{a}-{n}`。两套 id 没有统一的版次字段。方案 C 有。
- 自动核准仍不会在 retire 之后再发布。要再出一版，必须走手动 `publish_by_binding`。方案 B 和方案 C 也都不改 ensure。这不是 A 独有的缺点，三套都留着。
- 只上 V009、不改审计的话，第二次 `publication_retired` 会指向旧行。这是方案 A 和方案 C 共同的坑。方案 B 因为旧行被删，取「剩下的那条 retired」碰巧是新行，但更早的审计悬空。

实施拆分：

1. 本批：只有这份矩阵。分支 `chore/issue-74-design-matrix`。不开 PR。不关 #74。
2. Part B，一个 PR，合入后关 #74。内容是：V009 的 up 和 down，按方案 A 的草稿；`retire_by_binding` 在码为 `retired` 时带回刚改掉的 `publication_id`（`UPDATE … RETURNING`），`retire_publication` 用这个 id 写审计，不再取 retired 列表的第一行；契约测试覆盖第 2 节的路径，但断言成功：第二次 retire 返回 `retired`，两行都在，第一条上的资产还在，第二条资产是空的，再挂到任一 retired id 上仍是 `publication_retired`。内存和 PostgreSQL 都跑。ADR 0015 加一段，列清单不改。`implementation-matrix` 加一行。OpenAPI 不改，所以没有第二份生成文件提交。
3. 不排 Part C。只有以后列表要按数字版次排序、或响应要露出 generation 时，再单开。那一批不阻塞关 #74。

不单独合入一条红色复现测试。`expectedFailure` 留在 main 上会变成一条长期豁免。失败路径写在本文件第 2 节。成功断言和 V009 放在同一个 Part B。

## 6. 风险清单

- 部分索引一旦放过两条 retired，V009 的 down 不能在不删行的前提下加回三列 UNIQUE。down 选择失败回滚，不在 down 里删历史。这是落地后难回退的点。
- 不在实施前单独合入复现测试。第 2 节的伪代码只供阅读。Part B 用成功断言把路径固化。
- 本仓库没有一份独立的生产库。本地库 `k12` 和草稿库 `k12_d5_schema` 都是在 V007 的三列 UNIQUE 之下建的，所以每个绑定至多一条 active、至多一条 retired，除非有人用手工 SQL 绕过约束。V009 不改这些行。若 `CREATE UNIQUE INDEX` 失败，停下来查这两行 active，不在迁移里删行来换索引成功。本批不连这两份库。
- 只发迁移、不改 `rows[0]` 审计，会让 #74 的撞键消失，同时把审计指错。Part B 把两件事放在同一个 PR。
- 列表继续按 `publication_id` 排序。第 10 个手动版次会排在第 2 个前面。接受这一点，才能在方案 A 下关 #74。要数字序就改选方案 C，并让列表 `ORDER BY generation`。

## 自审

- 三套方案各八问都写了确定的 DDL、回填、函数行为和资产动作。没有「视情况而定」。
- 推荐方案 A 的缺点写了行数、列表行数、没有整数版次、两套 id、审计取行。没有只写优点。
- 方案 B 的资产是先删子行再删父行，外键保持 `RESTRICT`，不孤立。方案 A 和方案 C 的资产留在原 `publication_id`。没有写成以后再定。
- 没有改 R1–R6。出卷仍只看 active。作答、照片、学号、姓名的边界没进这份矩阵。
- 例子里没有真实学号和姓名。标识是 `q-74`、`a-74`、`subj-74`、`actor-74`。
- 第 2 节是伪代码。不实现，不运行。
