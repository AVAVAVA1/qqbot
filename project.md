# QQ Bot 项目说明

重要变更（重构、新功能、数据路径）应同步更新本文档（见 `.cursor/rules/karpathy-guidelines.mdc`）。

## 入口与依赖

- **`src/main.py`**：连接 NapCat WebSocket，处理私聊/群聊；群内消息中出现 **`@` + `config.json` 的 `bot_qq`** 时处理指令与对话。**`/command`**（群聊需 @；私聊整段为 `/command`）读取项目根 **`command.md`** 作为指令说明回复。
- **`command.md`**（项目根，与 `README.md` 同级）：显式指令列表与行为说明；**与代码中分支同步维护**，由 `/command` 输出。
- **`src/llm_chat.py`**：大模型对话管线（LangGraph）、搜索、Pixiv、记忆与偏好等。

## LangGraph 对话管线

`chat_agent()` 编译的图大致为：

```
context → pixiv → search_plan → [需要联网?] ──是──→ tavily → generate → finalize → END
                                    └──否──→ generate ──────────────┘
```

- **`context`**：解析永久记忆关键词、拼 `history_context` / 用户偏好摘要 / 永久记忆文本；若消息以 **`/pixiv`** 开头则解析下载参数（不下载），并把**去掉命令前缀后的正文**写入 `user_input_for_llm` 供后续 LLM 使用。普通消息不触发 Pixiv，避免与闲聊、联网意图混用。
- **`pixiv`**：仅当 `/pixiv` 后解析出下载任务时执行下载，结果写入 `pixiv_images`（不再在此处写死「已找到 N 张图」类 `final_response`）。
- **`search_plan`**：对 `user_input_for_llm` 调用 `analyze_search_need`（LLM JSON）决定是否搜索及查询参数；**`/pixiv` 命令下固定不联网**，与 Pixiv 下载分流。
- **`tavily`**：线程池中调用 Tavily `web_search`，写入 `web_results`。
- **`generate`**：组装系统提示（含可选 QBY skill）、调用 LLM、内容审核降级、「记住了」前缀。
- **`finalize`**：按关键词选表情图、更新话题偏好。

对外接口仍为 **`chat_agent(user_input, user_id=..., group_id=...)`**，返回 `response`、`emoji_path`、`memory_saved`、`pixiv_images`。

## 配置与环境变量（`src/.env`）

由 **`src/const.py`** 从与 `const.py` 同目录的 **`.env`** 加载（不依赖当前工作目录）。

| 变量 | 作用 |
|------|------|
| `SILICONFLOW_APIKEY` | 对话与搜索路由所用 LLM（见 `llm_chat` 内 `init_chat_model`） |
| `Tavily_APIKEY` | 联网搜索 |
| `DeepSeek_APIKEY` | 预留 |
| `SYSTEM_PROMPT` / `system_prompt` | 聊天主系统提示模板（含 `{user_input}` 等占位符）；空则用代码内默认 |
| `qby_model` | QBY 模式**进程启动时的默认**（`true`/`false`）；运行中见下文显式指令 |
| `qby_system_prompt` / `QBY_SYSTEM_PROMPT` | **仅 QBY 开启时**作为人设主文案（见下）；可与 `qby.md` 搭配 |

## 系统提示与 QBY 模式

两种模式**互斥**，不在同一次 `llm.ainvoke` 里混用 `system_prompt` 与 `qby_system_prompt`：

- **普通模式（`qby_mode_active == False`）**：主模板来自 **`.env` 的 `system_prompt`**（加载为 `const.chat_system_prompt`，缓存在 `system_prompts["chat"]`；空则用代码内 `_DEFAULT_CHAT_SYSTEM_PROMPT`）。若已通过 **`/change`** 选用人物卡，则在格式化后的模板后追加 **`character/char_md` 中对应正文**（「人物卡人格」区块）。末尾追加 **`_NORMAL_MODE_LOCK`**。内容审核降级时同样在格式化后追加当前人物卡与模式锁。
- **QBY 模式**：仅用 **`const.qby_system_prompt`** + **`_QBY_ROLE_RULES`** + **`_QBY_CONTEXT_TEMPLATE`** + 可选 **`team_member/qby.md`**（口癖轻量备忘，**非**剧本；唯一加载路径）。**不**读取 `system_prompts["chat"]` / oguri 模板。

