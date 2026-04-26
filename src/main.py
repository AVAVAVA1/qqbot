import asyncio
import os
import re
import websockets
import json
from loguru import logger
from response import api, MessageSegment
from llm_chat import (
    chat_agent,
    add_to_history,
    parse_group_qby_command,
    enable_qby_mode,
    disable_qby_mode,
)
from check_activity_level import create_activity_checker
import const

with open(
    os.path.join(os.path.dirname(__file__), "config.json"), encoding="utf-8"
) as _f:
    _bot_cfg = json.load(_f)

WS_URL = _bot_cfg["ws_url"]
ACCESS_TOKEN = _bot_cfg["access_token"]
chat_group_ls = [int(x) for x in _bot_cfg["chat_group_ids"]]
check_activity_level_group = [
    int(x) for x in _bot_cfg["check_activity_level_group_ids"]
]
"""
# 发送私聊消息
await api.send_private_msg(user_id=12345678, message="你好")

# 发送群消息
await api.send_group_msg(group_id=12345678, message="大家好")

# 发送复合消息（@ + 文本）
message = [
    MessageSegment.at(12345678),
    MessageSegment.text(" 你好")
]
await api.send_group_msg(group_id=12345678, message=message)

# 回复消息
message = [
    MessageSegment.reply(message_id),
    MessageSegment.text("收到")
]
await api.send_group_msg(group_id=12345678, message=message)
"""


message_counter = 0

update_log = {
    '2026/3/19': {'time': '2026/3/19', 'content': '1.新增了暖场服务和晚安问候服务 2.优化了web search 功能.接入了tavily的search api 每月1000免费额度'},
    '2026/3/21': {'time': '2026/3/21', 'content':'1.优化了pixiv download 模块，使下载数与请求数相匹配'},
    '2026/4/25': {'time': '2026/4/25', 'content':'1.新增了qby模式，可以在群聊中使用qby来回答用户的问题.使用/qby开启,/qby quit关闭模式 2.优化了langgraph pipeline，减少了api的无效访问，更易于维护'},
    '2026/4/26': {'time': '2026/4/26', 'content':'1.新增功能：对每名群u的发言进行蒸馏'},
}



async def connect_napcat():
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }

    try:
        async with websockets.connect(WS_URL, additional_headers=headers) as ws:
            logger.info(f"已连接到 NapCat WebSocket: {WS_URL}")
            api.set_ws(ws)



            async for message in ws:
                try:
                    data = json.loads(message)
                    if data.get("echo") and data["echo"] in api._pending_requests:
                        api._pending_requests[data["echo"]].set_result(data)
                        del api._pending_requests[data["echo"]]
                    else:
                        asyncio.create_task(handle_event(data))
                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析错误: {e}")

    except websockets.exceptions.ConnectionClosed as e:
        logger.warning(f"连接已关闭: {e}")
    except Exception as e:
        logger.error(f"连接错误: {e}")




async def handle_event(data: dict):
    post_type = data.get("post_type")

    if post_type == "message":
        await handle_message(data)
    elif post_type == "notice":
        logger.info(f"收到通知事件: {data.get('notice_type')}")
    elif post_type == "request":
        logger.info(f"收到请求事件: {data.get('request_type')}")
    elif post_type == "meta_event":
        if data.get("meta_event_type") == "heartbeat":
            pass
        elif data.get("meta_event_type") == "lifecycle":
            logger.info(f"生命周期事件: {data}")


