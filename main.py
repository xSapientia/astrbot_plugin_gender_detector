import asyncio
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter
from astrbot.api.message_components import At, Plain
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, register


@register(
    "astrbot_plugin_user_info_manager",
    "xSapientia",
    "智能管理用户信息并增强LLM对话体验的插件",
    "0.0.1",
    "https://github.com/xSapientia/astrbot_plugin_user_info_manager",
)
class UserInfoManager(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.plugin_data_dir = Path("data/plugin_data/astrbot_plugin_user_info_manager")
        self.plugin_data_dir.mkdir(parents=True, exist_ok=True)

        # 缓存文件路径
        self.user_info_file = self.plugin_data_dir / "user_info.json"
        self.nickname_priority_file = self.plugin_data_dir / "nickname_priority.json"

        # 加载缓存
        self.user_info_cache = self._load_json(self.user_info_file)
        self.nickname_priority_cache = self._load_json(self.nickname_priority_file)

        # 启动定时扫描任务
        if self.config.get("enable_daily_scan", True):
            asyncio.create_task(self._daily_scan_task())

        logger.info("UserInfoManager 插件已初始化")

    def _load_json(self, file_path: Path) -> dict:
        """加载JSON文件"""
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载 {file_path} 失败: {e}")
        return {}

    def _save_json(self, data: dict, file_path: Path):
        """保存JSON文件"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存 {file_path} 失败: {e}")

    def _is_cache_valid(self, timestamp: float) -> bool:
        """检查缓存是否有效"""
        valid_days = self.config.get("cache_valid_days", 7)
        return time.time() - timestamp < valid_days * 24 * 3600

    async def _get_user_info_from_platform(self, event: AstrMessageEvent, uid: str) -> Optional[dict]:
        """从平台获取用户信息"""
        try:
            if event.get_platform_name() == "aiocqhttp":
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                if isinstance(event, AiocqhttpMessageEvent):
                    client = event.bot

                    # 获取用户信息
                    user_info = {}

                    # 获取基本信息
                    try:
                        info_resp = await client.api.call_action('get_stranger_info', user_id=int(uid))
                        if info_resp and 'data' in info_resp:
                            data = info_resp['data']
                            user_info['nickname'] = data.get('nickname', '')
                            user_info['sex'] = data.get('sex', 'unknown')
                            user_info['age'] = data.get('age', 0)
                    except:
                        pass

                    # 如果是群消息，获取群成员信息
                    if event.get_group_id():
                        try:
                            member_resp = await client.api.call_action(
                                'get_group_member_info',
                                group_id=int(event.get_group_id()),
                                user_id=int(uid)
                            )
                            if member_resp and 'data' in member_resp:
                                data = member_resp['data']
                                user_info['card'] = data.get('card', '')
                                user_info['title'] = data.get('title', '')
                                # 更新基本信息
                                user_info['nickname'] = data.get('nickname', user_info.get('nickname', ''))
                                user_info['sex'] = data.get('sex', user_info.get('sex', 'unknown'))
                                user_info['age'] = data.get('age', user_info.get('age', 0))
                        except:
                            pass

                    user_info['uid'] = uid
                    user_info['update_time'] = time.time()
                    return user_info

        except Exception as e:
            if self.config.get("show_debug_info"):
                logger.error(f"获取用户信息失败: {e}")
        return None

    async def _scan_group_members(self, event: AstrMessageEvent):
        """扫描群成员信息"""
        if not event.get_group_id():
            return

        try:
            if event.get_platform_name() == "aiocqhttp":
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                if isinstance(event, AiocqhttpMessageEvent):
                    client = event.bot
                    group_id = event.get_group_id()

                    # 获取群成员列表
                    member_list_resp = await client.api.call_action('get_group_member_list', group_id=int(group_id))
                    if member_list_resp and 'data' in member_list_resp:
                        members = member_list_resp['data']

                        for member in members:
                            uid = str(member.get('user_id', ''))
                            if uid:
                                # 更新用户信息
                                user_info = {
                                    'uid': uid,
                                    'nickname': member.get('nickname', ''),
                                    'card': member.get('card', ''),
                                    'title': member.get('title', ''),
                                    'sex': member.get('sex', 'unknown'),
                                    'age': member.get('age', 0),
                                    'update_time': time.time()
                                }
                                self.user_info_cache[uid] = user_info

                        self._save_json(self.user_info_cache, self.user_info_file)
                        if self.config.get("show_debug_info"):
                            logger.info(f"扫描群 {group_id} 完成，更新了 {len(members)} 个成员信息")

        except Exception as e:
            if self.config.get("show_debug_info"):
                logger.error(f"扫描群成员失败: {e}")

    async def _daily_scan_task(self):
        """每日扫描任务"""
        while True:
            try:
                # 计算下次扫描时间
                scan_time_str = self.config.get("daily_scan_time", "03:00")
                hour, minute = map(int, scan_time_str.split(':'))

                now = datetime.now()
                next_scan = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

                if next_scan <= now:
                    next_scan += timedelta(days=1)

                wait_seconds = (next_scan - now).total_seconds()

                if self.config.get("show_debug_info"):
                    logger.info(f"下次扫描时间: {next_scan}, 等待 {wait_seconds} 秒")

                await asyncio.sleep(wait_seconds)

                # 执行扫描
                platforms = self.context.platform_manager.get_insts()
                for platform in platforms:
                    if hasattr(platform, 'get_group_list'):
                        try:
                            # 这里需要创建一个临时事件来扫描
                            # 实际实现中可能需要其他方式
                            logger.info("开始每日扫描...")
                        except:
                            pass

            except Exception as e:
                logger.error(f"每日扫描任务出错: {e}")
                await asyncio.sleep(3600)  # 出错后等待1小时

    def _extract_users_from_message(self, message_chain: list, message_str: str) -> Set[str]:
        """从消息中提取涉及的用户"""
        users = set()

        # 提取At的用户
        for comp in message_chain:
            if isinstance(comp, At):
                users.add(str(comp.qq))

        # 从缓存的昵称中匹配
        for uid, nicknames in self.nickname_priority_cache.items():
            for nickname in nicknames:
                if nickname in message_str:
                    users.add(uid)
                    break

        return users

    def _analyze_nickname_priority(self, uid: str, message_str: str, sender_id: str) -> List[str]:
        """分析昵称优先级"""
        nicknames = self.nickname_priority_cache.get(uid, [])
        max_nicknames = self.config.get("max_nicknames", 5)

        # 从消息中提取可能的称呼
        # 这里需要更复杂的NLP处理，简化处理
        potential_nicknames = []

        # 如果是本人强调的称呼，优先级最高
        if sender_id == uid:
            # 简单的模式匹配，如"叫我xxx"
            patterns = [
                r'叫我(.{1,10})',
                r'我是(.{1,10})',
                r'称呼我(.{1,10})'
            ]
            for pattern in patterns:
                match = re.search(pattern, message_str)
                if match:
                    potential_nicknames.insert(0, match.group(1))

        # 合并昵称列表
        for nickname in potential_nicknames:
            if nickname not in nicknames:
                nicknames.insert(0, nickname)

        # 限制数量
        nicknames = nicknames[:max_nicknames]

        return nicknames

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        """在LLM请求时修改prompt"""
        if not self.config.get("enable_llm_prompt_insert", True):
            return

        try:
            # 获取发送者信息
            sender_id = event.get_sender_id()
            sender_info = await self._get_cached_user_info(event, sender_id)

            # 提取消息中涉及的用户
            users = self._extract_users_from_message(event.message_obj.message, event.message_str)

            # 构建用户信息前缀
            prefix_parts = []

            # 添加统计信息
            if users:
                prefix_parts.append(f"[本次对话涉及 {len(users)} 位用户]")

            # 添加发送者信息
            if sender_info:
                sender_desc = self._format_user_info(sender_info)
                prefix_parts.append(f"[发送者: {sender_desc}]")

            # 为消息中的用户添加信息
            modified_prompt = req.prompt
            for uid in users:
                user_info = await self._get_cached_user_info(event, uid)
                if user_info:
                    user_desc = self._format_user_info(user_info)
                    # 在@或称呼前插入信息
                    # 这里需要更复杂的处理，简化示例
                    modified_prompt = modified_prompt.replace(f"@{uid}", f"@{uid}({user_desc})")

            # 修改请求
            if prefix_parts:
                req.prompt = "\n".join(prefix_parts) + "\n" + modified_prompt
            else:
                req.prompt = modified_prompt

            if self.config.get("show_debug_info"):
                logger.info(f"LLM请求已修改，涉及用户: {users}")

        except Exception as e:
            if self.config.get("show_debug_info"):
                logger.error(f"修改LLM请求失败: {e}")

    def _format_user_info(self, user_info: dict) -> str:
        """格式化用户信息"""
        parts = []

        # 优先显示群名片和头衔
        if user_info.get('title'):
            parts.append(user_info['title'])
        if user_info.get('card'):
            parts.append(user_info['card'])
        elif user_info.get('nickname'):
            parts.append(user_info['nickname'])

        # 添加基本信息
        if user_info.get('age'):
            parts.append(f"{user_info['age']}岁")
        if user_info.get('sex') and user_info['sex'] != 'unknown':
            sex_map = {'male': '男', 'female': '女'}
            parts.append(sex_map.get(user_info['sex'], user_info['sex']))

        return '/'.join(parts)

    async def _get_cached_user_info(self, event: AstrMessageEvent, uid: str) -> Optional[dict]:
        """获取缓存的用户信息，如果缓存无效则更新"""
        cached = self.user_info_cache.get(uid)

        # 检查缓存是否有效
        if cached and self._is_cache_valid(cached.get('update_time', 0)):
            return cached

        # 更新缓存
        user_info = await self._get_user_info_from_platform(event, uid)
        if user_info:
            self.user_info_cache[uid] = user_info
            self._save_json(self.user_info_cache, self.user_info_file)

        return user_info

    @filter.command("gender", alias={'性别', 'sex'})
    async def gender_command(self, event: AstrMessageEvent):
        """查询用户性别信息"""
        # 提取目标用户
        target_users = []

        # 检查是否有At
        for comp in event.message_obj.message:
            if isinstance(comp, At):
                target_users.append(str(comp.qq))

        # 如果没有At，检查消息中的称呼
        if not target_users:
            users = self._extract_users_from_message(event.message_obj.message, event.message_str)
            target_users = list(users)

        # 如果还是没有，查询发送者自己
        if not target_users:
            target_users = [event.get_sender_id()]

        # 查询并显示信息
        results = []
        for uid in target_users:
            user_info = await self._get_cached_user_info(event, uid)
            if user_info:
                sex = user_info.get('sex', 'unknown')
                sex_map = {'male': '男', 'female': '女', 'unknown': '未知'}
                sex_str = sex_map.get(sex, sex)

                name = user_info.get('card') or user_info.get('nickname', uid)
                results.append(f"{name}: {sex_str}")
            else:
                results.append(f"{uid}: 信息获取失败")

        yield event.plain_result("\n".join(results))

    @filter.command("gender_scan", alias={'gscan', '扫描群成员'})
    async def gender_scan_command(self, event: AstrMessageEvent):
        """主动扫描群成员信息"""
        if not event.get_group_id():
            yield event.plain_result("该指令仅在群聊中可用")
            return

        yield event.plain_result("开始扫描群成员信息...")
        await self._scan_group_members(event)
        yield event.plain_result("扫描完成！")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """智能整理历史消息"""
        if not self.config.get("enable_plugin", True):
            return

        try:
            # 分析消息中的称呼
            sender_id = event.get_sender_id()
            mentioned_users = self._extract_users_from_message(event.message_obj.message, event.message_str)

            # 更新昵称优先级
            for uid in mentioned_users:
                nicknames = self._analyze_nickname_priority(uid, event.message_str, sender_id)
                if nicknames:
                    self.nickname_priority_cache[uid] = nicknames

            # 定期保存
            if hasattr(self, '_last_save_time'):
                if time.time() - self._last_save_time > 60:  # 每分钟保存一次
                    self._save_json(self.nickname_priority_cache, self.nickname_priority_file)
                    self._last_save_time = time.time()
            else:
                self._last_save_time = time.time()

        except Exception as e:
            if self.config.get("show_debug_info"):
                logger.error(f"处理消息失败: {e}")

    async def terminate(self):
        """插件卸载时的清理工作"""
        try:
            # 保存缓存
            self._save_json(self.user_info_cache, self.user_info_file)
            self._save_json(self.nickname_priority_cache, self.nickname_priority_file)

            # 如果配置要求删除数据
            if self.config.get("delete_on_uninstall", False):
                import shutil
                shutil.rmtree(self.plugin_data_dir, ignore_errors=True)

                # 删除配置文件
                config_file = Path("data/config/astrbot_plugin_user_info_manager_config.json")
                if config_file.exists():
                    config_file.unlink()

                logger.info("已删除所有插件数据")

            logger.info("UserInfoManager 插件已卸载")

        except Exception as e:
            logger.error(f"插件卸载时出错: {e}")