开关：全局 **`qby_mode_active`**，默认 `const.qby_model_default`。群聊在 **`@` + `bot_qq`（来自 `config.json`）** 后（固定语义，**不**翻转）：

- **`/qby`** 或 **`qby`**：**仅开启** QBY（已在开则提示无需重复）；
- **`/qby quit`**：**仅关闭** QBY（兼容 **`qby quit`**）；已关则提示当前不在 QBY。
- **`/parse pic`**、**`/char list`**、**`/change`**：人物卡相关，见下文「人物卡」。

解析见 **`llm_chat.parse_group_qby_command`**（QBY，大小写不敏感，首尾可空白）；人物卡见 **`try_handle_group_character_commands`**。

## 数据与生成文件（项目根目录 `data/`）

| 路径 | 内容 |
|------|------|
| `data/chat_history.json` | 短期多轮消息 |
| `data/user_preferences.json` | 话题/表情偏好等 |
| `data/permanent_memories.json` | 「记住」类永久记忆 |
| `data/user_personality.json` | 聊天超限清理时的性格总结归档 |
| `data/active_character.json` | 当前选用的人物卡文件名（`character/char_md/*.md`）；**存在时优先于** `config.json` 的 `default_character`。`/change default` 会删除此文件并按 `default_character` 重新加载。 |

## 人物卡（SillyTavern PNG → Markdown）

- **源文件**：`char_pic` 下 **PNG**（须为 SillyTavern 等导出的**内嵌 chara** 角色卡，普通立绘 PNG 无法解析）、同名的 **.json** 角色数据；**JPG / WebP 等仅立绘时可配同名 .json** 一并解析（WebP 常见于 Pixiv `master1200` 导出）。
- **离线解析**：在 `src` 下执行 `python character_cards.py`；可为 **内嵌 chara 的 PNG**、**`.json` 角色文件**生成 md；纯立绘 PNG、仅 JPG/WebP 需 **同名 `.json`**（从 SillyTavern 等导出）。
- **`config.json` → `default_character`**（可选）：仅含 **`character/char_md` 下的文件名**（不要路径；可省略 `.md`）。**留空**表示启动时不默认加载人物卡。启动时若已有 **`data/active_character.json`**（例如曾用 `/change` 选过卡），则**以持久化为准**，忽略该项直至你发 **`/change default`**。
  - 兼容历史拼写错误键名 **`defult_character`**。
- **仅群聊、需 `@` 机器人**（与 `/qby`、`/log` 同类）。**`/parse pic`、`/char list`、`/change` 必须以 `/` 开头**；写成 `change`、`parse pic` 等不会命中。
  - **`/parse pic`**：增量解析（只处理缺 md 的图片），并回复简要报告。
  - **`/char list`**：列出 `char_md` 下的 `.md` 文件名（编号列表）。
  - **`/change 文件名`**：切换当前人物卡（可省略 `.md`）；**`/change default`**：去掉持久化并按 **`default_character`** 恢复（空则不加人物卡）。
- **与普通模式**：普通模式下 LLM 提示词为 **`.env` 的 `system_prompt` 模板（原则）** + **当前人物卡正文（个性）** + 模式锁；**QBY 模式**仍仅用 `qby_system_prompt` + `qby.md`，**不**叠人物卡。

解析逻辑见 **`src/character_cards.py`**；选用状态见 **`main.init_character_state_from_bot_config`** 与 **`llm_chat.try_handle_group_character_commands`**。

