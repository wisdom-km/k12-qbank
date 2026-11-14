# k12-qbank

[English](README.en.md)

机构老师用的数学题库和教学闭环。基线是 2026-11-07 的《初中数学题库与教学系统完整需求与架构设计方案》1.1。原文在 [docs/source/完整需求与架构设计方案-1.1.md](docs/source/完整需求与架构设计方案-1.1.md)。仓库里的对应说明是 [PRD.md](PRD.md)。

黑龙江省的机构老师，用人教版七年级上册有理数运算的一小批已核验题目，在电脑网页和可安装的安卓 App 上完成：核验题目、给每名学生出纸卷、收回、确认 AI 建议、再安排练习。场景是一名老师、大约 100 名学生，以后可能到大约三名老师、300 名学生。这两个数字是场景，不是容量保证。

档位是长期项目。要保存真实学情，老师会访问。文档和检查已经在仓库里。`catalog` 和 `practice` 有一条合成数据上的最小骨架，还没有网页，也没有数据库。`python scripts/status.py` 只打印状态，不出卷、不启动网站。

## 老师要完成的闭环

1. 练习册页面可追溯。老师核验题干、答案、解题过程和知识点。题目版本和适用答案都核准之后，才能正式出卷。
2. 按知识点、章节、题型和难度选题。给一名或多名学生生成各自的卷，打印带学号和页码的 PDF，卷面不印姓名。
3. 拍照或选图收回。缺页要提醒，补传留下历史。
4. AI 给出逐题建议和证据。老师确认、改判或手评。建议在确认之前不是正式结论。
5. 已确认的记录可以回看。老师再选原题、同类题或综合题。

已经发出的卷保留当时的题目和答案。后来改题库，不改旧卷。模型失败、看不清、缺页，都不是「学生做错」。

## 首批不做

学生在线作答，学生账号，家长账号，家长周报和月报，知识卡编辑与打印，可编辑 PPT，iOS，用手机浏览器代替安卓 App，跨机构，统一能力分，向量数据库，微服务，离线批改，以及平时绕过核验直接出卷。

## 现在的开发顺序

产品试用时，网页和安卓都要走完。写代码的顺序更窄：

1. 服务端先守住出卷和老师确认。
2. 第一段只做浏览器里的核验、出卷和确认。目录只建 `catalog` 和 `practice`。
3. 安卓拍照、上传和缺页排在这段之后。
4. 桌面安装壳更后。等老师这台电脑上，网页已经能核验、能打开带公式的 PDF。优先试 Tauri 2 的稳定版。Electron 不是退路。

服务端和网页已采纳 Python 3.12、FastAPI、PostgreSQL、React，见 [docs/adr/0012-adopt-stack.md](docs/adr/0012-adopt-stack.md)。这一段代码还没有导入这些框架。安卓试用机型、安装渠道、部署地点、识别和模型供应商、备份用时、姓名遮挡的具体做法、按学科扩展时的细权限，都还没有试用数据。机构决定 DEC-01 到 DEC-06 还没填。安卓界面仍是候选。详见 [docs/adr/0010-stack-and-deploy.md](docs/adr/0010-stack-and-deploy.md) 和 [docs/adr/0011-web-and-desktop.md](docs/adr/0011-web-and-desktop.md)。

## 当前实现状态

| 部分 | 状态 |
| --- | --- |
| 文档（PRD、架构、规则、ADR、门禁） | 已完成 |
| 业务代码 `catalog` / `practice` | 已开始最小骨架。合成题目上可以拒绝未核准出卷，并按操作键确认一条作答 |
| 教学服务 | 还没有 HTTP 进程，也没有网页 |
| 技术栈 | 已采纳 Python 3.12、FastAPI、PostgreSQL、React（网页优先）。框架包还没安装 |

## 命令

安装：当前没有依赖清单。Python 见 `.python-version`（3.12）。密钥扫描另需本机 PATH 里的 gitleaks。配置见 `.env.example`，复制成 `.env` 后只留在本机。教学服务还没有运行日志。

检查结果里的 `RECORD` 只表示命令写在这里。`DOCS` 只表示文档冒烟。它们都不表示教学服务已经启动，也不表示 AC-01 到 AC-09 已通过。

远端检查看 [Actions 的 check](https://github.com/wisdom-km/k12-qbank/actions)。验收入口见 [PRD 的验收](PRD.md#acceptance)：M1 是部分验证，M3 是试用验收，M4 是模型效果。

| 名称 | 命令 |
| --- | --- |
| 查看骨架状态 | `python scripts/status.py` |
| 文档冒烟 | `python scripts/smoke_docs.py` |
| 最小 core 测试 | `python -m unittest discover -s tests -v` |
| 全量检查 | `powershell -ExecutionPolicy Bypass -File scripts/check.ps1` |
| 全量检查（干净环境） | `bash scripts/check` |

## 先读

| 文件 | 内容 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 给实现用的短索引和强制项 |
| [PRD.md](PRD.md) | 做什么，以及明确不做的事 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 分层、不变量、日志、门禁 |
| [RULES.md](RULES.md) | 提交、测试和禁止事项 |
| [docs/exec-plans/active/rational-number-loop.md](docs/exec-plans/active/rational-number-loop.md) | 第一条闭环：骨架已开始，网页还没有 |

## 许可证

[MIT](LICENSE)。版权人 wisdom-km，2026。