async def handle_message(data: dict):
    message_type = data.get("message_type")
    user_id = data.get("user_id")
    message = data.get("message", [])
    raw_message = data.get("raw_message", "")

    message_content = parse_message(message)

    if message_type == "private":
        logger.info(f"[私聊] 用户 {user_id}: {message_content}")
        # 私聊处理
        result = await chat_agent(message_content, user_id=user_id)

        # 发送文本回复
        if result["response"]:
            await api.send_private_msg(user_id=user_id, message=result["response"])

        if result["emoji_path"]:
            emoji_msg = [MessageSegment.image(file=result["emoji_path"])]
            await api.send_private_msg(user_id=user_id, message=emoji_msg)

        # 记录历史
        add_to_history(user_id, message_content, "user")
        if result["response"]:
            add_to_history(user_id, result["response"], "assistant")

    elif message_type == "group":
        group_id = data.get("group_id")
        content = f"[群聊] 群 {group_id} 用户 {user_id}: {message_content}"
        logger.info(content)
        if group_id in check_activity_level_group:
            global message_counter
            message_counter += 1
        if group_id in chat_group_ls and '@3806541446' in message_content:
            try:
                clean_content = re.sub(r"^@3806541446\s*", "", message_content).strip()
                qby_cmd = parse_group_qby_command(clean_content)
                if qby_cmd:
                    if qby_cmd == "on":
                        changed = enable_qby_mode()
                        result = {
                            "response": (
                                "QBY 模式已开启。"
                                if changed
                                else "已经在 QBY 模式。关闭请发：@机器人 /qby quit"
                            )
                        }
                    else:
                        was_on = disable_qby_mode()
                        result = {
                            "response": (
                                "QBY 模式已关闭。"
                                if was_on
                                else "当前不在 QBY 模式。开启请发：@机器人 /qby"
                            )
                        }
                    if result["response"]:
                        await api.send_group_msg(group_id=group_id, message=result["response"])
                    add_to_history(user_id, clean_content, "user")
                    add_to_history(user_id, result["response"], "assistant")
                    return
                # 发送更新日志
                if clean_content == '/log':
                    update_data = ''
                    for update_time in update_log.keys():
                        update_data += f'更新时间：{update_log[update_time].get('time')}\n更新内容：{update_log[update_time].get('content')}\n'

                    result = {'response': update_data}
                else:
                    # LLM处理
                    result = await chat_agent(clean_content, user_id=user_id, group_id=group_id)

                # 发送文本回复
                if result["response"]:
                    await api.send_group_msg(group_id=group_id, message=result["response"])

                # 发送Pixiv图片
                if result.get("pixiv_images"):
                    for img_path in result["pixiv_images"]:
                        try:
                            # 转换为绝对路径
                            abs_path = os.path.abspath(img_path)
                            logger.info(f"发送Pixiv图片，绝对路径: {abs_path}")
                            img_msg = [MessageSegment.image(file=abs_path)]
                            await api.send_group_msg(group_id=group_id, message=img_msg)
                        except Exception as e:
                            logger.error(f"发送Pixiv图片失败: {e}")

                # 发送表情包（30%概率）
                if result["emoji_path"]:
                    emoji_msg = [MessageSegment.image(file=result["emoji_path"])]
                    await api.send_group_msg(group_id=group_id, message=emoji_msg)

                # 记录历史
                add_to_history(user_id, clean_content, "user")
                if result["response"]:
                    add_to_history(user_id, result["response"], "assistant")

            except Exception as e:
                logger.error(e)


def parse_message(message) -> str:
    if isinstance(message, str):
        return message

    if isinstance(message, list):
        result = []
        print(message)
        for seg in message:
            msg_type = seg.get("type")
            if msg_type == "text":
                result.append(seg.get("data", {}).get("text", ""))
            elif msg_type == "image":
                result.append(f"[图片]{seg.get('data')['url']}")
            elif msg_type == "face":
                result.append(f"[表情]{seg.get("data")['id']}")
            elif msg_type == "record":
                result.append("[语音]")
            elif msg_type == "video":
                result.append("[视频]")
            elif msg_type == "at":
                qq = seg.get("data", {}).get("qq", "")
                result.append(f"@{qq}")
            elif msg_type == "reply":
                result.append("[回复]")
            else:
                result.append(f"[{msg_type}]")
        return "".join(result)

    return str(message)


async def main():
    logger.info("启动 QQ Bot...")
    await connect_napcat()


def get_message_counter():
    """获取当前消息计数器值"""
    global message_counter
    return message_counter


def reset_message_counter():
    """重置消息计数器为0"""
    global message_counter
    message_counter = 0
    logger.info("消息计数器已重置为0")


if __name__ == "__main__":
    # 创建并配置活动检查器
    checker = create_activity_checker(
        api=api,
        groups=check_activity_level_group,
        message_counter_getter=get_message_counter,
        message_counter_resetter=reset_message_counter,
        llm_chat_func=chat_agent
    )
    # 启动定时任务（非阻塞）
    checker.start()
    asyncio.run(main())
