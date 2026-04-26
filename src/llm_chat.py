import json
import os
import random
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict, List, Optional, Dict, Any
from langgraph.graph import StateGraph, END
from langchain.chat_models import init_chat_model
from loguru import logger
import const

_executor = ThreadPoolExecutor(max_workers=2)

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from tavily import TavilyClient

chrome_options = Options()
chrome_options.add_argument('--headless=new')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--no-sandbox')

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)  # driver here

# 延迟导入，避免启动时依赖 cookie.json
download_by_rank = None
download_by_label = None
download_by_special_page = None

try:
    import download_by_rank
    import download_by_label
    import download_by_special_page
    logger.info("Pixiv 下载模块加载成功")
except ImportError as e:
    logger.warning(f"Pixiv 下载模块加载失败（可能缺少 cookie.json）: {e}")
    download_by_rank = None
    download_by_label = None
    download_by_special_page = None


def download_pic_pixiv_rank_label_page(page_url, mode, pic_folder, pic_num=2):
    """

    :param page_url: 搜索的关键词，mode1是根据排行榜['daily', 'weekly', 'monthly', 'rookie'].mode2是标签名.mode3是pid数字
    :param mode: 根据需求选择合适的mode
    :param pic_folder: 默认为pixiv
    :param pic_num: 请求图片的数目
    :return: 需发送的图片的地址为array
    """
    if not (download_by_rank and download_by_label and download_by_special_page):
        logger.warning("Pixiv 下载模块未加载，跳过图片下载")
        return []

    if pic_folder == '' or pic_folder is None:
        pic_folder = 'pixiv'

    pic_folder = 'pixiv'
    page_url = page_url
    path_ls = []
    if mode == '1' or mode == 1:
        path_ls += download_by_rank.download_pic_from_ranking_page(page_url, driver, pic_folder, pic_num)
    if mode == '2' or mode == 2:
        path_ls += download_by_label.download_pic_from_label(page_url, driver, pic_folder, pic_num)
    if mode == '3' or mode == 3:
        path_ls += download_by_special_page.download_pic_from_single_page(page_url, driver, pic_folder, pic_num)

    return path_ls


llm = init_chat_model(
    model=const.model_name,  #Qwen/Qwen3-8B   THUDM/GLM-Z1-9B-0414
    temperature=const.temperature,
    model_provider=const.model_provider,
    base_url=const.base_url, #https://api.deepseek.com   https://api.siliconflow.cn/v1
    api_key=const.api_key,
)

PIC_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), "source", "pic")
DATA_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
TEAM_MEMBER_FOLDER = os.path.join(os.path.dirname(DATA_FOLDER), "team_member")

os.makedirs(DATA_FOLDER, exist_ok=True)
os.makedirs(TEAM_MEMBER_FOLDER, exist_ok=True)

MAX_HISTORY_PER_USER = const.max_messages

# 群聊：由 main 在加载 config 后调用 set_group_chat_config 写入
# mode "reply" = 仅 @ 时记录并回复；"listen" = 全群记录，仅 @ 回复
GROUP_MODE: str = "reply"
CONTEXT_MESSAGE_NUM: int = 7


def set_group_chat_config(mode: Optional[str] = None, message_num: Any = None) -> str:
    """根据 config.json 设置群聊模式与注入上下文的条数。返回归一化后的 mode。"""
    global GROUP_MODE, CONTEXT_MESSAGE_NUM
    m = (mode or "reply").strip().lower()
    if m not in ("reply", "listen"):
        logger.warning(
            f"config mode 无效 {mode!r}，仅支持 listen / reply，已使用 reply"
        )
        m = "reply"
    GROUP_MODE = m
    try:
        n = int(message_num) if message_num is not None else 7
        if n < 1:
            n = 7
    except (TypeError, ValueError):
        n = 7
    CONTEXT_MESSAGE_NUM = n
    logger.info(f"群聊配置: mode={GROUP_MODE}，上下文联条数={CONTEXT_MESSAGE_NUM}")
    return m


class UserPreference(TypedDict):
    user_id: int
    emoji_preferences: Dict[str, int]
    topic_preferences: List[str]
    last_interaction: str


class ChatMessage(TypedDict):
    user_id: int
    message: str
    role: str
    timestamp: str


class PermanentMemory(TypedDict):
    user_id: int
    content: str
    timestamp: str


user_preferences: Dict[int, UserPreference] = {}
chat_history: List[ChatMessage] = []
permanent_memories: Dict[int, List[PermanentMemory]] = {}

_DEFAULT_CHAT_SYSTEM_PROMPT = """你是一个友好、智能的聊天助手。
    但再聊天中你的名字叫oguri，是一名可爱的赛马娘

用户信息: 用户ID {user_id}
用户偏好: {user_pref_info}

永久记忆:
{permanent_memory}

最近对话历史:
{history_context}

网络搜索结果:
{web_results}

用户说: {user_input}

请直接回复用户，保持对话自然流畅。要求:
1. 回复简洁友好，不要过长(但当用户并非普通聊天而是查询消息时应详细回答)
2. 适当参考对话历史和永久记忆，保持上下文连贯
3. 不要主动提及表情包，除非用户明确要求
4. 直接输出回复内容，不要任何额外说明
5.回答中可适当加上'喵'等语气词和一些颜文字，让自己显得可爱，毕竟oguri是一名可爱的赛马娘

"""

