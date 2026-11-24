# 导入一本书

规则在题库后端。这个脚本只读目录、登录、调用接口、把报告写到书目录。核对页不连题库。

服务要先在本机听着。默认地址是 `http://127.0.0.1:8765`。这个端口和核对页相同，两个进程不要同时听。

## 书目录

只认文件名里带 `page_` 加数字的页。页码取文件名里最后一处 `page_` 数字。

每一页可以有 `{stem}.page-role.txt`。文件内容去掉空白后正好是 `answers` 时，这一页是答案页，脚本只读 `{stem}.answers/`。缺这个文件，或内容不是 `answers`，这一页是题目页，脚本只读 `{stem}.questions.json`。换过种类之后，另一种旧文件可以留在目录里，脚本不读。

`_review_backups/`、以点开头的目录、以及名字里带 `.reviewed.` 的文件都不读。

书目录下要有 `import-book.json`：

```json
{
  "book_id": "rj-math-7a",
  "subject_id": "math",
  "pairs": [
    {"answer_page": 101, "question_page": 12},
    {"answer_page": 101, "question_page": 13, "keys": ["2:1", "2:2"]}
  ]
}
```

`book_id` 是书的编号，匹配 `^[a-z0-9][a-z0-9-]{0,23}$`，不是学号。`pairs` 把答案页配到题目页。`keys` 是答案上的原题目键。不写 `keys` 时，这一页答案全部配到那一页题。答案已经写在题目页上的书，`pairs` 可以是空数组。多出来的字段服务端会以 `unknown_field` 整本拒绝。

## 双击

双击 `scripts/import_book.cmd`。

找 Python 的顺序是环境变量 `K12_PYTHON`，然后 `conda run -n k12-qbank python`，然后 `py -3.12`。都找不到时，窗口会说明要安装 conda 环境 `k12-qbank` 或设置 `K12_PYTHON`。说明见议题 88。

没有在命令行传入书目录时，会弹出选文件夹窗口。选完就执行。结束时窗口暂停，不自动关。

也可以：

```text
scripts\import_book.cmd --book-dir D:\books\rj-math-7a
```

`--server` 默认先读 `K12_IMPORT_SERVER`，再默认 `http://127.0.0.1:8765`。`--dry-run-only` 只做预演，不询问写入。

Python 低于 3.12 时脚本会退出，并说明改用 conda 环境 `k12-qbank`。

## 登录和首次改密

用户名取环境变量 `K12_IMPORT_USER`。没有就在窗口里询问。口令用输入框读取，不回显，不写日志，不存盘。

账号若要求先改口令，脚本会请你输入两次新口令，再调用 `/api/account/password`。两次不一致就退出，不把口令打出来。

## 预演和写入

脚本先做一次 `dry_run`，并打印 `staged`、`kept`、`skipped`、`conflict`、`space_changed`。有页级错误或 `conflict` 时，写出报告，退出码 1，不写入。

没有这些错误时，询问「确认写入？(y/N)」。只有 `y` 或 `Y` 会真写入。拒绝时仍留下预演报告，退出码 0。

## 报告

报告在书目录的 `_import_reports/`：

```text
import-{book_id}-{UTC时间}.json
import-{book_id}-{UTC时间}.txt
```

里面有页码、原键、带命名空间的键、结果和原因，以及合计。没有口令、会话编号、CSRF。

每页的 `outcome` 是 `ok` 或 `rejected`。每题的结果：

| 结果 | 含义 |
| --- | --- |
| staged | 这次新写入 |
| kept | 库里已有，题干、选项、答案文本和 type 相同。没有新版本行 |
| skipped | 这道题没有采用的答案 |
| conflict | 库里已有，但内容不同。这一次整本都没有写 |
| space_changed | 题干、选项、答案文本和 type 都没变，只有答题区大小变了。只更新这一列 |

`written` 为 false 表示这次没有落库。`dry_run` 为 true 表示这是预演。

## 逐题设置答题区大小

`import-book.json` 可以加可选的 `answer_space`。不写时，导入后按题型使用默认值：选择题 `letter`，填空题 `blanks`，解答题和综合题 `large`，其余 `medium`。库里这一列留空，表示「用默认」。

要覆盖某一题：

```json
{
  "book_id": "rj-math-7a",
  "subject_id": "math",
  "pairs": [],
  "answer_space": [
    {"page": 12, "key": "3:1", "space": "full"}
  ]
}
```

`page` 是题目页页码，和文件名里的 `page_` 数字相同。`key` 是核对页上的原键，例如 `3:1`，不要自己加上书号。`space` 只能是 `letter`、`blanks`、`small`、`medium`、`large`、`full`。

指到没有的题，整本拒绝，原因在该页的 `no_question`。取值不在列表里是 `invalid_answer_space`。同一页同一键写两次是 `duplicate_answer_space`。这三种都不写入。

已经导入过的书，如果只改了这里的大小，重导的结果是 `space_changed`，题干和其他行不变。这次清单里不再写某一题，会把上次的覆盖清掉，回到按题型默认，同样记 `space_changed`。题干变了仍是 `conflict`，答题区也不会被这次改掉。

已发出的卷用的是出卷时存下的坐标，不受这次重导影响。

## 遇到 conflict

在核准页里修订这道题。库里的原内容保持不变，同一本 `book_id` 可以再导，未改动的题是 `kept`。

或者换一个新的 `book_id` 再导。那是另一本书，键不同，不会覆盖原来的书，库里会有两套题。

不要改了题干再对同一个 `book_id` 重导。服务端会整本拒绝，已经在库里的内容不变。

## 常见问题

Python 版本不对：窗口或脚本会写明当前版本。使用 conda 环境 `k12-qbank`，或设置 `K12_PYTHON` 指向 3.12。

服务没启动：连接失败。先按 README 启动本机站点，并确认核对页没有占用 8765。

登录失败：核对用户名和口令。口令不会出现在报告里。账号停用或口令错误时，看服务标准输出里的错误码，不看报告正文。

## 公式警告怎么处理

报告里某一题的原因是 `formula_unsupported` 加命令名时，这道题已经导入。警告不挡整本。卷面还印不出这个命令。

在核对页里改成 ADR 0046 列出的写法，再把这本书重导。已经比较为 kept 的行不会被这次重导改写，也不会补上公式片段。要让这道题带上分开保存的文字和公式，需要在核对页改出新版本后再导。不要改服务端去从纯文本里猜公式。

旧行没有公式片段时，目录里 `formula_note` 是「公式未结构化」。纯文本里如果还有反斜杠命令，出卷整份拒绝，错误码 `formula_unstructured`。结构化片段里不认识的命令是 `formula_unsupported`。一个公式比一行宽是 `formula_too_wide`。三种都不会把源码印到卷面上。
