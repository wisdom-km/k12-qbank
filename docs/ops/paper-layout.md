# 卷面版式参数

新卷按题目高度往下排。参数在 `backend/practice/domain/paper_layout.json`。要换一份，把 `K12_PAPER_LAYOUT_PATH` 指到另一份 JSON。空着就用仓库里的这一份。

已发出的卷用出卷时抄进 `papers.layout_params` 和 `practice_item_box` 的坐标。改这个文件，或改环境变量指向的文件，都不移动那些卷。下一份新卷才用新参数。

`slots_per_page` 为 1 或 4 的旧卷不读这份参数，仍按槽位打开。

## 参数

单位是 PDF 点。1 点 = 2.54 / 72 cm，约 0.0353 cm。A4 是 595 × 842 点。

| 字段 | 默认 | 约合 | 下限 |
| --- | --- | --- | --- |
| page_width | 595 | 21.0 cm | 不小于 0 |
| page_height | 842 | 29.7 cm | 不小于 0 |
| margin_left / margin_right | 48 | 1.69 cm | 不小于 0 |
| margin_top | 36 | 1.27 cm | 不小于 0 |
| margin_bottom | 42 | 1.48 cm | 不小于 0 |
| font_size | 11 | 0.39 cm | 不小于 0 |
| line_height | 16 | 0.56 cm | 不小于 font_size |
| header_x | 48 | 距左 1.69 cm | 不小于 0 |
| header_y | 812 | 基线距底 28.6 cm | 不小于 0 |
| header_font_size | 10 | 0.35 cm | 不小于 9 pt |
| qr_module | 1.8 | 0.0635 cm | 不小于 1.7 pt |
| qr_quiet_modules | 4 | 静区每边 0.25 cm | 整数，不少于 4 |
| mark_size | 14 | 0.49 cm | 不小于 12 pt |
| mark_inset | 16 | 0.56 cm | 不小于 0 |
| letter_width | 36 | 1.27 cm | 不小于 28 pt |
| letter_height | 24 | 0.85 cm | 不小于 20 pt |
| blank_width | 36 | 1.27 cm | 不小于 0 |
| blank_height | 20 | 0.71 cm | 不小于 0 |
| blank_gap | 8 | 0.28 cm | 不小于 0 |
| small_height | 80 | 2.82 cm | 不小于 0 |
| medium_height | 160 | 5.64 cm | 不小于 0 |
| large_height | 300 | 10.58 cm | 不小于 0 |
| item_gap | 12 | 0.42 cm | 不小于 0 |

二维码固定 29 × 29 个模块。默认码面 52.2 点，约 1.84 cm。加上四周各 4 个模块的静区，整块 66.6 点，约 2.35 cm。默认放在右上角页边之内：原点 x = 487.6 点，y = 746.6 点。页眉在左上角，和这块不重叠。

`letter` 是选择题字母框，画在题号那一行的右侧。`blanks` 是填空小框，个数等于题干里连续下划线（至少两个 `_`）的段数；一段都没有时仍画一个。`small`、`medium`、`large` 是通栏大框。`full` 从题干下沿占到正文区底边，高度不是表里的固定数。

未列出的字段会被拒绝。布尔值不当成数字。

## 公式

公式的字号跟随上面的 `font_size`。流式新卷默认 11。槽位卷和单题旧版式里的公式用 12，不读这份 JSON。

下面的比例写在 `backend/practice/domain/formula.py`，不是本文件的字段。多写进 JSON 会被拒绝。

| 名字 | 值 | 含义 |
| --- | --- | --- |
| SCRIPT_SCALE | 0.7 | 上标和下标相对正文字号 |
| SUPERSCRIPT_RISE | 0.45 | 上标基线相对正文基线上移，乘字号 |
| SUBSCRIPT_DROP | 0.22 | 下标基线相对正文基线下移，乘字号 |
| FRACTION_GAP | 0.16 | 分子、分母到分数线的间距，乘字号 |
| FRACTION_AXIS | 0.22 | 分数线相对正文基线上移，乘字号 |

一行里有分数时，这一行的高度取这一行里最高的一块，且不小于 `line_height`。下一道题从这个高度之后再排。一个公式不拆到两行。比整行还宽时出卷返回 `formula_too_wide`。

## 校验

production：文件读不出、不是对象、缺字段、多字段、不是数字、或低于下限，进程启动失败。标准输出一条 `startup_refused`，`outcome` 是 `layout_invalid:` 加字段名。说明写在标准错误，并写出是哪个字段。

development：同样的文件不阻止启动。出卷时返回 `layout_invalid`，说明里有字段名。卷不会写入。

一道题的题干加答题区超过一整页正文区：出卷返回 `item_too_long`，说明是第几题、哪个 `question_version_id`。没有任何一行被丢掉。卷不会写入。

## 换一份参数

1. 复制 `backend/practice/domain/paper_layout.json`。
2. 只改要试的数字，保持字段名不变。
3. 设置 `K12_PAPER_LAYOUT_PATH` 为这份文件的绝对路径。
4. 重新启动进程。production 会在启动时检查；development 在下一次出卷时检查。

## 实测微调

1. 用当前参数出一份卷，打印。
2. 用手机拍这一页。
3. 看右上角二维码能不能扫出卷号和页码。扫不出时，先把 `qr_module` 加大，仍不要小于 1.7。静区保持至少 4 个模块。
4. 看 `letter` 框够不够写一个字母，大框够不够写步骤。不够就加大对应的宽或高，不要低于表里的下限。
5. 页眉若和二维码挤在一起，改 `header_x`、`header_y` 或页边距，再出一份新卷。
6. 已发出的卷不要重出。改完参数后出的下一份才用新数字。对照时打开两份 PDF，看旧卷的框没有跟着动。