# 仅「普通模式」使用：与 .env 的 system_prompt 一致，永不写入 QBY 文案
_OGURI_PROMPT_TEMPLATE = (const.chat_system_prompt or _DEFAULT_CHAT_SYSTEM_PROMPT).strip() or _DEFAULT_CHAT_SYSTEM_PROMPT

system_prompts = {
    "chat": _OGURI_PROMPT_TEMPLATE,
}

# 接在普通模式完整 prompt 末尾，防止历史里曾出现 qby 而串台（不是 QBY 人设，只是模式锁）
_NORMAL_MODE_LOCK = (
    "\n\n【模式：普通】你必须严格遵循本提示最上方的身份与要求；禁止自称 qby、禁止 QBY 语体或与 qby skill 相关的称呼习惯。"
)

qby_mode_active: bool = const.qby_model_default
QBY_SKILL_PATH = os.path.join(TEAM_MEMBER_FOLDER, "qby.md")


def get_qby_mode() -> bool:
    return qby_mode_active


def enable_qby_mode() -> bool:
    """强制开启 QBY。返回 True 表示此前为关（本次刚从关→开）。"""
    global qby_mode_active
    was_off = not qby_mode_active
    qby_mode_active = True
    if was_off:
        logger.info("qby_mode_active = True (explicit on)")
    return was_off


def disable_qby_mode() -> bool:
    """强制关闭 QBY。返回 True 表示此前为开（本次执行了关）。"""
    global qby_mode_active
    was_on = qby_mode_active
    qby_mode_active = False
    if was_on:
        logger.info("qby_mode_active = False (explicit off)")
    return was_on


def quit_qby_mode() -> bool:
    """与显式关闭一致（兼容 qby quit）。"""
    return disable_qby_mode()


def parse_group_qby_command(text: str) -> Optional[str]:
    """
    解析群聊 @ 机器人后的 QBY 指令（固定语义，不翻转）。
    返回 'on' | 'off' | None：/qby 仅开启，/qby quit 仅关闭。
    """
    raw = (text or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"/qby\s+quit\s*", raw, re.IGNORECASE):
        return "off"
    if raw.lower() == "qby quit":
        return "off"
    if re.fullmatch(r"/qby\s*", raw, re.IGNORECASE):
        return "on"
    if re.fullmatch(r"qby\s*", raw, re.IGNORECASE):
        return "on"
    return None


_QBY_CONTEXT_TEMPLATE = """用户信息: 用户ID {user_id}
用户偏好: {user_pref_info}

永久记忆:
{permanent_memory}

最近对话历史:
{history_context}

网络搜索结果:
{web_results}

用户说: {user_input}"""

# QBY 人设里常只写「你是 qby」，易与「用户」混淆；固定补一段角色边界（不依赖 .env 是否写全）
_QBY_ROLE_RULES = """
【角色与输出（必须遵守）】
- 你是聊天助手，人设网名是 qby；正在回复的是下面「用户说」里的用户，不要把对方叫成 QBY/qby。
- 自称用「我」即可，不必每句带网名。
- 上文「口癖备忘」**只供轻量借鉴**（零星口癖、短句节奏），**禁止**套模板、禁止过拟合文档、禁止为像而像。先答内容，再考虑是否带一点口癖。
- **禁止**用同一句首口头禅刷屏（尤其不要每句都以「搞么」「搞么~」开头）；口癖可省略，或轮换、或放在句中/句尾。
- 不要用赛马娘式「喵～」、堆颜文字，除非用户明确要求。
- 以自然对话为主：长短随话题，别刻意堆游戏黑话或清单式口癖。"""


