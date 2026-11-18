# ADR 0027 口令哈希

状态：accepted

## 背景

管理员和老师的口令要能校验，不能可逆。依赖需要在允许的许可证里，并钉死版本。

## 选项

1. 标准库哈希。没有抗 GPU 的内存成本。
2. `argon2-cffi` 的 argon2id。许可证是 MIT。
3. 另选 bcrypt 或 scrypt。

## 决定

选 2。参数固定，不按环境改变：

- 算法：argon2id
- `time_cost=3`
- `memory_cost=65536`
- `parallelism=2`
- salt 16 字节
- 哈希长度 32 字节

`verify` 成功后，若 `check_needs_rehash` 为真，立刻用同一组参数重写哈希。

口令规则：至少 10 个字符，并且同时含字母和数字。用户名是 3 到 32 个字符，字符集 `[a-z0-9._-]`。

## 后果

`requirements.txt` 增加 `argon2-cffi` 及其绑定包，版本用 `==` 钉死。领域层不导入该包。哈希只在适配器里做。

## 状态

采纳。2026-11-18。用户已预批准这个依赖。
