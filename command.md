# QQ Bot · 指令速查

完整用法与匹配规则见 **README.md**。下表为显式指令及作用。

---

## 私聊

`/command`  
　→ 发送本列表全文

`/pixiv` + 可选参数  
　→ Pixiv 配图下载；可与说明同条；回复仍走大模型；不触发联网搜索。

---

## 群聊（配置群 + @ 机器人）

> **去 @ 后整段仅含指令**（首尾可空白）；勿与闲聊同条，否则交给大模型。`/parse pic`、`/char list`、`/change` **必须带 /**。细则见 README。

`/command`  
　→ 同上，发出本列表。

`/log`  
　→ 内置更新记录，不调用大模型。

`/qby`　或　`qby`  
　→ 开启 QBY 模式。

`/qby quit`　或　`qby quit`  
　→ 关闭 QBY。

`/parse pic`  
　→ `char_pic` 缺 md 的条目写入 `char_md`（ST 式 PNG / 同名 JSON 等）。

`/char list`  
　→ 列出 `char_md` 下 `.md` 文件（编号）。

`/change` + 文件名或 `default`  
　→ 切换人物卡；`/change default` 按 `config.json` 的 `default_character` 恢复。

`/pixiv` + 可选参数  
　→ 去 @ 后仍以 `/pixiv` 开头；其余同私聊。

---

## 其它

未列出的内容走对话模型，无固定斜杠指令。