def _load_qby_skill_text() -> str:
    try:
        with open(QBY_SKILL_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.warning(f"未找到 QBY skill 文件: {QBY_SKILL_PATH}")
        return ""
    except Exception as e:
        logger.error(f"读取 QBY skill 失败: {e}")
        return ""


def set_system_prompt(prompt_type: str, prompt: str):
    """仅用于覆盖普通模式模板（oguri / .env system_prompt），勿写入 QBY 内容。"""
    system_prompts[prompt_type] = prompt


def get_system_prompt(prompt_type: str) -> str:
    return system_prompts.get(prompt_type, "")


def _normal_mode_prompt(ctx: Dict[str, Any]) -> str:
    """普通模式唯一入口：只用 oguri 模板 + 模式锁，不引用 qby_system_prompt 与 skill。"""
    return system_prompts["chat"].format(**ctx) + _NORMAL_MODE_LOCK


def _normalize_bot_reply_text(text: str) -> str:
    """发送前整理：去掉首尾空白，把连续多个换行压成单行，避免 QQ 里出现双空行、大块留白。"""
    if not text:
        return text
    t = text.strip()
    if not t:
        return t
    return re.sub(r"\n{2,}", "\n", t)


def load_user_preferences():
    global user_preferences
    prefs_file = os.path.join(DATA_FOLDER, "user_preferences.json")
    if os.path.exists(prefs_file):
        try:
            with open(prefs_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                user_preferences = {int(k): v for k, v in data.items()}
        except Exception as e:
            logger.error(f"加载用户偏好失败: {e}")


def save_user_preferences():
    prefs_file = os.path.join(DATA_FOLDER, "user_preferences.json")
    try:
        with open(prefs_file, 'w', encoding='utf-8') as f:
            json.dump(user_preferences, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存用户偏好失败: {e}")


def load_chat_history():
    global chat_history
    history_file = os.path.join(DATA_FOLDER, "chat_history.json")
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                chat_history = json.load(f)
        except Exception as e:
            logger.error(f"加载聊天历史失败: {e}")


def save_chat_history():
    history_file = os.path.join(DATA_FOLDER, "chat_history.json")
    try:
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(chat_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存聊天历史失败: {e}")


def load_permanent_memories():
    global permanent_memories
    memory_file = os.path.join(DATA_FOLDER, "permanent_memories.json")
    if os.path.exists(memory_file):
        try:
            with open(memory_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                permanent_memories = {int(k): v for k, v in data.items()}
        except Exception as e:
            logger.error(f"加载永久记忆失败: {e}")


def save_permanent_memories():
    memory_file = os.path.join(DATA_FOLDER, "permanent_memories.json")
    try:
        with open(memory_file, 'w', encoding='utf-8') as f:
            json.dump(permanent_memories, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存永久记忆失败: {e}")


load_user_preferences()
load_chat_history()
load_permanent_memories()


def get_user_history_count(user_id: int) -> int:
    return sum(1 for msg in chat_history if msg.get("user_id") == user_id)


def clear_user_history(user_id: int):
    global chat_history

    # 获取该用户的历史记录用于总结
    user_messages = [msg for msg in chat_history if msg.get("user_id") == user_id]

    if user_messages:
        # 在线程池中运行异步总结任务，避免与主事件循环冲突
        import threading

        def run_summary():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            personality_data: Optional[Dict[str, Any]] = None
            try:
                personality_data = loop.run_until_complete(_summarize_user_personality(user_id, user_messages))
                if personality_data:
                    _save_user_personality(user_id, personality_data)
            except Exception as e:
                logger.error(f"清理前用户总结失败: {e}")
            finally:
                try:
                    _write_team_member_md(user_id, personality_data)
                except Exception as e:
                    logger.error(f"写入 team_member 档案失败: {e}")
                loop.close()

        thread = threading.Thread(target=run_summary)
        thread.start()
        thread.join(timeout=30)  # 最多等待30秒

    chat_history = [msg for msg in chat_history if msg.get("user_id") != user_id]
    save_chat_history()
    logger.info(f"已清空用户 {user_id} 的临时聊天历史")


async def _summarize_user_personality(user_id: int, user_messages: List[ChatMessage]) -> dict:
    """总结用户的性格和有趣的事情（仅根据用户本人发言，不含 assistant 回复）。"""
    if not user_messages:
        return None

    user_only = [msg for msg in user_messages if msg.get("role") == "user"]
    if not user_only:
        return None

    chat_text = "\n".join([f"用户: {msg['message']}" for msg in user_only])

    summary_prompt = f"""请根据以下**用户发言**（已排除机器人回复），总结该用户的性格特点和聊天中有趣之处。

用户发言：
{chat_text}

请按以下JSON格式返回分析结果：
{{
    "personality": "用户的性格特点描述（如：幽默风趣、严肃认真、活泼开朗等）",
    "interests": ["用户感兴趣的话题1", "话题2", "话题3"],
    "funny_moments": "聊天中发生的有趣事情或经典对话（如果没有可以写\"无\"）",
    "communication_style": "用户的沟通风格（如：喜欢开玩笑、直接了当、礼貌客气等）",
    "summary": "整体总结，50字以内"
}}

要求：
1. 分析要客观、准确
2. 性格描述要具体，不要泛泛而谈
3. 有趣的事情要真实发生在聊天记录中
4. 只返回JSON格式，不要其他内容"""

    try:
        response = await llm.ainvoke(summary_prompt)
        content = response.content.strip()
        logger.info(f"用户 {user_id} 的性格分析结果: {content[:200]}...")

        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        result = json.loads(content)

        from datetime import datetime
        return {
            "personality": result.get("personality", "未知"),
            "interests": result.get("interests", []),
            "funny_moments": result.get("funny_moments", "无"),
            "communication_style": result.get("communication_style", "未知"),
            "summary": result.get("summary", ""),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"总结用户性格失败: {e}")
        return None


def _write_team_member_md(user_id: int, personality_data: Optional[Dict[str, Any]]):
    """将偏好与说话方式蒸馏写入 team_member/{user_id}.md（聊天条数达上限触发清理时调用）。"""
    from datetime import datetime

    pref = get_user_preference(user_id)
    ts = (personality_data or {}).get("timestamp") or datetime.now().isoformat()

    topics = pref.get("topic_preferences") or []
    emoji_items = sorted(
        (pref.get("emoji_preferences") or {}).items(),
        key=lambda x: -x[1],
    )[:8]
    emoji_line = "、".join(f"{name}（{cnt}）" for name, cnt in emoji_items) if emoji_items else "暂无统计"

    lines = [
        f"# 群友档案 · {user_id}",
        "",
        f"- 蒸馏时间：`{ts}`",
        "",
        "## 偏好",
        "",
    ]
    if topics:
        lines.append("- **感兴趣话题**：" + "、".join(topics))
    else:
        lines.append("- **感兴趣话题**：暂无记录")
    lines.append(f"- **常用表情图**：{emoji_line}")
    if pref.get("last_interaction"):
        lines.append(f"- **最近互动**：`{pref['last_interaction']}`")
    lines.extend(["", "## 说话方式与画像", ""])

    if personality_data:
        interests = personality_data.get("interests") or []
        lines.extend(
            [
                f"- **沟通风格**：{personality_data.get('communication_style', '未知')}",
                f"- **性格侧写**：{personality_data.get('personality', '未知')}",
                "- **兴趣摘要（对话蒸馏）**：" + ("、".join(interests) if interests else "无"),
                f"- **一句话画像**：{personality_data.get('summary', '')}",
                "",
                "## 互动花絮",
                "",
                str(personality_data.get("funny_moments") or "无"),
            ]
        )
    else:
        lines.append("_（本窗口对话较多，但自动蒸馏未完成或失败；仅保留偏好统计。）_")

    path = os.path.join(TEAM_MEMBER_FOLDER, f"{user_id}.md")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        logger.info(f"已写入团队成员档案: {path}")
    except Exception as e:
        logger.error(f"写入 team_member 档案失败: {e}")


def _save_user_personality(user_id: int, personality_data: dict):
    """保存用户性格数据到文件"""
    personality_file = os.path.join(DATA_FOLDER, "user_personality.json")

    existing_data = {}
    if os.path.exists(personality_file):
        try:
            with open(personality_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        except Exception as e:
            logger.error(f"读取用户性格文件失败: {e}")

    user_id_str = str(user_id)
    if user_id_str not in existing_data:
        existing_data[user_id_str] = []

    existing_data[user_id_str].append(personality_data)

    try:
        with open(personality_file, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
        logger.info(f"已保存用户 {user_id} 的性格分析")
    except Exception as e:
        logger.error(f"保存用户性格数据失败: {e}")


def add_to_history(
    user_id: int,
    message: str,
    role: str = "user",
    group_id: Optional[int] = None,
):
    from datetime import datetime

    user_count = get_user_history_count(user_id)
    if user_count >= MAX_HISTORY_PER_USER:
        clear_user_history(user_id)

    record: dict = {
        "user_id": user_id,
        "message": message,
        "role": role,
        "timestamp": datetime.now().isoformat(),
    }
    if group_id is not None:
        record["group_id"] = group_id
    chat_history.append(record)
    save_chat_history()


def add_permanent_memory(user_id: int, content: str):
    from datetime import datetime

    if user_id not in permanent_memories:
        permanent_memories[user_id] = []

    permanent_memories[user_id].append({
        "user_id": user_id,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })
    save_permanent_memories()
    logger.info(f"已为用户 {user_id} 添加永久记忆: {content}")


def get_user_permanent_memories(user_id: int) -> List[str]:
    if user_id not in permanent_memories:
        return []
    return [m["content"] for m in permanent_memories[user_id]]


def check_memory_request(text: str) -> Optional[str]:
    keywords = ["记住", "记得", "记下来", "别忘了", "帮我记"]
    for kw in keywords:
        if kw in text:
            idx = text.find(kw)
            content = text[idx + len(kw):].strip()
            if content:
                return content
            parts = text.split(kw, 1)
            if len(parts) > 1 and parts[1].strip():
                return parts[1].strip()
    return None


def get_user_recent_history(user_id: int, limit: int = 5) -> List[ChatMessage]:
    user_messages = [msg for msg in reversed(chat_history) if msg.get("user_id") == user_id]
    return user_messages[:limit]


def get_group_recent_history(group_id: int, limit: int) -> List[ChatMessage]:
    gmsgs = [msg for msg in reversed(chat_history) if msg.get("group_id") == group_id]
    return gmsgs[:limit]


def search_chat_history(query: str, user_id: Optional[int] = None, limit: int = 10) -> List[ChatMessage]:
    results = []
    for msg in reversed(chat_history):
        if user_id and msg.get("user_id") != user_id:
            continue
        if query.lower() in msg.get("message", "").lower():
            results.append(msg)
            if len(results) >= limit:
                break
    return results


def get_available_emojis() -> List[dict]:
    emojis = []
    if os.path.exists(PIC_FOLDER):
        for filename in os.listdir(PIC_FOLDER):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                name_without_ext = os.path.splitext(filename)[0]
                emojis.append({
                    "name": name_without_ext,
                    "path": os.path.join(PIC_FOLDER, filename)
                })
    return emojis


def find_emoji_by_description(description: str) -> Optional[str]:
    emojis = get_available_emojis()
    description_lower = description.lower()
    for emoji in emojis:
        if description_lower in emoji["name"].lower():
            return emoji["path"]
    return None


def web_search(query: str, max_results: int = 7, time_range: str = 'week') -> str:
    """使用 Tavily API 进行网络搜索"""
    # 验证 time_range 参数
    valid_time_ranges = ['none', 'day', 'week', 'month', 'year']
    if time_range not in valid_time_ranges:
        time_range = 'week'
    
    # 检查 API Key
    if not const.tavily_apikey:
        logger.error("Tavily API Key 未配置")
        return "网络搜索功能未配置 API Key"
    
    try:
        client = TavilyClient(const.tavily_apikey)
        
        # 构建搜索参数
        search_params = {
            "query": query,
            "search_depth": "advanced",
            "max_results": max_results,  # 注意：参数名是小写
        }
        
        # 只有非 'none' 时才添加 time_range
        if time_range != 'none':
            search_params["time_range"] = time_range
        
        logger.info(f"Tavily 搜索参数: {search_params}")
        response = client.search(**search_params)
        
        results = []
        for element in response.get("results", []):
            title = element.get("title", "")
            content = element.get("content", "")
            url = element.get("url", "")
            if title and content:
                results.append({
                    "title": title,
                    "content": content[:500],  # 限制内容长度
                    "url": url
                })
        
        if not results:
            return "网络搜索结果：未找到相关信息"
        
        # 格式化输出
        output_lines = ["网络搜索结果："]
        for i, r in enumerate(results, 1):
            output_lines.append(f"\n{i}. {r['title']}")
            output_lines.append(f"   {r['content']}")
            if r['url']:
                output_lines.append(f"   来源: {r['url']}")
        
        result_text = "\n".join(output_lines)
        logger.info(f"搜索完成，找到 {len(results)} 条结果")
        return result_text
        
    except Exception as e:
        logger.error(f"Tavily 搜索失败: {e}")
        return f"网络搜索失败: {str(e)}"


class SearchParams(TypedDict):
    need_search: bool
    query: str
    max_results: int
    time_range: str


async def analyze_search_need(user_input: str) -> SearchParams:
    """让模型判断是否需要网络搜索，并生成搜索参数"""
    check_prompt = f"""分析以下用户问题，判断是否需要网络搜索，并生成搜索参数。

用户问题: {user_input}

请按以下JSON格式返回结果：
{{
    "need_search": true/false,
    "query": "优化后的搜索关键词",
    "max_results": 数字(3-10),
    "time_range": "none/day/week/month/year"
}}

字段说明：
- need_search: 是否需要搜索
  - true: 需要查询最新信息、新闻、天气、股票、知识点、人物、事件等
  - false: 日常聊天、问候、情感交流、常识问题、要求表情包
- query: 优化后的搜索关键词，提取用户问题的核心搜索意图
- max_results: 需要的搜索结果数量，根据问题复杂度选择3-10
- time_range: 时间范围偏好
  - None: 不限制时间（历史知识、常识）
  - "day": 最近一天（突发新闻、今日热点）
  - "week": 最近一周（一般新闻、动态）
  - "month": 最近一月（较新信息）
  - "year": 最近一年（年度信息）

只返回JSON格式，不要其他内容。"""

    try:
        response = await llm.ainvoke(check_prompt)
        content = response.content.strip()
        logger.info(f"模型搜索分析结果: {content}")

        # 尝试解析JSON
        import json
        # 清理可能的markdown代码块
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        result = json.loads(content)

        # 验证并设置默认值
        return {
            "need_search": result.get("need_search", False),
            "query": result.get("query", user_input),
            "max_results": max(3, min(10, result.get("max_results", 7))),
            "time_range": result.get("time_range", "week") if result.get("time_range") in ['none', 'day', 'week', 'month', 'year'] else 'week'
        }
    except json.JSONDecodeError as e:
        logger.error(f"解析搜索参数JSON失败: {e}, 内容: {content}")
        # 回退到简单判断
        return {
            "need_search": "需要" in content or "true" in content.lower(),
            "query": user_input,
            "max_results": 7,
            "time_range": "week"
        }
    except Exception as e:
        logger.error(f"分析搜索需求失败: {e}")
        return {
            "need_search": False,
            "query": user_input,
            "max_results": 7,
            "time_range": "week"
        }


async def need_web_search(user_input: str) -> bool:
    """让模型判断是否需要网络搜索（兼容旧接口）"""
    result = await analyze_search_need(user_input)
    return result["need_search"]


def get_user_preference(user_id: int) -> UserPreference:
    if user_id not in user_preferences:
        user_preferences[user_id] = {
            "user_id": user_id,
            "emoji_preferences": {},
            "topic_preferences": [],
            "last_interaction": ""
        }
    return user_preferences[user_id]


def update_user_emoji_preference(user_id: int, emoji_name: str):
    from datetime import datetime
    pref = get_user_preference(user_id)
    pref["emoji_preferences"][emoji_name] = pref["emoji_preferences"].get(emoji_name, 0) + 1
    pref["last_interaction"] = datetime.now().isoformat()
    save_user_preferences()


def get_preferred_emoji(user_id: int) -> Optional[str]:
    pref = get_user_preference(user_id)
    if not pref["emoji_preferences"]:
        return None
    return max(pref["emoji_preferences"].items(), key=lambda x: x[1])[0]


def update_user_topic_preference(user_id: int, topics: List[str]):
    from datetime import datetime
    pref = get_user_preference(user_id)
    for topic in topics:
        if topic not in pref["topic_preferences"]:
            pref["topic_preferences"].append(topic)
    pref["topic_preferences"] = pref["topic_preferences"][-10:]
    pref["last_interaction"] = datetime.now().isoformat()
    save_user_preferences()


class AgentState(TypedDict):
    user_input: str
    user_id: Optional[int]
    group_id: Optional[int]
    final_response: str
    emoji_to_send: Optional[str]
    memory_saved: bool
    pixiv_images: List[str]
    memory_content: Optional[str]
    history_context: str
    user_pref_info: str
    permanent_memory_str: str
    web_results: str
    need_search: bool
    search_query: str
    search_max_results: int
    search_time_range: str
    pixiv_request: Optional[Dict[str, Any]]


def parse_pixiv_request(user_input: str) -> Optional[dict]:
    """解析用户对 Pixiv 图片的请求"""
    pixiv_keywords = ["pixiv", "p站", "P站", "Pixiv", "PIXIV"]
    has_pixiv_keyword = any(kw in user_input for kw in pixiv_keywords)

    if not has_pixiv_keyword:
        return None

    result = {"mode": None, "page_url": None, "pic_num": 2}

    rank_patterns = [
        (r"今日.*排行|daily.*排行|日榜", "daily"),
        (r"本周.*排行|weekly.*排行|周榜", "weekly"),
        (r"本月.*排行|monthly.*排行|月榜", "monthly"),
        (r"新人.*排行|rookie.*排行|新秀", "rookie"),
        (r"排行", "daily"),
    ]

    for pattern, rank_type in rank_patterns:
        if re.search(pattern, user_input):
            result["mode"] = 1
            result["page_url"] = rank_type
            break

    if result["mode"] == 1:
        num_match = re.search(r"(\d+)\s*张", user_input)
        if num_match:
            result["pic_num"] = min(int(num_match.group(1)), 10)
        return result

    pid_pattern = r"(?:pid|PID|Pid)?\s*(\d{6,10})"
    pid_match = re.search(pid_pattern, user_input)
    if pid_match:
        result["mode"] = 3
        result["page_url"] = pid_match.group(1)
        num_match = re.search(r"(\d+)\s*张", user_input)
        if num_match:
            result["pic_num"] = min(int(num_match.group(1)), 10)
        return result

    label_patterns = [
        r"(.+?)的?图片",
        r"(.+?)的?图",
        r"搜(.+?)",
        r"找(.+?)",
    ]

    for pattern in label_patterns:
        match = re.search(pattern, user_input)
        if match:
            label = match.group(1).strip()
            for kw in pixiv_keywords + ["的", "张", "图片", "图"]:
                label = label.replace(kw, "")
            if label and len(label) > 0:
                result["mode"] = 2
                result["page_url"] = label
                num_match = re.search(r"(\d+)\s*张", user_input)
                if num_match:
                    result["pic_num"] = min(int(num_match.group(1)), 10)
                return result

    return None


async def context_node(state: AgentState) -> Dict[str, Any]:
    """加载会话上下文、永久记忆写入、解析 Pixiv 请求（不下载）。"""
    user_input = state["user_input"]
    user_id = state.get("user_id")

    memory_saved = False
    memory_content: Optional[str] = check_memory_request(user_input)
    if memory_content and user_id:
        add_permanent_memory(user_id, memory_content)
        memory_saved = True

    recent_history: List[ChatMessage] = []
    lim = CONTEXT_MESSAGE_NUM
    gid = state.get("group_id")
    # 群聊：reply / listen 均取该群最近 N 条（多用户）；私聊仍按 user_id
    if gid:
        recent_history = get_group_recent_history(gid, lim)
        history_context = "\n".join(
            [
                (
                    f"用户{msg['user_id']}: {msg['message']}"
                    if msg.get("role") == "user"
                    else f"助手: {msg['message']}"
                )
                for msg in reversed(recent_history)
            ]
        )
    elif user_id:
        recent_history = get_user_recent_history(user_id, lim)
        history_context = "\n".join(
            [f"{msg['role']}: {msg['message']}" for msg in reversed(recent_history)]
        )
    else:
        history_context = ""

    user_pref_info = ""
    if user_id:
        pref = get_user_preference(user_id)
        if pref["topic_preferences"]:
            user_pref_info = f"感兴趣的话题: {', '.join(pref['topic_preferences'][:3])}"

    permanent_memory_str = "暂无"
    if user_id:
        memories = get_user_permanent_memories(user_id)
        if memories:
            permanent_memory_str = "\n".join([f"- {m}" for m in memories[-5:]])

    return {
        "memory_saved": memory_saved,
        "memory_content": memory_content,
        "history_context": history_context,
        "user_pref_info": user_pref_info,
        "permanent_memory_str": permanent_memory_str,
        "pixiv_request": parse_pixiv_request(user_input),
    }


async def pixiv_node(state: AgentState) -> Dict[str, Any]:
    """如有 Pixiv 请求则下载；成功时直接生成简短 final_response。"""
    pixiv_request = state.get("pixiv_request")
    pixiv_images: List[str] = []
    final_response = ""

    if pixiv_request:
        try:
            logger.info(
                f"Pixiv请求: mode={pixiv_request['mode']}, page_url={pixiv_request['page_url']}, pic_num={pixiv_request['pic_num']}"
            )
            loop = asyncio.get_event_loop()
            pixiv_images = await loop.run_in_executor(
                _executor,
                download_pic_pixiv_rank_label_page,
                pixiv_request["page_url"],
                pixiv_request["mode"],
                "pixiv",
                pixiv_request["pic_num"],
            )
            logger.info(f"Pixiv下载完成，获取 {len(pixiv_images)} 张图片")
        except Exception as e:
            logger.error(f"Pixiv下载失败: {e}")
            pixiv_images = []

    if pixiv_images:
        final_response = f"已经为你找到了 {len(pixiv_images)} 张图片喵~"
        logger.info(f"Pixiv图片路径: {pixiv_images}")

    return {"pixiv_images": pixiv_images, "final_response": final_response}


def route_after_pixiv(state: AgentState) -> str:
    """有图则跳过后续搜索与生成，直接去收尾（与原逻辑一致）。"""
    return "finalize" if state.get("pixiv_images") else "search_plan"


async def search_plan_node(state: AgentState) -> Dict[str, Any]:
    """LLM 决定是否需要联网搜索及查询参数。"""
    search_params = await analyze_search_need(state["user_input"])
    logger.info(
        f"搜索分析结果: need_search={search_params['need_search']}, query={search_params['query']}, "
        f"max_results={search_params['max_results']}, time_range={search_params['time_range']}"
    )
    return {
        "need_search": search_params["need_search"],
        "search_query": search_params["query"],
        "search_max_results": search_params["max_results"],
        "search_time_range": search_params["time_range"],
        "web_results": "无需搜索",
    }


def route_need_search(state: AgentState) -> str:
    return "tavily" if state.get("need_search") else "generate"


async def tavily_node(state: AgentState) -> Dict[str, Any]:
    """执行 Tavily 搜索，写入 web_results。"""
    logger.info(f"开始网络搜索: {state['search_query']}")
    loop = asyncio.get_event_loop()
    web_results = await loop.run_in_executor(
        _executor,
        web_search,
        state["search_query"],
        state["search_max_results"],
        state["search_time_range"],
    )
    logger.info(
        f"搜索结果长度: {len(web_results)}, 内容预览: {web_results[:300] if len(web_results) > 300 else web_results}"
    )
    return {"web_results": web_results}


async def generate_node(state: AgentState) -> Dict[str, Any]:
    """组装提示词并调用 LLM（含 QBY skill 与审核降级）。"""
    user_input = state["user_input"]
    user_id = state.get("user_id")
    web_results = state.get("web_results") or "无需搜索"
    history_context = state.get("history_context") or ""
    user_pref_info = state.get("user_pref_info") or ""
    permanent_memory_str = state.get("permanent_memory_str") or "暂无"
    memory_saved = state.get("memory_saved", False)
    memory_content = state.get("memory_content")

    if not state.get("need_search"):
        logger.info("不需要网络搜索，跳过")

    ctx_kwargs = dict(
        user_input=user_input,
        user_id=user_id or "未知",
        history_context=history_context or "无历史记录",
        user_pref_info=user_pref_info or "暂无",
        permanent_memory=permanent_memory_str,
        web_results=web_results,
    )

    if qby_mode_active:
        # QBY：仅 qby_system_prompt + skill + QBY 上下文，禁止混入 system_prompt（oguri）
        persona = (const.qby_system_prompt or "你是群聊助手，网名 qby；回答要自然，口癖仅从下文备忘里轻量借一点即可。").strip()
        body = _QBY_CONTEXT_TEMPLATE.format(**ctx_kwargs)
        skill = _load_qby_skill_text()
        core = f"{persona}\n{_QBY_ROLE_RULES}\n\n{body}"
        if skill:
            prompt = (
                "【口癖与节奏备忘】（不是剧本，不要逐条模仿；内容与礼貌优先）\n\n"
                f"{skill}\n\n---\n\n"
                f"{core}"
            )
        else:
            prompt = core
    else:
        # 普通：仅 .env system_prompt（经 system_prompts['chat']），与 QBY 完全隔离
        prompt = _normal_mode_prompt(ctx_kwargs)

    logger.info(f"提示词中web_results字段: {web_results[:100] if len(web_results) > 100 else web_results}")
    logger.debug(f"完整提示词长度: {len(prompt)}")

    final_response = ""
    try:
        response = await llm.ainvoke(prompt)
        final_response = response.content
    except Exception as e:
        error_str = str(e)
        if "Content Exists Risk" in error_str or "content_filter" in error_str.lower():
            logger.warning("内容审核触发，尝试简化提示词重试")
            if qby_mode_active:
                persona = (const.qby_system_prompt or "你是群聊助手，网名 qby；回答要自然，口癖仅从备忘轻量借一点即可。").strip()
                simple_core = f"""用户问: {user_input}

抱歉，搜索结果触发了内容审核，无法直接展示。请根据你的知识简单回答用户的问题，并说明搜索结果暂时不可用。"""
                simple_prompt = f"{persona}\n{_QBY_ROLE_RULES}\n\n{simple_core}"
                skill = _load_qby_skill_text()
                if skill:
                    simple_prompt = (
                        "【口癖与节奏备忘】（轻量借鉴，勿套模板）\n\n"
                        f"{skill}\n\n---\n\n"
                        f"{simple_prompt}"
                    )
            else:
                ctx_audit = {
                    **ctx_kwargs,
                    "web_results": (
                        "（内容审核已拦截联网摘要，请勿编造链接或具体搜索结果；请依据常识简要说明无法展示原因并回答用户。）"
                    ),
                }
                simple_prompt = (
                    system_prompts["chat"].format(**ctx_audit)
                    + "\n\n【审核降级】回复尽量简短。"
                    + _NORMAL_MODE_LOCK
                )
            try:
                response = await llm.ainvoke(simple_prompt)
                final_response = response.content
            except Exception as e2:
                logger.error(f"简化提示词也失败: {e2}")
                final_response = "抱歉喵，搜索结果触发了内容审核，暂时无法回答这个问题~ 试试换个话题吧！"
        else:
            raise e

    if memory_saved:
        mc = memory_content or ""
        final_response = f"好的，我已经记住了：{mc}\n{final_response}"

    return {"final_response": _normalize_bot_reply_text(final_response)}


async def finalize_node(state: AgentState) -> Dict[str, Any]:
    """表情与话题偏好（与原 chat_node 尾部一致）。"""
    user_input = state["user_input"]
    user_id = state.get("user_id")

    emoji_path: Optional[str] = None
    emoji_keywords = ["表情", "emoji", "表情包", "发个图", "斗图"]
    needs_emoji = any(kw in user_input for kw in emoji_keywords)

    if needs_emoji:
        emojis = get_available_emojis()
        if emojis:
            random_emoji = random.choice(emojis)
            emoji_path = random_emoji["path"]
            if user_id:
                update_user_emoji_preference(user_id, random_emoji["name"])

    if user_id:
        topics = extract_topics(user_input)
        if topics:
            update_user_topic_preference(user_id, topics)

    return {"emoji_to_send": emoji_path}


def extract_topics(text: str) -> List[str]:
    topic_keywords = [
        "游戏", "音乐", "电影", "动漫", "美食", "旅行", "运动", "健身",
        "科技", "编程", "学习", "工作", "生活", "情感", "搞笑", "宠物",
        "摄影", "读书", "购物", "天气", "新闻", "体育", "明星", "汽车"
    ]

    found_topics = []
    for topic in topic_keywords:
        if topic in text:
            found_topics.append(topic)

    return found_topics[:3]


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("context", context_node)
    graph.add_node("pixiv", pixiv_node)
    graph.add_node("search_plan", search_plan_node)
    graph.add_node("tavily", tavily_node)
    graph.add_node("generate", generate_node)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("context")
    graph.add_edge("context", "pixiv")
    graph.add_conditional_edges(
        "pixiv",
        route_after_pixiv,
        {"finalize": "finalize", "search_plan": "search_plan"},
    )
    graph.add_conditional_edges(
        "search_plan",
        route_need_search,
        {"tavily": "tavily", "generate": "generate"},
    )
    graph.add_edge("tavily", "generate")
    graph.add_edge("generate", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


agent_graph = build_graph()


async def chat_agent(
        user_input: str,
        user_id: Optional[int] = None,
        group_id: Optional[int] = None
) -> dict:
    initial_state: AgentState = {
        "user_input": user_input,
        "user_id": user_id,
        "group_id": group_id,
        "final_response": "",
        "emoji_to_send": None,
        "memory_saved": False,
        "pixiv_images": [],
        "memory_content": None,
        "history_context": "",
        "user_pref_info": "",
        "permanent_memory_str": "暂无",
        "web_results": "无需搜索",
        "need_search": False,
        "search_query": "",
        "search_max_results": 7,
        "search_time_range": "week",
        "pixiv_request": None,
    }

    result = await agent_graph.ainvoke(initial_state)

    emoji_path = result.get("emoji_to_send")

    if not emoji_path and random.random() < 0.15:
        emojis = get_available_emojis()
        if emojis:
            random_emoji = random.choice(emojis)
            emoji_path = random_emoji["path"]
            if user_id:
                update_user_emoji_preference(user_id, random_emoji["name"])

    return {
        "response": _normalize_bot_reply_text(result.get("final_response", "") or ""),
        "emoji_path": emoji_path,
        "memory_saved": result.get("memory_saved", False),
        "pixiv_images": result.get("pixiv_images", [])
    }
