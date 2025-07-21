import json
import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
import re
from collections import defaultdict

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.message_components import At, Plain
from astrbot.api.platform import AiocqhttpAdapter

@register(
    "astrbot_plugin_gender_detector",
    "xSapientia",
    "识别用户性别并添加到LLM prompt的插件",
    "0.0.1",
    "https://github.com/xSapientia/astrbot_plugin_gender_detector",
)
class GenderDetectorPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.plugin_data_dir = "data/plugin_data/astrbot_plugin_gender_detector"
        self.cache_file = os.path.join(self.plugin_data_dir, "user_cache.json")
        self.scan_schedule_file = os.path.join(self.plugin_data_dir, "scan_schedule.json")

        # 确保目录存在
        os.makedirs(self.plugin_data_dir, exist_ok=True)

        # 加载缓存
        self.user_cache = self._load_cache()
        self.scan_schedule = self._load_scan_schedule()

        # 启动定时扫描任务
        if self.config.get("enable_daily_scan", True):
            asyncio.create_task(self._daily_scan_task())

        logger.info("astrbot_plugin_gender_detector 插件已初始化")

    def _load_cache(self) -> Dict:
        """加载用户缓存"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载缓存失败: {e}")
        return {}

    def _save_cache(self):
        """保存用户缓存"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.user_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")

    def _load_scan_schedule(self) -> Dict:
        """加载扫描计划"""
        if os.path.exists(self.scan_schedule_file):
            try:
                with open(self.scan_schedule_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载扫描计划失败: {e}")
        return {}

    def _save_scan_schedule(self):
        """保存扫描计划"""
        try:
            with open(self.scan_schedule_file, 'w', encoding='utf-8') as f:
                json.dump(self.scan_schedule, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存扫描计划失败: {e}")

    def _is_cache_valid(self, uid: str) -> bool:
        """检查缓存是否有效"""
        if uid not in self.user_cache:
            return False

        cache_time = self.user_cache[uid].get("cache_time")
        if not cache_time:
            return False

        cache_duration = self.config.get("cache_duration_hours", 24)
        cache_datetime = datetime.fromisoformat(cache_time)
        return datetime.now() - cache_datetime < timedelta(hours=cache_duration)

    async def _get_user_info_from_platform(self, event: AstrMessageEvent, uid: str) -> Optional[Dict]:
        """从平台获取用户信息"""
        try:
            if event.get_platform_name() == "aiocqhttp":
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                if isinstance(event, AiocqhttpMessageEvent):
                    client = event.bot

                    # 获取用户信息
                    user_info = await client.api.get_stranger_info(user_id=int(uid))

                    # 如果是群消息，获取群成员信息
                    group_info = {}
                    if event.get_group_id():
                        try:
                            member_info = await client.api.get_group_member_info(
                                group_id=int(event.get_group_id()),
                                user_id=int(uid)
                            )
                            group_info = {
                                "card": member_info.get("card", ""),
                                "title": member_info.get("title", ""),
                                "join_time": member_info.get("join_time", ""),
                                "last_sent_time": member_info.get("last_sent_time", "")
                            }
                        except:
                            pass

                    return {
                        "uid": uid,
                        "nickname": user_info.get("nickname", ""),
                        "sex": user_info.get("sex", "unknown"),
                        "age": user_info.get("age", 0),
                        "level": user_info.get("level", 0),
                        **group_info,
                        "cache_time": datetime.now().isoformat()
                    }
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
        return None

    async def _update_user_cache(self, event: AstrMessageEvent, uid: str):
        """更新用户缓存"""
        if not self._is_cache_valid(uid):
            user_info = await self._get_user_info_from_platform(event, uid)
            if user_info:
                self.user_cache[uid] = user_info
                self._save_cache()
                if self.config.get("show_debug", False):
                    logger.debug(f"更新用户缓存: {uid} -> {user_info}")

    async def _scan_group_members(self, event: AstrMessageEvent, group_id: str) -> Dict[str, int]:
        """扫描群成员信息"""
        stats = {"male": 0, "female": 0, "unknown": 0}

        try:
            if event.get_platform_name() == "aiocqhttp":
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                if isinstance(event, AiocqhttpMessageEvent):
                    client = event.bot

                    # 获取群成员列表
                    members = await client.api.get_group_member_list(group_id=int(group_id))

                    for member in members:
                        uid = str(member.get("user_id"))
                        user_info = await self._get_user_info_from_platform(event, uid)

                        if user_info:
                            self.user_cache[uid] = user_info
                            sex = user_info.get("sex", "unknown")
                            if sex == "male":
                                stats["male"] += 1
                            elif sex == "female":
                                stats["female"] += 1
                            else:
                                stats["unknown"] += 1

                    self._save_cache()

                    # 更新扫描记录
                    self.scan_schedule[group_id] = {
                        "last_scan": datetime.now().isoformat(),
                        "member_count": len(members),
                        "stats": stats
                    }
                    self._save_scan_schedule()

        except Exception as e:
            logger.error(f"扫描群成员失败: {e}")

        return stats

    async def _daily_scan_task(self):
        """每日扫描任务"""
        while True:
            try:
                scan_time = self.config.get("daily_scan_time", "03:00")
                hour, minute = map(int, scan_time.split(":"))

                now = datetime.now()
                next_scan = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

                if next_scan <= now:
                    next_scan += timedelta(days=1)

                wait_seconds = (next_scan - now).total_seconds()
                await asyncio.sleep(wait_seconds)

                # 执行扫描
                logger.info("开始执行每日群成员扫描")
                # 这里需要获取所有群列表，但需要有事件触发
                # 实际实现中可能需要保存群列表

            except Exception as e:
                logger.error(f"每日扫描任务错误: {e}")
                await asyncio.sleep(3600)  # 出错后等待1小时

    def _analyze_mentions_in_text(self, text: str) -> List[str]:
        """分析文本中提到的用户"""
        mentions = []

        # 查找@提及
        at_pattern = r'@(\S+)'
        at_matches = re.findall(at_pattern, text)
        mentions.extend(at_matches)

        # 查找可能的称呼（需要根据缓存的称呼进行匹配）
        for uid, info in self.user_cache.items():
            if "aliases" in info:
                for alias in info["aliases"]:
                    if alias in text:
                        mentions.append(info.get("nickname", uid))
                        break

        return list(set(mentions))  # 去重

    async def _analyze_history_messages(self, event: AstrMessageEvent, count: int = 100):
        """分析历史消息，提取用户称呼"""
        try:
            if event.get_platform_name() == "aiocqhttp":
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                if isinstance(event, AiocqhttpMessageEvent):
                    client = event.bot

                    # 获取历史消息
                    if event.get_group_id():
                        messages = await client.api.get_group_msg_history(
                            group_id=int(event.get_group_id()),
                            count=count
                        )
                    else:
                        # 私聊历史消息需要其他API
                        return

                    # 分析消息中的称呼
                    user_aliases = defaultdict(set)

                    for msg in messages.get("messages", []):
                        sender_id = str(msg.get("sender", {}).get("user_id", ""))
                        message_text = msg.get("message", "")

                        # 提取称呼
                        mentions = self._analyze_mentions_in_text(message_text)

                        # 更新别名缓存
                        for mention in mentions:
                            if sender_id in self.user_cache:
                                if "aliases" not in self.user_cache[sender_id]:
                                    self.user_cache[sender_id]["aliases"] = []

                                max_aliases = self.config.get("max_aliases", 5)
                                if mention not in self.user_cache[sender_id]["aliases"]:
                                    self.user_cache[sender_id]["aliases"].append(mention)
                                    self.user_cache[sender_id]["aliases"] = \
                                        self.user_cache[sender_id]["aliases"][-max_aliases:]

                    self._save_cache()

        except Exception as e:
            logger.error(f"分析历史消息失败: {e}")

    @filter.on_llm_request()
    async def modify_llm_prompt(self, event: AstrMessageEvent, req):
        """修改LLM请求的prompt"""
        if not self.config.get("enable_prompt_injection", True):
            return

        try:
            # 更新发送者缓存
            sender_id = event.get_sender_id()
            await self._update_user_cache(event, sender_id)

            # 获取发送者信息
            sender_info = self.user_cache.get(sender_id, {})

            # 分析消息中提到的用户
            mentioned_users = []
            message_text = event.message_str

            # 检查At消息
            for comp in event.message_obj.message:
                if isinstance(comp, At):
                    at_uid = str(comp.qq)
                    await self._update_user_cache(event, at_uid)
                    if at_uid in self.user_cache:
                        mentioned_users.append(self.user_cache[at_uid])

            # 分析文本中的提及
            text_mentions = self._analyze_mentions_in_text(message_text)
            for mention in text_mentions:
                for uid, info in self.user_cache.items():
                    if info.get("nickname") == mention or mention in info.get("aliases", []):
                        mentioned_users.append(info)
                        break

            # 构建用户信息描述
            user_info_prefix = []

            # 发送者信息
            if sender_info:
                sex_map = {"male": "男", "female": "女", "unknown": "未知"}
                sex = sex_map.get(sender_info.get("sex", "unknown"), "未知")

                sender_desc = f"[发送者信息: {sender_info.get('nickname', '未知')}({sender_id})"
                if sender_info.get("card"):
                    sender_desc += f", 群名片: {sender_info.get('card')}"
                if sender_info.get("title"):
                    sender_desc += f", 群头衔: {sender_info.get('title')}"
                sender_desc += f", 性别: {sex}"
                if sender_info.get("age", 0) > 0:
                    sender_desc += f", 年龄: {sender_info.get('age')}岁"
                sender_desc += "]"

                user_info_prefix.append(sender_desc)

            # 提及的用户信息
            if mentioned_users:
                user_info_prefix.append(f"[消息中提及了{len(mentioned_users)}位用户]")
                for user in mentioned_users:
                    uid = user.get("uid", "")
                    sex_map = {"male": "男", "female": "女", "unknown": "未知"}
                    sex = sex_map.get(user.get("sex", "unknown"), "未知")

                    user_desc = f"[@{user.get('nickname', '未知')}({uid}): 性别{sex}"
                    if user.get("age", 0) > 0:
                        user_desc += f", {user.get('age')}岁"
                    user_desc += "]"

                    # 在原消息中相应位置插入用户信息
                    # 这里简化处理，只在开头添加
                    user_info_prefix.append(user_desc)

            # 修改prompt
            if user_info_prefix:
                prefix = "\n".join(user_info_prefix) + "\n\n"
                req.system_prompt = prefix + req.system_prompt

                if self.config.get("show_debug", False):
                    logger.debug(f"已注入用户信息到prompt: {prefix}")

        except Exception as e:
            logger.error(f"修改LLM prompt失败: {e}")

    @filter.command("gender", alias={"性别"})
    async def gender_command(self, event: AstrMessageEvent):
        """查询用户性别"""
        try:
            target_uid = None

            # 检查是否有@
            for comp in event.message_obj.message:
                if isinstance(comp, At):
                    target_uid = str(comp.qq)
                    break

            # 如果没有@，尝试从文本中提取
            if not target_uid:
                text = event.message_str.replace("/gender", "").strip()
                text = text.replace("性别", "").strip()

                if text:
                    # 在缓存中查找匹配的用户
                    for uid, info in self.user_cache.items():
                        if info.get("nickname") == text or text in info.get("aliases", []):
                            target_uid = uid
                            break

            # 如果还是没有，查询发送者
            if not target_uid:
                target_uid = event.get_sender_id()

            # 更新缓存
            await self._update_user_cache(event, target_uid)

            # 获取用户信息
            user_info = self.user_cache.get(target_uid)

            if user_info:
                sex_map = {"male": "男性", "female": "女性", "unknown": "未知"}
                sex = sex_map.get(user_info.get("sex", "unknown"), "未知")

                result = f"用户: {user_info.get('nickname', '未知')}({target_uid})\n"
                result += f"性别: {sex}\n"

                if user_info.get("age", 0) > 0:
                    result += f"年龄: {user_info.get('age')}岁\n"

                if user_info.get("card"):
                    result += f"群名片: {user_info.get('card')}\n"

                if user_info.get("title"):
                    result += f"群头衔: {user_info.get('title')}\n"

                yield event.plain_result(result.strip())
            else:
                yield event.plain_result("未找到该用户的信息")

        except Exception as e:
            logger.error(f"查询性别失败: {e}")
            yield event.plain_result(f"查询失败: {str(e)}")

    @filter.command("gender_scan", alias={"gscan", "性别扫描"})
    async def gender_scan_command(self, event: AstrMessageEvent):
        """扫描群成员性别"""
        try:
            if not event.get_group_id():
                yield event.plain_result("该指令仅在群聊中可用")
                return

            yield event.plain_result("正在扫描群成员信息，请稍候...")

            # 执行扫描
            stats = await self._scan_group_members(event, event.get_group_id())

            # 分析历史消息
            if self.config.get("analyze_history", True):
                history_count = self.config.get("history_message_count", 100)
                await self._analyze_history_messages(event, history_count)

            # 生成统计结果
            result = f"群成员性别统计完成！\n"
            result += f"男性: {stats['male']}人\n"
            result += f"女性: {stats['female']}人\n"
            result += f"未知: {stats['unknown']}人\n"
            result += f"总计: {sum(stats.values())}人"

            yield event.plain_result(result)

        except Exception as e:
            logger.error(f"扫描群成员失败: {e}")
            yield event.plain_result(f"扫描失败: {str(e)}")

    async def terminate(self):
        """插件卸载时的清理"""
        self._save_cache()
        self._save_scan_schedule()

        # 根据配置决定是否删除数据
        if self.config.get("delete_data_on_unload", False):
            try:
                import shutil
                shutil.rmtree(self.plugin_data_dir)
                logger.info(f"已删除插件数据目录: {self.plugin_data_dir}")
            except Exception as e:
                logger.error(f"删除插件数据失败: {e}")

        # 删除配置文件
        if self.config.get("delete_config_on_unload", False):
            try:
                config_file = "data/config/astrbot_plugin_gender_detector_config.json"
                if os.path.exists(config_file):
                    os.remove(config_file)
                    logger.info(f"已删除配置文件: {config_file}")
            except Exception as e:
                logger.error(f"删除配置文件失败: {e}")

        logger.info("astrbot_plugin_gender_detector 插件已卸载")
