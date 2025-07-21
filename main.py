import os
import json
import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.provider import ProviderRequest
import astrbot.api.message_components as Comp

@register(
    "astrbot_plugin_gender_detector",
    "xSapientia",
    "智能识别用户性别并自动添加到LLM提示词的插件",
    "0.0.1",
    "https://github.com/xSapientia/astrbot_plugin_gender_detector"
)
class GenderDetectorPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.plugin_data_dir = Path("data/plugin_data/astrbot_plugin_gender_detector")
        self.plugin_data_dir.mkdir(parents=True, exist_ok=True)

        # 缓存文件路径
        self.user_cache_file = self.plugin_data_dir / "user_cache.json"
        self.user_cache: Dict[str, Dict] = self._load_cache()

        # 启动每日扫描任务
        if self.config.get("scan_settings", {}).get("enable_daily_scan", True):
            asyncio.create_task(self._daily_scan_task())

        logger.info("astrbot_plugin_gender_detector 插件已加载")

    def _load_cache(self) -> Dict:
        """加载缓存文件"""
        if self.user_cache_file.exists():
            try:
                with open(self.user_cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载缓存失败: {e}")
        return {}

    def _save_cache(self):
        """保存缓存文件"""
        try:
            with open(self.user_cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.user_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")

    def _is_cache_valid(self, cache_time: str) -> bool:
        """检查缓存是否有效"""
        try:
            cache_datetime = datetime.fromisoformat(cache_time)
            valid_days = self.config.get("cache_settings", {}).get("cache_valid_days", 7)
            return datetime.now() - cache_datetime < timedelta(days=valid_days)
        except:
            return False

    async def _get_user_info(self, event: AstrMessageEvent, user_id: str) -> Optional[Dict]:
        """获取用户信息"""
        # 先检查缓存
        if user_id in self.user_cache:
            cache_data = self.user_cache[user_id]
            if self._is_cache_valid(cache_data.get("cache_time", "")):
                if self.config.get("debug_settings", {}).get("show_debug", False):
                    logger.debug(f"从缓存获取用户信息: {user_id}")
                return cache_data

        # 根据平台获取用户信息
        platform_name = event.get_platform_name()
        user_info = None

        if platform_name == "aiocqhttp":
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
            if isinstance(event, AiocqhttpMessageEvent):
                try:
                    # 获取用户信息
                    ret = await event.bot.api.call_action('get_stranger_info', user_id=int(user_id))
                    if ret and ret.get("status") == "ok":
                        data = ret.get("data", {})
                        user_info = {
                            "user_id": user_id,
                            "nickname": data.get("nickname", ""),
                            "age": data.get("age", 0),
                            "sex": data.get("sex", "unknown"),
                            "birthday": self._parse_birthday(data.get("age", 0)),
                            "cache_time": datetime.now().isoformat()
                        }

                        # 如果是群消息，获取群信息
                        if event.get_group_id():
                            group_ret = await event.bot.api.call_action(
                                'get_group_member_info',
                                group_id=int(event.get_group_id()),
                                user_id=int(user_id)
                            )
                            if group_ret and group_ret.get("status") == "ok":
                                group_data = group_ret.get("data", {})
                                user_info.update({
                                    "card": group_data.get("card", ""),
                                    "title": group_data.get("title", "")
                                })
                except Exception as e:
                    logger.error(f"获取用户信息失败: {e}")

        # 更新缓存
        if user_info:
            self.user_cache[user_id] = user_info
            self._save_cache()

        return user_info

    def _parse_birthday(self, age: int) -> str:
        """根据年龄推算生日年份"""
        if age > 0:
            birth_year = datetime.now().year - age
            return f"{birth_year}年"
        return "未知"

    async def _scan_group_members(self, event: AstrMessageEvent, group_id: str):
        """扫描群成员信息"""
        platform_name = event.get_platform_name()

        if platform_name == "aiocqhttp":
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
            if isinstance(event, AiocqhttpMessageEvent):
                try:
                    ret = await event.bot.api.call_action('get_group_member_list', group_id=int(group_id))
                    if ret and ret.get("status") == "ok":
                        members = ret.get("data", [])
                        for member in members:
                            user_id = str(member.get("user_id"))
                            user_info = {
                                "user_id": user_id,
                                "nickname": member.get("nickname", ""),
                                "card": member.get("card", ""),
                                "title": member.get("title", ""),
                                "age": member.get("age", 0),
                                "sex": member.get("sex", "unknown"),
                                "birthday": self._parse_birthday(member.get("age", 0)),
                                "cache_time": datetime.now().isoformat()
                            }
                            self.user_cache[user_id] = user_info

                        self._save_cache()
                        logger.info(f"群 {group_id} 成员扫描完成，共扫描 {len(members)} 人")
                except Exception as e:
                    logger.error(f"扫描群成员失败: {e}")

    async def _analyze_history_messages(self, event: AstrMessageEvent):
        """分析历史消息识别称呼"""
        # 获取当前会话的历史对话
        uid = event.unified_msg_origin
        curr_cid = await self.context.conversation_manager.get_curr_conversation_id(uid)

        if not curr_cid:
            return

        conversation = await self.context.conversation_manager.get_conversation(uid, curr_cid)
        if not conversation:
            return

        try:
            history = json.loads(conversation.history)
            history_count = self.config.get("history_settings", {}).get("history_count", 100)

            # 分析最近的历史消息
            for msg in history[-history_count:]:
                content = msg.get("content", "")
                # 识别@和称呼
                self._extract_nicknames(content)

        except Exception as e:
            logger.error(f"分析历史消息失败: {e}")

    def _extract_nicknames(self, content: str):
        """从内容中提取称呼"""
        # 提取@的用户
        at_pattern = r'@(\S+)'
        at_matches = re.findall(at_pattern, content)

        # TODO: 这里可以添加更复杂的称呼识别逻辑
        # 比如通过NLP识别"小明说"、"告诉小红"等模式

        for nickname in at_matches:
            # 更新到缓存中的nicknames字段
            pass

    def _get_sex_text(self, sex: str) -> str:
        """转换性别文本"""
        sex_map = {
            "male": "男",
            "female": "女",
            "unknown": "未知"
        }
        return sex_map.get(sex, "未知")

    async def _inject_user_info_to_prompt(self, event: AstrMessageEvent, req: ProviderRequest):
        """注入用户信息到提示词"""
        if not self.config.get("prompt_settings", {}).get("enable_prompt_inject", True):
            return

        # 获取发送者信息
        sender_id = event.get_sender_id()
        sender_info = await self._get_user_info(event, sender_id)

        inject_parts = []

        # 统计涉及的用户
        if self.config.get("prompt_settings", {}).get("insert_user_count", True):
            # 分析消息中的@和称呼
            message_str = event.message_str
            mentioned_users = set()

            # 查找@
            at_pattern = r'@(\S+)'
            at_matches = re.findall(at_pattern, message_str)
            mentioned_users.update(at_matches)

            if mentioned_users:
                inject_parts.append(f"[本次对话涉及 {len(mentioned_users) + 1} 位用户]")

        # 插入发送者信息
        if self.config.get("prompt_settings", {}).get("insert_sender_info", True) and sender_info:
            sender_desc = f"[发送者: {sender_info.get('nickname', '未知')}({sender_id})"
            if sender_info.get('title'):
                sender_desc += f", 头衔: {sender_info['title']}"
            if sender_info.get('card'):
                sender_desc += f", 群名片: {sender_info['card']}"
            sender_desc += f", 性别: {self._get_sex_text(sender_info.get('sex', 'unknown'))}"
            if sender_info.get('age', 0) > 0:
                sender_desc += f", 年龄: {sender_info['age']}"
            sender_desc += "]"
            inject_parts.append(sender_desc)

        # 注入到system_prompt前面
        if inject_parts:
            prefix = "\n".join(inject_parts) + "\n\n"
            req.system_prompt = prefix + req.system_prompt

            if self.config.get("debug_settings", {}).get("show_debug", False):
                logger.debug(f"注入用户信息: {prefix}")

    async def _daily_scan_task(self):
        """每日扫描任务"""
        while True:
            try:
                # 获取配置的扫描时间
                scan_time = self.config.get("scan_settings", {}).get("scan_time", "03:00")
                hour, minute = map(int, scan_time.split(":"))

                # 计算下次扫描时间
                now = datetime.now()
                next_scan = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

                if next_scan <= now:
                    next_scan += timedelta(days=1)

                wait_seconds = (next_scan - now).total_seconds()
                await asyncio.sleep(wait_seconds)

                # 执行扫描
                logger.info("开始执行每日群成员扫描")
                # TODO: 获取所有已加入的群并扫描

            except Exception as e:
                logger.error(f"每日扫描任务出错: {e}")
                await asyncio.sleep(3600)  # 出错后等待1小时

    @filter.command("gender", alias={"性别"})
    async def cmd_gender(self, event: AstrMessageEvent):
        """查看用户性别信息"""
        # 检查消息中是否有@
        target_users = []

        # 查找@的用户
        for comp in event.message_obj.message:
            if isinstance(comp, Comp.At):
                target_users.append(str(comp.qq))

        # 如果没有@，则查看发送者自己
        if not target_users:
            target_users.append(event.get_sender_id())

        results = []
        for user_id in target_users:
            user_info = await self._get_user_info(event, user_id)
            if user_info:
                sex_text = self._get_sex_text(user_info.get("sex", "unknown"))
                result = f"{user_info.get('nickname', '未知')}({user_id}): {sex_text}"
                if user_info.get("age", 0) > 0:
                    result += f", {user_info['age']}岁"
                results.append(result)
            else:
                results.append(f"用户({user_id}): 信息获取失败")

        yield event.plain_result("\n".join(results))

    @filter.command("gender_scan", alias={"gscan", "群扫描"})
    async def cmd_scan(self, event: AstrMessageEvent):
        """主动扫描群成员"""
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("该指令仅在群聊中可用")
            return

        yield event.plain_result("开始扫描群成员信息...")

        await self._scan_group_members(event, group_id)

        # 统计性别信息
        male_count = 0
        female_count = 0
        unknown_count = 0

        for user_data in self.user_cache.values():
            sex = user_data.get("sex", "unknown")
            if sex == "male":
                male_count += 1
            elif sex == "female":
                female_count += 1
            else:
                unknown_count += 1

        stats = f"扫描完成！统计信息:\n男性: {male_count} 人\n女性: {female_count} 人\n未知: {unknown_count} 人"
        yield event.plain_result(stats)

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        """在LLM请求时注入用户信息"""
        await self._inject_user_info_to_prompt(event, req)

    @filter.on_astrbot_loaded()
    async def on_loaded(self):
        """AstrBot加载完成时"""
        logger.info("GenderDetector: AstrBot已加载完成")

    async def terminate(self):
        """插件卸载时的清理工作"""
        # 保存缓存
        self._save_cache()

        # 根据配置决定是否删除数据
        if self.config.get("cleanup_settings", {}).get("delete_plugin_data", False):
            try:
                import shutil
                shutil.rmtree(self.plugin_data_dir)
                logger.info("已删除插件数据目录")
            except Exception as e:
                logger.error(f"删除插件数据失败: {e}")

        if self.config.get("cleanup_settings", {}).get("delete_config", False):
            try:
                config_file = Path(f"data/config/astrbot_plugin_gender_detector_config.json")
                if config_file.exists():
                    config_file.unlink()
                    logger.info("已删除插件配置文件")
            except Exception as e:
                logger.error(f"删除配置文件失败: {e}")

        logger.info("astrbot_plugin_gender_detector 插件已卸载")
