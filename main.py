import os
import json
import asyncio
import re
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Any, Set
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.provider import ProviderRequest
import astrbot.api.message_components as Comp

@register(
    "astrbot_plugin_gender_detector",
    "xSapientia",
    "智能识别用户性别并自动添加到 LLM prompt 的插件",
    "0.0.1",
    "https://github.com/xSapientia/astrbot_plugin_gender_detector",
)
class GenderDetectorPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.plugin_data_dir = Path("data/plugin_data/astrbot_plugin_gender_detector")
        self.plugin_data_dir.mkdir(parents=True, exist_ok=True)

        # 缓存文件路径
        self.cache_file = self.plugin_data_dir / "user_cache.json"
        self.nickname_priority_file = self.plugin_data_dir / "nickname_priority.json"

        # 加载缓存
        self.user_cache = self._load_cache()
        self.nickname_priorities = self._load_nickname_priorities()

        # 扫描任务
        self.scan_task = None
        if self.config.get("enable_daily_scan", True):
            self.scan_task = asyncio.create_task(self._daily_scan_task())

        self._debug_log("插件初始化完成")

    def _debug_log(self, message: str):
        """调试日志"""
        if self.config.get("show_debug_info", False):
            logger.info(f"[GenderDetector Debug] {message}")

    def _load_cache(self) -> Dict[str, Dict]:
        """加载用户缓存"""
        if self.cache_file.exists():
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

    def _load_nickname_priorities(self) -> Dict[str, List[Dict]]:
        """加载称呼优先级"""
        if self.nickname_priority_file.exists():
            try:
                with open(self.nickname_priority_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载称呼优先级失败: {e}")
        return {}

    def _save_nickname_priorities(self):
        """保存称呼优先级"""
        try:
            with open(self.nickname_priority_file, 'w', encoding='utf-8') as f:
                json.dump(self.nickname_priorities, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存称呼优先级失败: {e}")

    async def _get_user_info_from_platform(self, event: AstrMessageEvent, user_id: str) -> Optional[Dict]:
        """从平台获取用户信息"""
        if event.get_platform_name() == "aiocqhttp":
            try:
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                if isinstance(event, AiocqhttpMessageEvent):
                    client = event.bot

                    # 获取用户信息
                    user_info = await client.api.call_action('get_stranger_info', user_id=int(user_id))

                    gender = "未知"
                    if user_info.get("sex") == "male":
                        gender = "男"
                    elif user_info.get("sex") == "female":
                        gender = "女"

                    return {
                        "user_id": user_id,
                        "nickname": user_info.get("nickname", "未知"),
                        "gender": gender,
                        "update_time": datetime.now().isoformat()
                    }
            except Exception as e:
                self._debug_log(f"获取用户 {user_id} 信息失败: {e}")
        return None

    async def _scan_group_members(self, event: AstrMessageEvent) -> Dict[str, Dict]:
        """扫描群成员信息"""
        scanned_users = {}

        if event.get_platform_name() == "aiocqhttp" and event.get_group_id():
            try:
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                if isinstance(event, AiocqhttpMessageEvent):
                    client = event.bot
                    group_id = int(event.get_group_id())

                    # 获取群成员列表
                    members = await client.api.call_action('get_group_member_list', group_id=group_id)

                    for member in members:
                        user_id = str(member.get("user_id"))
                        gender = "未知"
                        if member.get("sex") == "male":
                            gender = "男"
                        elif member.get("sex") == "female":
                            gender = "女"

                        scanned_users[user_id] = {
                            "user_id": user_id,
                            "nickname": member.get("nickname", "未知"),
                            "card": member.get("card", ""),  # 群名片
                            "gender": gender,
                            "role": member.get("role", "member"),  # owner/admin/member
                            "update_time": datetime.now().isoformat()
                        }

                        # 更新缓存
                        self._update_user_cache(user_id, scanned_users[user_id])

                    self._save_cache()
                    self._debug_log(f"扫描群 {group_id} 完成，共 {len(scanned_users)} 个成员")

            except Exception as e:
                logger.error(f"扫描群成员失败: {e}")

        return scanned_users

    def _update_user_cache(self, user_id: str, user_info: Dict):
        """更新用户缓存"""
        if user_id not in self.user_cache:
            self.user_cache[user_id] = {}

        self.user_cache[user_id].update(user_info)

        # 检查缓存过期
        cache_settings = self.config.get("cache_settings", {})
        expire_days = cache_settings.get("cache_expire_days", 30)

        if cache_settings.get("auto_clean_cache", True):
            self._clean_expired_cache(expire_days)

    def _clean_expired_cache(self, expire_days: int):
        """清理过期缓存"""
        now = datetime.now()
        expired_users = []

        for user_id, info in self.user_cache.items():
            update_time_str = info.get("update_time")
            if update_time_str:
                try:
                    update_time = datetime.fromisoformat(update_time_str)
                    if (now - update_time).days > expire_days:
                        expired_users.append(user_id)
                except:
                    pass

        for user_id in expired_users:
            del self.user_cache[user_id]
            if user_id in self.nickname_priorities:
                del self.nickname_priorities[user_id]

        if expired_users:
            self._debug_log(f"清理了 {len(expired_users)} 个过期用户缓存")

    def _extract_nicknames_from_message(self, event: AstrMessageEvent):
        """从消息中提取称呼信息"""
        message_str = event.message_str
        sender_id = event.get_sender_id()

        # 识别 @某人 的模式
        at_pattern = r'@(\S+)'
        for match in re.finditer(at_pattern, message_str):
            nickname = match.group(1)

            # 查找消息链中的 At 组件
            for comp in event.message_obj.message:
                if isinstance(comp, Comp.At):
                    target_id = str(comp.qq)
                    self._update_nickname_priority(target_id, nickname, "others", sender_id)

        # 识别自我介绍模式
        self_intro_patterns = [
            r'我[叫是](\S+)',
            r'叫我(\S+)',
            r'我的名字[叫是](\S+)',
            r'请叫我(\S+)'
        ]

        for pattern in self_intro_patterns:
            match = re.search(pattern, message_str)
            if match:
                nickname = match.group(1)
                self._update_nickname_priority(sender_id, nickname, "self", sender_id)
                self._debug_log(f"检测到用户 {sender_id} 的自我介绍: {nickname}")

    def _update_nickname_priority(self, user_id: str, nickname: str, source: str, from_user: str):
        """更新称呼优先级"""
        if user_id not in self.nickname_priorities:
            self.nickname_priorities[user_id] = []

        max_nicknames = self.config.get("max_cached_nicknames", 5)

        # 检查是否已存在
        existing = None
        for item in self.nickname_priorities[user_id]:
            if item["nickname"] == nickname:
                existing = item
                break

        if existing:
            # 更新优先级
            if source == "self":
                existing["priority"] = 1
                existing["source"] = "self"
        else:
            # 添加新称呼
            priority = 1 if source == "self" else 2 if source == "others" else 3
            self.nickname_priorities[user_id].append({
                "nickname": nickname,
                "source": source,
                "from_user": from_user,
                "priority": priority,
                "add_time": datetime.now().isoformat()
            })

        # 排序并限制数量
        self.nickname_priorities[user_id].sort(key=lambda x: x["priority"])
        self.nickname_priorities[user_id] = self.nickname_priorities[user_id][:max_nicknames]

        self._save_nickname_priorities()

    def _get_best_nickname(self, user_id: str) -> Optional[str]:
        """获取最佳称呼"""
        if user_id in self.nickname_priorities and self.nickname_priorities[user_id]:
            return self.nickname_priorities[user_id][0]["nickname"]

        # 从缓存获取默认昵称
        if user_id in self.user_cache:
            return self.user_cache[user_id].get("card") or self.user_cache[user_id].get("nickname")

        return None

    async def _daily_scan_task(self):
        """每日扫描任务"""
        while True:
            try:
                scan_time_str = self.config.get("daily_scan_time", "03:00")
                hour, minute = map(int, scan_time_str.split(":"))
                target_time = time(hour, minute)

                now = datetime.now()
                target_datetime = datetime.combine(now.date(), target_time)

                if now > target_datetime:
                    target_datetime += timedelta(days=1)

                wait_seconds = (target_datetime - now).total_seconds()
                self._debug_log(f"下次扫描时间: {target_datetime}, 等待 {wait_seconds/3600:.1f} 小时")

                await asyncio.sleep(wait_seconds)

                # 执行扫描
                logger.info("开始执行每日群成员扫描...")
                # 这里需要获取所有群并扫描，暂时跳过

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"每日扫描任务出错: {e}")
                await asyncio.sleep(3600)  # 出错后等待1小时

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest):
        """在 LLM 请求时修改 prompt"""
        if not self.config.get("enable_plugin", True):
            return

        try:
            # 从消息中提取称呼信息
            self._extract_nicknames_from_message(event)

            # 识别消息中涉及的用户
            involved_users = self._identify_involved_users(event)

            # 构建用户信息描述
            user_info_parts = []

            for user_id in involved_users:
                # 获取或更新用户信息
                user_info = None
                if user_id in self.user_cache:
                    user_info = self.user_cache[user_id]
                else:
                    user_info = await self._get_user_info_from_platform(event, user_id)
                    if user_info:
                        self._update_user_cache(user_id, user_info)
                        self._save_cache()

                if user_info:
                    gender = user_info.get("gender", "未知")
                    nickname = self._get_best_nickname(user_id) or user_info.get("nickname", "用户")

                    user_desc = f"{nickname}({gender})"
                    if user_id == event.get_sender_id():
                        user_desc = f"[发送者]{user_desc}"

                    user_info_parts.append(user_desc)

            # 添加到系统提示词
            if user_info_parts:
                user_context = f"\n当前对话涉及的用户: {', '.join(user_info_parts)}"

                # 获取默认称呼设置
                default_nickname_hint = self._get_default_nickname_hint()
                if default_nickname_hint:
                    user_context += f"\n{default_nickname_hint}"

                req.system_prompt = req.system_prompt.rstrip() + user_context

                self._debug_log(f"已添加用户信息到 prompt: {user_context}")

        except Exception as e:
            logger.error(f"处理 LLM 请求时出错: {e}")

    def _identify_involved_users(self, event: AstrMessageEvent) -> Set[str]:
        """识别消息中涉及的用户"""
        involved_users = set()

        # 添加发送者
        sender_id = event.get_sender_id()
        if sender_id:
            involved_users.add(sender_id)

        # 检查消息链中的 At
        for comp in event.message_obj.message:
            if isinstance(comp, Comp.At):
                involved_users.add(str(comp.qq))

        # 检查回复消息
        for comp in event.message_obj.message:
            if isinstance(comp, Comp.Reply):
                # 这里需要根据平台获取被回复消息的发送者
                pass

        return involved_users

    def _get_default_nickname_hint(self) -> Optional[str]:
        """获取默认称呼提示"""
        # 从当前人格设置中提取默认称呼规则
        try:
            personas = self.context.provider_manager.personas
            default_persona_name = self.context.provider_manager.selected_default_persona.get("name")

            for persona in personas:
                if persona.name == default_persona_name:
                    # 从人格描述中提取称呼规则
                    prompt = persona.prompt
                    if "称呼" in prompt or "叫" in prompt:
                        # 简单提取包含称呼的句子
                        lines = prompt.split('\n')
                        for line in lines:
                            if "称呼" in line or "叫" in line:
                                return f"称呼习惯: {line.strip()}"
        except:
            pass

        return None

    @filter.command("gender", alias={"性别"})
    async def check_gender(self, event: AstrMessageEvent):
        """查看用户性别"""
        if not self.config.get("enable_plugin", True):
            yield event.plain_result("插件已禁用")
            return

        # 检查是否有 At
        target_user_id = None
        target_nickname = None

        for comp in event.message_obj.message:
            if isinstance(comp, Comp.At):
                target_user_id = str(comp.qq)
                break

        # 如果没有 At，查看发送者自己
        if not target_user_id:
            target_user_id = event.get_sender_id()
            target_nickname = "你"

        # 获取用户信息
        user_info = None
        if target_user_id in self.user_cache:
            user_info = self.user_cache[target_user_id]
        else:
            user_info = await self._get_user_info_from_platform(event, target_user_id)
            if user_info:
                self._update_user_cache(target_user_id, user_info)
                self._save_cache()

        if user_info:
            gender = user_info.get("gender", "未知")
            nickname = self._get_best_nickname(target_user_id) or user_info.get("nickname", "用户")

            if target_nickname == "你":
                yield event.plain_result(f"你的性别是: {gender}")
            else:
                yield event.plain_result(f"{nickname} 的性别是: {gender}")

            # 显示称呼优先级（调试模式）
            if self.config.get("show_debug_info", False) and target_user_id in self.nickname_priorities:
                nicknames = [f"{item['nickname']}(优先级{item['priority']})"
                           for item in self.nickname_priorities[target_user_id]]
                yield event.plain_result(f"已缓存的称呼: {', '.join(nicknames)}")
        else:
            yield event.plain_result("无法获取用户信息，请稍后重试")

    @filter.command("gender_scan", alias={"gscan", "群扫描"})
    async def manual_scan(self, event: AstrMessageEvent):
        """手动扫描群成员"""
        if not self.config.get("enable_plugin", True):
            yield event.plain_result("插件已禁用")
            return

        if not event.get_group_id():
            yield event.plain_result("此命令仅在群聊中可用")
            return

        yield event.plain_result("开始扫描群成员信息...")

        scanned = await self._scan_group_members(event)

        if scanned:
            male_count = sum(1 for u in scanned.values() if u.get("gender") == "男")
            female_count = sum(1 for u in scanned.values() if u.get("gender") == "女")
            unknown_count = len(scanned) - male_count - female_count

            result = f"扫描完成！\n"
            result += f"总人数: {len(scanned)}\n"
            result += f"男性: {male_count} 人\n"
            result += f"女性: {female_count} 人\n"
            result += f"未知: {unknown_count} 人"

            yield event.plain_result(result)
        else:
            yield event.plain_result("扫描失败，请检查权限或稍后重试")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def extract_nicknames(self, event: AstrMessageEvent):
        """从所有消息中提取称呼信息"""
        if not self.config.get("enable_plugin", True):
            return

        try:
            self._extract_nicknames_from_message(event)
        except Exception as e:
            self._debug_log(f"提取称呼信息时出错: {e}")

    async def terminate(self):
        """插件卸载时的清理工作"""
        # 取消定时任务
        if self.scan_task:
            self.scan_task.cancel()

        # 保存缓存
        self._save_cache()
        self._save_nickname_priorities()

        # 根据配置决定是否删除数据
        cleanup_config = self.config.get("cleanup_on_uninstall", {})

        if cleanup_config.get("delete_plugin_data", False):
            try:
                import shutil
                shutil.rmtree(self.plugin_data_dir)
                logger.info("已删除插件数据目录")
            except Exception as e:
                logger.error(f"删除插件数据目录失败: {e}")

        if cleanup_config.get("delete_config", False):
            try:
                config_file = Path(f"data/config/astrbot_plugin_gender_detector_config.json")
                if config_file.exists():
                    config_file.unlink()
                    logger.info("已删除插件配置文件")
            except Exception as e:
                logger.error(f"删除配置文件失败: {e}")

        logger.info("astrbot_plugin_gender_detector 插件已卸载")
