# QQ Bot（NapCat + LLM）

基于 [NapCat](https://github.com/NapNeko/NapCatQQ) WebSocket 的 QQ 机器人：私聊与群聊接入大模型对话、联网搜索、Pixiv 配图、记忆与群聊模式等。

---

## 简介

本项目在本地运行 Python 客户端，通过 WebSocket 连接 NapCat，将用户消息送入 `llm_chat` 中的 **LangGraph** 管线（上下文 → Pixiv 节点 → 搜索规划 → 可选 Tavily → 生成 → 收尾），再经 NapCat 将文本与图片发回 QQ。数据与偏好落在项目根目录的 `data/` 下，群成员长期画像可写入 `team_member/`。

---

## 如何与机器人对话

### 私聊

- 向机器人发送的**整段内容**会原样进入对话管线（`chat_agent`），**不需要** @。
- 可直接闲聊、问问题、在句子里使用「记住…」等触发永久记忆（由模型与关键词逻辑解析，见 `project.md`），也可发送以 `/pixiv` 开头的 Pixiv 请求。

### 群聊

- 只有 **`config.json` 里 `chat_group_ids` 包含的群**里，机器人才会收消息并可能回复；其它群会忽略。
- 需要本机器人**生成回复**时，消息中必须带 **@ 本机器人**（与 `config.json` 中的 `bot_qq` 一致）。程序会用 `@` + `bot_qq` 判断是否 @ 机器人并剥离前缀。
- 发消息时**先 @ 再写内容**。程序会剥掉**开头那一次 @**，把余下部分当作用户输入。例如：  
  `@机器人 今天天气怎么样` → 模型看到的是 `今天天气怎么样`。
- **`mode`（`config.json`）**  
  - **`reply`**：只有 @ 了机器人时，才会**记录**这条并**回复**；未 @ 的消息不进入机器人逻辑。  
  - **`listen`**：未 @ 的群消息也会**按用户写入**短期历史（多用户群上下文），但**只有 @ 了机器人**时才会调用大模型并回复。

### 群聊与私聊的差异（与指令有关）

- **`/qby`、`/qby quit`、`/command`、`/parse pic`、`/char list`、`/change`、与恰好为 `/log` 的更新日志**只在**群聊里**按固定规则解析；私聊发这些内容会当作普通话交给大模型，**例外：`/command` 私聊也可用**（整段恰好为 `/command`）。其中 **`/parse pic`、`/char list`、`/change` 必须带前导 `/`**（不要发成 `change`、`parse pic`）。  
- **`/pixiv` 在私聊与群聊**均可使用；群聊里请写成 `@机器人 /pixiv …`，保证去掉 @ 后仍以 `/pixiv` 开头。

---

## 已配置的命令

下列为代码中**显式分支**处理的命令；未列出的内容一律按自然语言交给大模型（含是否联网、是否发图等，由 `chat_agent` 内部决定）。

| 命令 | 场景 | 行为说明 |
|------|------|----------|
| `/command` | **群聊与私聊** | **群聊**去掉 @ 后整段恰好为 `/command`（`fullmatch`）。**私聊**整段恰好为 `/command`。读取并发送项目根目录 **`command.md`** 的全文，不调用大模型；新增指令时请同步维护该文件。 |
| `/log` | 仅**群聊** | 去掉 @ 后，**整段内容恰好等于** `/log` 时，返回 `main.py` 里 `update_log` 拼出的**更新说明文本**，不调用大模型。多一个字都不会命中。 |
| `/qby` 或 `qby` | 仅**群聊** | 去掉 @ 后，**整段**仅含「开启 QBY」指令（`fullmatch`），**只负责开启** QBY 模式；已开启时会提示可发 `/qby quit` 关闭。`qby` 与带斜杠的 `/qby` 等效。 |
| `/qby quit` 或 `qby quit` | 仅**群聊** | 同上，**整段**匹配关闭 QBY。 |
| `/parse pic` | 仅**群聊** | 将 `char_pic` 中缺 `.md` 的条目录入 `char_md`：**含 chara 的 PNG**、或 **同名 `.json`**；纯立绘 PNG / 仅 JPG 需自行放入与 stem 同名的角色 **JSON**（详见 `project.md`）。 |
| `/char list` | 仅**群聊** | 列出当前 `character/char_md` 下的 `.md` 文件名（编号列表）。 |
| `/change …` | 仅**群聊** | **`/change 文件名`** 切换普通模式叠用的人物卡（可省略 `.md`）；**`/change default`** 清除持久化并恢复为 **`config.json` 的 `default_character`**（该项为空则不加人物卡）。 |
| `/pixiv` … | **私聊与群聊** | 在**去掉 @ 之后**（群聊）或**整段消息**（私聊），**以** `/pixiv` 开头（不区分大小写），后面可接日/周/月榜、作品 id、标签等，见 `project.md`；会走 Pixiv 下载，**不会**与 Tavily 联网搜索混用，其余文字仍由大模型组织回复。 |

**注意：** QBY、`/log` 与人物卡相关指令（`/parse pic`、`/char list`、`/change`）的解析要求「去掉 @ 以后」**只有命令本身**（`fullmatch` 允许的空白除外），不能在同一条里写成 `@机器人 /parse pic 随便聊聊」，否则会整句交给大模型。**人物卡三条必须以 `/` 开头**（`/parse pic`、`/char list`、`/change`），写成 `change xxx` 不会命中。**`/command` 在私聊也可使用**（整段仅为 `/command`）。Pixiv 则允许 `/pixiv` 后接任意说明文字。

---

## 基本功能

以下能力在代码中均有实现，按模块归类方便你对照 `project.md` 深入阅读。

| 类别 | 功能说明 |
|------|------------|
| **连接与入站** | 通过 `config.json` 中的 `ws_url`、`access_token` 连接 NapCat；处理私聊与群聊事件。 |
| **大模型对话** | 使用 LangChain `init_chat_model` 与可配置的 Base URL / 模型名（见环境变量）生成回复。 |
| **群聊触发** | 群内需 **@ 机器人**（`config.json` 的 `bot_qq`）才走对话与指令；可配置仅响应指定群。 |
| **群聊模式** | `config.json` 的 `mode`：`reply` 仅 @ 时记录并回复；`listen` 全群记录、仅 @ 时回复。`message_num` 控制群上下文注入条数。 |
| **联网搜索** | 由 LLM 判断是否需要搜索，在 **Tavily** 中检索，结果注入提示词（需 `Tavily_APIKEY`）。 |
| **Pixiv 配图** | 消息以 **`/pixiv`** 开头时解析参数并下载配图（Selenium + 本机 Chrome）；与闲聊/联网意图分离；正文仍走大模型。 |
| **短期聊天历史** | 多轮对话写入 `data/chat_history.json`；进模型条数有上限，超限会触发清理与总结（见 `project.md`）。 |
| **永久记忆** | 用户说「记住」等关键词时写入 `data/permanent_memories.json`，后续回复可带入。 |
| **用户偏好** | 话题、表情等偏好存 `data/user_preferences.json`，用于丰富提示。 |
| **性格 / 群友蒸馏** | 历史触顶时 LLM 总结并写入 `data/user_personality.json` 与 `team_member/{user_id}.md`。 |
| **QBY 模式** | 群聊 @ 后发送 **`/qby`** 或 `qby` 开启、**`/qby quit`** 或 `qby quit` 关闭；使用独立人设与 `team_member/qby.md` 口癖备忘（与「普通模式」二选一）。 |
| **人物卡** | PNG / 同名 JSON / JPG 立绘配 JSON 放 `character/char_pic`，**`/parse pic`** 生成 `character/char_md`；**`/char list`**、**`/change`** 选用；**仅普通模式**与 `.env` 的 `system_prompt` 叠用，详见 `project.md`。 |
| **群聊指令** | 见上文 **「已配置的命令」**（如 **`/log`** 推送 `update_log`）。 |
| **表情与随机表情** | 按关键词从本地表情库选图；另有概率随机发表情（见 `finalize` 与主流程返回）。 |
| **活跃暖场** | `check_activity_level_group_ids` 配置的群在消息数达到配置时会触发 `check_activity_level` 中的暖场/互动逻辑（与 `chat_agent` 衔接）。 |
| **内容安全** | 对第三方 API 返回的审核类错误有降级重试与简短兜底文案。 |

更细的管线图、条数与路径说明以 **`project.md`** 为准。

---

## 配置：config.json

从 `src/config_example.json` 复制为 **`src/config.json`**（与 `main.py` 同目录）并填写。

| 字段 | 说明 |
|------|------|
| `ws_url` | NapCat 正向 WebSocket 地址，例如 `ws://127.0.0.1:端口号/路径`（以你的 NapCat 配置为准）。 |
| `access_token` | 与 NapCat 里为 WebSocket 配置的 Token 一致。 |
| `bot_qq` | **必填。** 本机器人登录的 QQ 号（数字）；用于识别「群消息里是否 @ 了本机器人」、去掉开头的 `@`。 |
| `chat_group_ids` | 需要机器人响应的**群号**列表；仅在这些群内处理 @ 与（按模式的）历史。 |
| `check_activity_level_group_ids` | 需要参与**活跃暖场/计数**的群号列表。 |
| `mode` | `reply` 或 `listen`，含义见上表。 |
| `message_num` | 群聊拼进上下文的**消息条数**（会参与 `llm_chat` 中的 `CONTEXT_MESSAGE_NUM` 等逻辑，见 `set_group_chat_config`）。 |
| `default_character` | **可选。** `character/char_md` 下的文件名（可省略 `.md`）；进程启动时若**没有** `data/active_character.json` 则加载该人物卡。**空字符串**表示不默认加载人物卡。误写为 `defult_character` 时也会被读取。 |

---

## 配置：cookie.json（Pixiv 下载）

Pixiv 相关下载依赖浏览器请求头。将 **`src/cookie_example.json`** 复制为 **`src/cookie.json`**，在登录 Pixiv 后的浏览器中同步填写：

| 字段 | 说明 |
|------|------|
| `User-Agent` | 与常用浏览器一致即可。 |
| `cookie` | 登录后站点的 Cookie 串（需自行从浏览器导出，注意保密）。 |
| `Referer` | 保持示例中 `https://www.pixiv.net/` 或按站点要求填写。 |

未配置或配置错误时，Pixiv 模块可能无法加载或下载失败，其它聊天功能一般仍可使用。

---

## 配置：.env（与 `src/const.py` 同目录）

在 **`src/.env`** 中配置（`const.py` 会固定从该文件所在目录加载，与当前工作目录无关）。

### 大模型与对话（`llm_chat` 使用 `init_chat_model`）

| 变量 | 说明 |
|------|------|
| `API_KEY` | 大模型 API 密钥。若值不是以 `sk-` 开头，会被视为**环境变量名**，再从环境中读取实际密钥。 |
| `MODEL_NAME` | 模型名，如硅基流动等 OpenAI 兼容服务上的 ID。 |
| `MODEL_PROVIDER` | LangChain 所识别的提供方，请与你的 Base URL 一致（如 `openai` 等）。 |
| `BASE_URL` | 兼容 OpenAI 的 API 根地址，例如 `https://api.siliconflow.cn/v1`。 |
| `TEMPERATURE` | 采样温度，可选。 |
| `SYSTEM_PROMPT` 或 `system_prompt` | 普通模式主系统提示；可含 `{user_input}` 等占位符，空则用代码内默认。 |
| `MAX_MESSAGES` | 单用户短期历史上限相关（与 `llm_chat` 中 `MAX_HISTORY_PER_USER` 等逻辑对应），默认 100。 |

### 联网搜索

| 变量 | 说明 |
|------|------|
| `Tavily_APIKEY` | Tavily Search API，未配置时联网分支可能无法正常工作。 |

### QBY 模式

| 变量 | 说明 |
|------|------|
| `qby_model` | `true` / `false` 等，进程启动时是否默认进入 QBY；群聊里仍可用 `/qby` 切换。 |
| `QBY_SYSTEM_PROMPT` 或 `qby_system_prompt` | 仅 QBY 开启时的人设主文案。 |

### 其它

| 变量 | 说明 |
|------|------|
| `DeepSeek_APIKEY` | 代码中预留读取，按你后续接法使用。 |
| `SILICONFLOW_APIKEY` | 在 `const` 中读取；若你只用 `API_KEY` 指向其它网关，可忽略。 |

实际键名以 `src/const.py` 为准；`project.md` 中的表若与 `const.py` 不一致，**以 `const.py` 为准**。

---

## Quickstart

1. **环境**  
   - Python 3.10+（建议）；安装后确认终端里 `python --version` 可用。  
   - 安装 [Google Chrome](https://www.google.com/chrome/)（Pixiv 使用无头 Chrome + ChromeDriver，首次运行会自动拉取驱动）。

2. **克隆或解压项目后，进入项目根目录**（含 `src`、`requirements.txt`、`run_qqbot.bat` 的那一层）。

3. **（推荐）创建虚拟环境**（在项目根目录执行）

   ```powershell
   python -m venv .venv
   ```

   - **PowerShell** 激活（执行策略若拦截，可先 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`）：  
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
   - **命令提示符 cmd**：  
     ```bat
     .venv\Scripts\activate.bat
     ```

   激活后提示符前会出现 `(.venv)`；此后 `pip`、`python` 都指向该环境。也可用 `python -m venv venv` 在项目根得到 `venv` 文件夹（与 `.venv` 二选一即可）。若不使用虚拟环境，也可跳过本步，`run_qqbot.bat` 会回退到系统 PATH 里的 `python`。

4. **安装依赖**（建议在已激活的 `.venv` 下、仍在项目根目录执行）

   ```bash
   pip install -r requirements.txt
   ```

   `requirements.txt` 与 `src` 中的第三方库 import 对应；若遇版本冲突，以能成功启动机器人为准。

5. **配置文件**（详见上文各节，此处为最小清单）

   - 从 `src/config_example.json` 复制为 `src/config.json`，填写 NapCat 的 `ws_url`、`access_token`、`bot_qq`、`chat_group_ids` 等。  
   - 新建 `src/.env`，至少配置 `API_KEY`、`MODEL_NAME`、`MODEL_PROVIDER`、`BASE_URL`；需要联网时配置 `Tavily_APIKEY`；需要 QBY 默认开启或人设时配置 `qby_model`、`QBY_SYSTEM_PROMPT`。  
   - （可选）Pixiv：复制并填写 `src/cookie.json`。

6. **启动**  
   **直接双击或在资源管理器中运行项目根目录下的 `run_qqbot.bat`。**  
   脚本会切换到项目根目录（与 `run_qqbot.bat` 同级），按顺序查找 **`.\.venv\Scripts\python.exe`** → **`.\venv\Scripts\python.exe`** → **`.\env\Scripts\python.exe`**，找到则用该解释器运行 `src\main.py`，都找不到才使用系统 PATH 里的 `python`。请把虚拟环境建在项目根目录，否则双击启动仍会用系统 Python。

   等价手动命令（在项目根目录、且已激活 `.venv` 时）：

   ```bash
   python src\main.py
   ```

   看到日志中 WebSocket 连接成功即表示与 NapCat 已连通。之后按上文 **「如何与机器人对话」** 在私聊或群内 @ 后测试；命令列表见 **「已配置的命令」**。

更完整的协议字段、数据文件与记忆/历史说明，请继续阅读 [`project.md`](project.md)。
