# k12-qbank

[English](README.en.md)

机构老师用的数学题库和教学闭环。基线是 2026-11-07 的《初中数学题库与教学系统完整需求与架构设计方案》1.1。仓库里的对应说明是 [PRD.md](PRD.md)。

黑龙江省的机构老师，用人教版七年级上册有理数运算的一小批已核验题目，在电脑网页和可安装的安卓 App 上完成：核验题目、给每名学生出纸卷、收回、确认 AI 建议、再安排练习。场景是一名老师、大约 100 名学生，以后可能到大约三名老师、300 名学生。这两个数字是场景，不是容量保证。

档位是长期项目。要保存真实学情，老师会访问。当前仓库是架构约束和检查脚本，教学服务还没有实现。`python scripts/status.py` 只打印这句状态，不出卷、不启动网站。

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

框架版本、安卓试用机型、安装渠道、部署地点、识别和模型供应商、备份用时、姓名遮挡的具体做法、按学科扩展时的细权限，都还没有试用数据，不能写成已经选定。机构决定 DEC-01 到 DEC-06 还没填。FastAPI、PostgreSQL、React、Flutter 仍是候选。详见 [docs/adr/0010-stack-and-deploy.md](docs/adr/0010-stack-and-deploy.md) 和 [docs/adr/0011-web-and-desktop.md](docs/adr/0011-web-and-desktop.md)。

## 怎么跑

- 安装：当前没有依赖清单。Python 见 `.python-version`（3.12）。密钥扫描另需本机 PATH 里的 gitleaks。
- 启动：`python scripts/status.py`
- 测试：`python scripts/smoke_docs.py`
- 全量检查：Windows 用 `powershell -ExecutionPolicy Bypass -File scripts/check.ps1`。干净环境用 `bash scripts/check`。
- 日志在哪看：教学服务还没有运行日志。检查脚本的输出就在这条命令的终端里。
- 需要的配置：见 `.env.example`。复制成 `.env` 后只留在本机。不要提交 `.env`。

## 现在可以运行的命令

```text
python scripts/status.py
python scripts/smoke_docs.py
powershell -ExecutionPolicy Bypass -File scripts/check.ps1
```

文档冒烟通过，只说明约束文件还在，不说明 AC-01 到 AC-09 已通过。

## 先读

| 文件 | 内容 |
| --- | --- |
| [AGENTS.md](AGENTS.md) | 给实现用的短索引和强制项 |
| [PRD.md](PRD.md) | 做什么，以及明确不做的事 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 分层、不变量、日志、门禁 |
| [RULES.md](RULES.md) | 提交、测试和禁止事项 |
| [docs/exec-plans/active/rational-number-loop.md](docs/exec-plans/active/rational-number-loop.md) | 第一条还没开工的闭环 |

## 许可证

上游说明里的许可证建议是 MIT，仓库里还没有许可证文件。未核实，不在这里补一个未经选择的许可证正文。
