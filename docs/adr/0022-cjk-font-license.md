# ADR 0022 中文字体许可证

状态：proposed

## 背景

合成 PDF 用标准库 Helvetica，编码是 WinAnsi。写不出的字符返回 `not_rendered`。有一项要求换成 Noto Sans CJK 或同等字体，并先确认许可证。

Noto Sans CJK 发布包的许可证文件写明 SIL Open Font License, Version 1.1。核对的是 notofonts/noto-cjk 标签 `NotoSansV2.001` 的 `LICENSE` 开头两句。许可证正文不抄进本仓库。

本仓库允许 MIT、BSD、Apache-2.0。名单以外是待人审。OFL 1.1 不在这份名单里。

## 选项

1. 现在把 Noto 放进仓库，并改 `pdf_page.py`。
2. 停住。不加入字体，不改渲染。等人决定能不能接受 OFL，或另指定一份在允许名单里的字体。

## 决定

选 2。需要人工决定。

不加入字体文件。不改 `backend/practice/adapters/pdf_page.py`。不编一份含「解：」的样张。

## 后果

中文和公式超出 WinAnsi 时，卷仍留在待渲染，原因仍是 `not_rendered`。实现矩阵不改。

## 状态

提议。2026-11-18。许可证不在允许名单里，等人决定。不取代现有的 Helvetica 合成页。
