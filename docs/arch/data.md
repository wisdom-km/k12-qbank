# 数据

分层、不变量和禁止项仍在 [ARCHITECTURE.md](../../ARCHITECTURE.md)。

关系数据和文件分开，见 ADR 0009。数据库产品定为 PostgreSQL（ADR 0012）。identity 与审计已有迁移 `V001__init.sql`。不设置 `K12_PG_DSN` 时不连接。题目和答案这一段仍不建表。

核心对象：来源与页、题目版本、答案版本、发布记录、知识点、题目和知识点的关系、学生、老师、负责关系、学生卷、页、照片版本、作答、建议、确认。

题目草稿契约是 `k12-question-draft` 第 1 版，见 ADR 0013。形状文件在 `backend/catalog/contracts/`，见 ADR 0017。核对页的 `.questions.json` 由 `import_question_draft` 解析一次后保存。题干、选项、小问和裁图不再转换成第二套 JSON。第一次写入题目时，迁移按 ADR 0013 的表插入同一次解析结果。这一段仍不建表，也不连接 PostgreSQL。裁图只保存坐标。可编辑几何图预留为以后的 `figure_geometry` 表。新题型先映射到已有的 `structure`。只有现有子行放不下时才加子表。综合题是 `composite`，小问各自带题型。

参考答案契约是 `k12-answer-draft` 第 1 版，见 ADR 0014。扫描件、模型候选和老师修改共用 `answer_version`，`origin` 分别是 `ocr`、`model`、`teacher`。核对页把 OCR 答案写成一份文件一条答案。`import_answer_draft` 解析一次后按 `key` 放进内存。同一题最多一条 `applicable` 为 true。模型候选不能标成可出卷。确认过的答案草稿仍不是发布，`answer_version_id` 要等核准。第一次写入答案时才建 `answer_version`、`answer_part`、`answer_asset` 和 `answer_decision`。没有要写入的行时不建空表。学生作答不进这些表。

2026-11-20：`V005__catalog_subtables.sql` 已建 `question_option`、`sub_question`、`question_asset`、`answer_part`、`answer_asset`。`figure_geometry` 和 `answer_decision` 仍不建。上面关于仍不建表的句子是这一步之前的说法。

发布记录、知识点、练习册和多题练习的列见 ADR 0015。解题方法是另一张目录，见 ADR 0016。知识点回答要懂什么，解题方法回答怎么做。某一次做错只生成建议，建议指向已有标识。老师确认后才成为这次错因。错因不写入题目行或参考答案。模型不得因此往目录里插入新行。这些表也是有行要写时才建。现在的学生卷仍只冻结一个题目版本。数据库仍是这一个 PostgreSQL。

2026-11-20：knowledge 的内存端口已接。`knowledge_point`、`question_knowledge`、`method`、`question_method` 仍未建表。

题目正文可以有结构化 JSON。来源、审核、知识点和作答仍然是独立关系，不把整库塞进一个 JSON。

学生卷的合成 PDF 只画面向学生的内容：冻结的公式、学号、页码、总页数和这一份卷的标识。答案和解析不进入这份渲染输入。老师核验页仍按授权显示答案。修改题干或答案会另建一个未核准版本，原来的版本和核准记录留着。渲染读发卷时冻结的公式，不读后来的题干。样张字体是标准库 Helvetica，编码是 WinAnsi，所以乘号这类受支持的字符能画出来。这个字体画不出的字符不生成 PDF。中文用本机已安装的楷体；没有楷体时用微软雅黑，再没有用黑体。只嵌入这一页用到的字形，字体文件不进仓库。机器上没有这些字体时，中文仍不生成 PDF。见 ADR 0024。

状态词：

| 对象 | 状态 |
| --- | --- |
| 学生卷 | 待渲染、可打印、已发放、作废 |
| 卷页 | 缺页、待核对、可用 |
| 分析任务 | 待执行、执行中、已完成、失败 |
| 建议 | 待复核、已采纳或修改、驳回、已过期 |
| 老师记录 | 待处理、已确认、已更正 |

确认的事实和状态在同一次数据库事务里提交。不要在这个事务里等待模型。文件先落盘并核对，再写引用。

操作键：幂等范围是学生卷、小问、服务端确认的老师和操作键字符串。同一范围同内容返回原结果，同一范围不同内容拒绝。复核版本另核；版本变了，第一次确认就拒绝。同一卷、同一小问、同一复核版本只留一条正式记录。

配置只来自环境变量。示例键在 `.env.example`。真实值只在本机 `.env`，该文件被忽略。

迁移：identity 与审计的可回退迁移是 `backend/identity/migrations/V001__init.sql`。题目和答案的可回退迁移是 `backend/catalog/migrations/V004__questions_answers.sql`。子表的可回退迁移是 `backend/catalog/migrations/V005__catalog_subtables.sql`。进程只在 `K12_PG_DSN` 有值时连接并执行迁移。
