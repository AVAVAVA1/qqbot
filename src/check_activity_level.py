from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, time, timedelta
import random
import time as tm
import asyncio
from typing import Optional, List, Callable
from loguru import logger


class ActivityChecker:
    """活动检查器 - 定时任务管理类"""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.is_running = False
        self.delay_seconds = None
        self.active = False
        self.check = False
        self.api = None  # API客户端，用于发送消息
        self.check_activity_level_group: List[int] = []  # 需要检查的群组列表
        self.get_message_counter: Optional[Callable] = None  # 获取消息计数器的函数
        self.reset_message_counter: Optional[Callable] = None  # 重置消息计数器的函数
        self.llm_chat_func: Optional[Callable] = None  # LLM聊天函数

    def set_api(self, api):
        """设置API客户端"""
        self.api = api

    def set_groups(self, groups: List[int]):
        """设置需要检查的群组"""
        self.check_activity_level_group = groups

    def set_message_counter_getter(self, getter: Callable):
        """设置获取消息计数器的函数"""
        self.get_message_counter = getter

    def set_message_counter_resetter(self, resetter: Callable):
        """设置重置消息计数器的函数"""
        self.reset_message_counter = resetter

    def set_llm_chat_func(self, chat_func: Callable):
        """设置LLM聊天函数"""
        self.llm_chat_func = chat_func

    async def my_task(self):
        """实际执行的任务 - 暖场话语"""
        try:
            # 获取当前消息计数
            message_counter = self.get_message_counter() if self.get_message_counter else 0

            # 计算活跃度
            if self.delay_seconds and self.delay_seconds > 0:
                activity_level = message_counter / self.delay_seconds
            else:
                activity_level = 0

            # 判断活跃度
            if activity_level < (5 / 3600):
                self.active = False
            else:
                self.active = True

            logger.info(f"任务执行于: {datetime.now()}, 活跃度: {activity_level:.6f}, 消息数: {message_counter}")

            # 如果活跃度低，发送暖场话语
            if not self.active and self.api and self.llm_chat_func:
                await self._send_warm_up_message()

            self.check = True

            # 重置消息计数器
            if self.reset_message_counter:
                self.reset_message_counter()

            # 安排下一次任务
            self.schedule_next_task()

            return 'check_activity_level'
        except Exception as e:
            logger.error(f"my_task 执行出错: {e}")
            # 即使出错也安排下一次
            self.schedule_next_task()
            return 'check_activity_level_error'

    async def _send_warm_up_message(self):
        """发送暖场话语"""
        if not self.check_activity_level_group:
            return

        # 构建提示词，让LLM生成暖场话语
        warm_up_prompt = """你是一只可爱的赛马娘，名字叫oguri。群里现在很冷清，你想说点什么来活跃气氛。

请以"怎么没人说话喵~"开头，然后加上一些可爱、俏皮的话语来暖场。可以：
- 分享一个有趣的话题
- 问问大家在做什么
- 撒个娇吸引注意
- 或者随便说点可爱的废话

要求：
1. 必须以"怎么没人说话喵~"开头
2. 语气要可爱，适当加"喵"等语气词和颜文字
3. 内容要有趣，能吸引大家聊天

请直接输出你想说的话："""

        try:
            # 调用LLM生成暖场话语
            result = await self.llm_chat_func(warm_up_prompt, user_id=3806541446)
            warm_message = result.get("response", "怎么没人说话喵~")

            # 向所有配置的群组发送消息
            for group_id in self.check_activity_level_group:
                try:
                    await self.api.send_group_msg(group_id=group_id, message=warm_message)
                    logger.info(f"已向群 {group_id} 发送暖场消息")
                except Exception as e:
                    logger.error(f"向群 {group_id} 发送暖场消息失败: {e}")

        except Exception as e:
            logger.error(f"生成或发送暖场消息失败: {e}")

    async def rest_reminder(self):
        """休息提醒任务 - 晚安问候"""
        try:
            logger.info(f"休息提醒执行于: {datetime.now()}")

            if not self.api or not self.llm_chat_func:
                logger.warning("API或LLM函数未设置，无法发送晚安问候")
                return 'remind resting skipped'

            # 构建提示词，让LLM生成晚安问候
            goodnight_prompt = """你是一只可爱的赛马娘，名字叫oguri。现在已经是深夜了（23:30），你要跟大家说晚安。

请生成一段温馨的晚安问候语，可以：
- 提醒大家该休息了
- 祝大家做个好梦
- 表达一下对大家的不舍（因为要去睡觉了）
- 说明天再见

要求：
1. 语气要温柔可爱，适当加"喵"等语气词
2. 要有关心大家身体健康的感觉
3. 不要太长，2-3句话即可
4. 可以带一点依依不舍的感觉

请直接输出晚安问候："""

            # 调用LLM生成晚安问候
            result = await self.llm_chat_func(goodnight_prompt, user_id=3806541446)
            goodnight_message = result.get("response", "该休息了喵~ 大家晚安，做个好梦！")

            # 向所有配置的群组发送晚安问候
            for group_id in self.check_activity_level_group:
                try:
                    await self.api.send_group_msg(group_id=group_id, message=goodnight_message)
                    logger.info(f"已向群 {group_id} 发送晚安问候")
                except Exception as e:
                    logger.error(f"向群 {group_id} 发送晚安问候失败: {e}")

            return 'remind resting'
        except Exception as e:
            logger.error(f"rest_reminder 执行出错: {e}")
            return 'remind resting error'

    def calculate_next_run(self):
        """计算下一次任务执行时间（当前时间 + 3-5小时随机）"""
        now = datetime.now()
        # 随机生成 3-5 小时（以秒为单位）
        random_hours = random.uniform(3, 5)
        self.delay_seconds = int(random_hours * 3600)  #hhh
        next_run = now + timedelta(seconds=self.delay_seconds)
        return next_run, self.delay_seconds

    def _run_async_task(self, coro):
        """运行异步任务的辅助方法"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果事件循环已经在运行，创建新任务
                asyncio.create_task(coro)
            else:
                # 如果没有运行，运行直到完成
                loop.run_until_complete(coro)
        except RuntimeError:
            # 没有事件循环，创建新的
            asyncio.run(coro)

    def schedule_next_task(self):
        """安排下一次任务"""
        next_run, delay_seconds = self.calculate_next_run()

        # 检查下一次执行时间是否在禁止时间段内（23:30 - 7:00）
        next_run_time = next_run.time()
        start_time = time(7, 0)
        end_time = time(23, 30)

        if start_time <= next_run_time < end_time:
            # 在允许的时间段内，正常安排任务
            self.scheduler.add_job(
                lambda: self._run_async_task(self.my_task()),
                'date',
                run_date=next_run
            )
            logger.info(f"下次任务安排在: {next_run}（{delay_seconds / 3600:.2f}小时后）")
        else:
            # 下一次执行时间落在禁止时间段内，推迟到第二天 7:00
            next_day = next_run + timedelta(days=1)
            next_run = next_day.replace(hour=7, minute=0, second=0, microsecond=0)
            self.scheduler.add_job(
                lambda: self._run_async_task(self.my_task()),
                'date',
                run_date=next_run
            )
            logger.info(f"下次执行时间落在休息时段，推迟到: {next_run}")

    def schedule_rest_reminder(self):
        """安排今天的休息提醒（23:30）"""
        now = datetime.now()
        reminder_time = now.replace(hour=23, minute=30, second=0, microsecond=0)

        # 如果已经过了 23:30，则安排到明天
        if now.time() >= time(23, 30):
            reminder_time += timedelta(days=1)

        self.scheduler.add_job(
            lambda: self._run_async_task(self.rest_reminder()),
            'date',
            run_date=reminder_time
        )
        logger.info(f"休息提醒安排在: {reminder_time}")

        # 安排明天的休息提醒
        next_reminder = reminder_time + timedelta(days=1)
        self.scheduler.add_job(
            self.schedule_rest_reminder,
            'date',
            run_date=next_reminder
        )

    def start(self):
        """启动定时任务"""
        if self.is_running:
            logger.info("任务已经在运行中")
            return

        self.scheduler.start()
        self.is_running = True

        # 获取当前时间
        now = datetime.now()
        current_time = now.time()
        start_time = time(7, 0)
        end_time = time(23, 30)

        # 检查当前是否在允许执行的时间范围内
        if start_time <= current_time < end_time:
            # 在允许的时间段内，安排首次任务
            logger.info(f"当前时间 {current_time} 在允许执行范围内，开始安排任务")
            self.schedule_next_task()
        else:
            # 在禁止时间段内，等到明天 7:00 再开始
            logger.info(f"当前时间 {current_time} 在休息时段，任务将在明天 7:00 开始")
            next_start = now.replace(hour=7, minute=0, second=0, microsecond=0) + timedelta(days=1)
            self.scheduler.add_job(
                lambda: self._run_async_task(self.my_task()),
                'date',
                run_date=next_start
            )

        # 安排休息提醒
        self.schedule_rest_reminder()
        logger.info("定时任务已启动")

    def stop(self):
        """停止定时任务"""
        if not self.is_running:
            logger.info("任务未在运行")
            return

        self.scheduler.shutdown()
        self.is_running = False
        logger.info("定时任务已停止")

    def run_blocking(self):
        """以阻塞方式运行（保持程序不退出）"""
        self.start()
        try:
            while True:
                tm.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            logger.info("\n程序正在关闭...")
            self.stop()


def create_activity_checker(
        api=None,
        groups: Optional[List[int]] = None,
        message_counter_getter: Optional[Callable] = None,
        message_counter_resetter: Optional[Callable] = None,
        llm_chat_func: Optional[Callable] = None
) -> ActivityChecker:
    """
    创建并配置活动检查器的工厂函数

    参数:
        api: API客户端，用于发送消息
        groups: 需要检查的群组ID列表
        message_counter_getter: 获取消息计数器的函数
        message_counter_resetter: 重置消息计数器的函数
        llm_chat_func: LLM聊天函数

    返回:
        配置好的 ActivityChecker 实例
    """
    checker = ActivityChecker()

    if api:
        checker.set_api(api)
    if groups:
        checker.set_groups(groups)
    if message_counter_getter:
        checker.set_message_counter_getter(message_counter_getter)
    if message_counter_resetter:
        checker.set_message_counter_resetter(message_counter_resetter)
    if llm_chat_func:
        checker.set_llm_chat_func(llm_chat_func)

    return checker


# 如果直接运行此文件，则演示阻塞模式
if __name__ == "__main__":
    # 创建基本的 checker（无API功能，仅打印日志）
    checker = ActivityChecker()
    checker.run_blocking()
