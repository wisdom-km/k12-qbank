# ADR 0012 采纳第一段的服务端和网页技术栈

## 背景

ADR 0010 把 FastAPI、PostgreSQL、React、Flutter 留作候选，并写明选定其中一项时要另写 ADR，取代对应句子。第一段要在 `catalog` 和 `practice` 里用合成数据验证出卷和确认。检查脚本已经是 Python。

## 选项

1. 继续把四项都留作候选，业务代码不绑定任何框架。
2. 采纳 Python 3.12、FastAPI、PostgreSQL、React（网页优先）。安卓界面、部署地点、模型供应商仍不在这次决定里。

## 决定

选 2。

- 服务端语言是 Python 3.12，与 `.python-version` 和现有检查脚本一致，第一条闭环可以立刻用标准库和假端口验证。
- HTTP 入口以后用 FastAPI。领域和用例不导入它。
- 关系数据库产品是 PostgreSQL。这一段还没有数据库，也没有迁移。第一次把数据写入 PostgreSQL 时，同一改动里要有可回退的迁移。
- 网页用 React。这一段不创建 `apps/web`。创建时只通过 HTTPS 调用用例，不导入 `backend`。
- 不并行引入第二套网页框架。Vue 不再作为第一套网页的候选。
- 安卓界面仍未选定。Flutter 和 React Native 仍是候选，本条不取代 ADR 0010 里的那一句。
- 部署地点、模型供应商、备份数字仍按 ADR 0010，等机构确认。不在本条里代填 DEC-01 到 DEC-06。

这次还不安装 FastAPI、数据库驱动或 React。仓库里因此仍没有依赖清单，M-09 仍是 N/A。第一次加入清单时，同一改动里把 `scripts/check.conf` 的 `APP_DIRS` 写成清单所在目录，并把 `INSTALL_CMD` 写成锁定安装命令。

## 后果

新的 HTTP、数据库和网页代码按上面的选择进入。领域规则保持与框架无关，所以换部署或换网页打包方式时不改 R1、R2、R3、R5。

`scripts/check_boundaries.py` 仍拒绝 domain 和 application 导入 FastAPI、SQLAlchemy 等框架。这与本决定一致：框架只放在以后的适配器或 HTTP 入口。

## 状态

采纳。2026-11-14。取代 ADR 0010 里关于后端语言、网页框架和关系数据库产品的候选句子。