## 群成员蒸馏档案（`team_member/`）

当某用户短期聊天达到条数上限触发 **`clear_user_history`** 时，除写入 `user_personality.json` 外，会覆盖写入 **`team_member/{user_id}.md`**（与 `data/` 同级的项目根目录下），汇总偏好统计与对话蒸馏的说话方式/画像。**LLM 性格总结仅使用 `chat_history` 里该用户 `role=user` 的发言，不包含 `assistant` 回复。**

---

## 聊天记录管理（短期历史）

本 QQ bot 的「聊天记录」指**短期对话历史**（用户与助手的多轮消息），与**永久记忆**、**用户偏好**分开存储。

### 存储位置与格式

- **文件路径**：项目根目录下的 `data/chat_history.json`（由 `llm_chat` 中的 `DATA_FOLDER` 决定）。
- **数据结构**：JSON 数组，每条记录包含：
  - `user_id`：QQ 用户 ID
  - `message`：文本内容
  - `role`：`"user"` 或 `"assistant"`
  - `timestamp`：ISO 时间字符串

进程启动时会执行 `load_chat_history()` 读入内存；之后每次写入都会 `save_chat_history()` 整文件落盘。

### 写入入口

- `main.py` 在收到用户消息后调用 `add_to_history(user_id, content, "user")`；模型回复后再 `add_to_history(..., "assistant")`。

### 条数上限与自动清理

- 常量 **`MAX_HISTORY_PER_USER = 40`**：按**单用户**统计 `chat_history` 中该 `user_id` 的消息条数（用户消息与助手回复都计入）。
- 当某用户已有 ≥40 条记录、再次 `add_to_history` 时，会先对该用户调用 **`clear_user_history(user_id)`**：
  - 将该用户从 `chat_history` 中全部移除并保存；
  - 在后台用当前这批消息做一次 **LLM 性格/兴趣等总结**，结果追加写入 `data/user_personality.json`；
  - 并写入 **`team_member/{user_id}.md`**（见上文）。

因此：短期历史最多保留每个用户 40 条；超出时整段清空并触发总结归档，而不是只删最旧的一条。

### 模型上下文里用多少历史

- 生成回复时通过 **`get_user_recent_history(user_id, limit=7)`** 取该用户**最近 7 条**消息，拼成 `history_context` 填入系统提示词（时间顺序在拼接时会再反转，保证对话顺序正确）。

也就是说：**磁盘上**最多 40 条/用户，**单次请求里**只带最近 7 条进 prompt。

### 其它相关能力（非 chat_history.json）

- **永久记忆**：用户话里出现「记住」「记下来」等关键词时，会解析内容写入 `data/permanent_memories.json`；回复组装时最多取该用户最近 **5 条**永久记忆拼进提示词。
- **用户偏好**：话题、表情偏好等存在 `data/user_preferences.json`，用于 `user_pref_info`，不是逐条聊天日志。
- **历史检索**：`search_chat_history(query, user_id?, limit=10)` 在内存中的 `chat_history` 上做子串匹配（从新到旧），供工具或逻辑查询使用。

### 小结

| 项目 | 说明 |
|------|------|
| 持久化文件 | `data/chat_history.json` |
| 单用户上限 | 40 条（user+assistant 合计） |
| 超限行为 | 清空该用户短期历史 + `user_personality.json` + `team_member/{user_id}.md` |
| 进模型上下文 | 最近 7 条 |
| 与永久记忆 | `permanent_memories.json`，关键词触发，与聊天条数上限无关 |

## 群聊指令备忘

（以下 `@机器人` 指 **`@` + `config.json` 的 `bot_qq`**）

- **`@机器人 /log`**：推送内置更新日志文本。
- **`@机器人 /qby`**：开启 QBY；**`@机器人 /qby quit`**（或 **`qby quit`**）关闭。见上文「系统提示与 QBY」。
