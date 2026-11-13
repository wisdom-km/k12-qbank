# k12-qbank

机构老师用的数学题库和教学闭环。首批是人教版七年级上册有理数运算：核验题目、给每名学生出纸卷、拍照收回、老师确认 AI 建议、再练。

档位是长期项目。要保存真实学情，老师会访问。当前仓库是架构约束和检查脚本，教学服务还没有实现。`python scripts/status.py` 只打印这句状态，不出卷、不启动网站。

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

方案基线是 2026-11-07 的《初中数学题库与教学系统完整需求与架构设计方案》1.1。机构确认项 DEC-01 到 DEC-06 还没填。

## 许可证

上游说明里的许可证建议是 MIT，仓库里还没有许可证文件。未核实，不在这里补一个未经选择的许可证正文。
