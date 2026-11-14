# AGENTS.md

本文只做指针，不复制规格正文。冲突时优先级：用户当场的明确指示 > [RULES.md](RULES.md) > [ARCHITECTURE.md](ARCHITECTURE.md) > [PRD.md](PRD.md) > 历史草案。

## 一句话

- 产品：机构老师用电脑网页和安卓 App，把已核验的数学题发给学生、收回纸卷、确认 AI 建议，并安排再练。
- 范围外：学生在线作答、家长报告、知识卡编辑器、可编辑 PPT、iOS、跨机构。见 [PRD.md](PRD.md) 的范围外。

## 开工前必读

- 下面的「强制项」
- [RULES.md](RULES.md) 禁止清单
- [RULES.md](RULES.md) Definition of Done

## 强制项（MUST）

编号来自 project-essentials 的 MANDATORY.md，正文不抄到这里。

- 档位：长期。依据方案 1.1 的长期信号选定。见 [docs/adr/0001-long-lived-tier.md](docs/adr/0001-long-lived-tier.md)。
- 条件：[D] 存真实用户数据：是。[P] 别人能访问：是。
- 本档 MUST：M-01 版本控制且 main 只经 PR；M-02 一条命令能跑且 CI 在干净环境跑通；M-03 密钥不进仓库；M-04 结构化日志加请求 ID；M-05 不吞错；M-06 core 单测、契约、回归、少量端到端；M-07 独立审查，敏感改动要人审；M-08 CI 且为必需检查；M-09 锁文件；M-12 架构文档与代码同 PR；M-13 版本号与回滚。
- 条件 MUST：[D] M-11 数据安全；[P] M-10 安全基础 8 条，以及 M-14 健康检查与错误上报。
- 本档 SHOULD：M-15 无障碍。ASVS L1 自查是 SHOULD，不拦发布。
- 红线：R-1 密钥不进仓库也不进日志；R-2 不对真实数据做没有备份的不可逆操作；R-3 不编造测试或检查结果。
- 全量检查：Windows 用 `powershell -ExecutionPolicy Bypass -File scripts/check.ps1`。干净环境用 `bash scripts/check`。退出码非 0 就是未满足。
- 豁免：只认用户原话，记在 [docs/WAIVERS.md](docs/WAIVERS.md)，并另写一条 ADR。R-1 到 R-3 不能豁免。
- 关口：开工前 G0；说完成前 G1；合入前 G2；发布前 G3。每项只写 PASS（附证据）/ FAIL / WAIVED / N/A。哪个阶段拦什么，见 [ARCHITECTURE.md](ARCHITECTURE.md) 的「关口」。合成数据上的第一条路径，不被尚未存在的服务或数据库挡住。真实学生试用前才要求运行时安全验证，以及数据库和文件的联合恢复。
- **某一关适用的 MUST 是 FAIL：报告「未满足：M-xx」和补法，不说完成，不合入，不发布。** 门禁表里任一 MUST 写成 FAIL 时，先看它是不是这一关适用的项。

## 按任务类型读哪些节

| 任务类型 | 先读 |
| --- | --- |
| 改界面，不改规则 | [DESIGN.md](DESIGN.md)；ARCHITECTURE 的依赖规则 |
| 改业务规则 | PRD 里对应的 US 和 AC；ARCHITECTURE 的不变量 R1–R6 |
| 加适配器或换模型 | ARCHITECTURE 的端口；[docs/adr/0005-analysis-ports.md](docs/adr/0005-analysis-ports.md) |
| 排查 bug | 先按 request_id 看日志，命令见下；再读 ARCHITECTURE 的运行日志 |
| 第一段：网页核验、出卷、确认 | [docs/exec-plans/active/rational-number-loop.md](docs/exec-plans/active/rational-number-loop.md)。只建 `catalog` 和 `practice` |
| 拍卷、安卓 | 排在第一段网页之后。PRD 的 US-03、AC-03、AC-06 |
| 桌面壳 | [docs/adr/0011-web-and-desktop.md](docs/adr/0011-web-and-desktop.md)。网页在老师电脑上能核验并打开 PDF 之前不做 |
| 改门禁或 `scripts/check*` | 停下问人。读 [docs/gates/HOW-TO-FIX.md](docs/gates/HOW-TO-FIX.md) |
| 补测试 | ARCHITECTURE 的测试策略；对应 AC |
| 第一条功能 | [docs/exec-plans/active/rational-number-loop.md](docs/exec-plans/active/rational-number-loop.md) |

## 命令

当次退出码以终端为准。远端结果看 [Actions 的 check](https://github.com/wisdom-km/k12-qbank/actions)。已经写下来的运行留在 [docs/evidence/](docs/evidence/)。

| 做什么 | 命令 |
| --- | --- |
| 安装 | 无依赖清单，不必安装 |
| 类型检查 | 未落地 |
| 查看骨架状态 | `python scripts/status.py` |
| 文档冒烟 | `python scripts/smoke_docs.py` |
| 边界、相对导入和第一段范围 | `python scripts/check_boundaries.py` |
| 日志规则 | `python scripts/check_logging.py` |
| 文件备份演练 | `python scripts/drill_backup.py`。夹具记录在 `docs/evidence/backup-drill-2026-11-14.md`，不是正式数据 |
| 全量检查 | `powershell -ExecutionPolicy Bypass -File scripts/check.ps1` |
| 干净环境检查 | `bash scripts/check`。GitHub Actions 的 job 名是 `check` |
| 看日志 | 教学服务未落地，没有运行日志。落地后在该次运行的标准输出里搜 `request_id` |

`python scripts/status.py` 不启动教学服务。

## 禁止事项摘要

见 RULES 禁止清单。摘要：不把密钥写入仓库或日志；不吞错；不绕过门禁；不在界面里放行 R1–R6；不把 AI 建议写成老师结论；不扩大已确认范围；不编造测试结果。

## 完成标准

见 RULES 的 DoD。说完成之前跑全量检查，并留下命令和退出码。

## 何时停下问人

规格和方案 1.1 冲突；要改门禁；要花钱调用模型；要动真实学生数据；DEC-01 到 DEC-06 仍空着却必须替机构做决定；缺了端口契约。

## 容易误导

`backend/kernel` 只有日志事件和 Result，没有题库规则。技术栈仍是提议，见 [docs/adr/0010-stack-and-deploy.md](docs/adr/0010-stack-and-deploy.md)。不要把 FastAPI、React 或 Flutter 写成已经选定。

第一段只做浏览器里的核验、出卷和确认，只建 `catalog` 和 `practice`。不要一次建满六个切片，不要建安卓工程，不要打包桌面。Electron 不是退路。ADR 0011 仍是提议。
