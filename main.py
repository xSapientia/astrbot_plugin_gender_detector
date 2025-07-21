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
    "0.0.2",
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
        self.manual_gender_file = self.plugin_data_dir / "manual_gender.json"  # 新增：手动设置的性别

        # 加载缓存
        self.user_cache = self._load_cache()
        self.nickname_priorities = self._load_nickname_priorities()
        self.manual_genders = self._load_manual_genders()  # 新增：加载手动设置的性别

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

    def _load_manual_genders(self) -> Dict[str, str]:
        """加载手动设置的性别"""
        if self.manual_gender_file.exists():
            try:
                with open(self.manual_gender_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载手动性别设置失败: {e}")
        return {}

    def _save_manual_genders(self):
        """保存手动设置的性别"""
        try:
            with open(self.manual_gender_file, 'w', encoding='utf-8') as f:
                json.dump(self.manual_genders, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存手动性别设置失败: {e}")

    def _parse_gender(self, sex_value, user_id: str = None) -> str:
        """解析性别值"""
        self._debug_log(f"解析性别值: {sex_value}, 类型: {type(sex_value)}")

        # 首先检查手动设置的性别
        if user_id and user_id in self.manual_genders:
            manual_gender = self.manual_genders[user_id]
            self._debug_log(f"使用手动设置的性别: {manual_gender}")
            return manual_gender

        # 处理 None 或空值
        if sex_value is None or sex_value == "":
            return "未知"

        # 转换为字符串进行比较
        sex_str = str(sex_value).lower().strip()

        # 处理 "unknown" 的情况
        if sex_str in ["unknown", "未知", "保密"]:
            return "未知"

        # 数字形式 (QQ API 标准)
        if sex_str == "1":
            return "男"
        elif sex_str == "2":
            return "女"
        elif sex_str == "0":
            return "未设置"

        # 字符串形式
        if sex_str in ["male", "m", "男", "男性", "man", "boy"]:
            return "男"
        elif sex_str in ["female", "f", "女", "女性", "woman", "girl"]:
            return "女"

        return "未知"

    async def _get_user_info_from_platform(self, event: AstrMessageEvent, user_id: str) -> Optional[Dict]:
        """从平台获取用户信息"""
        if event.get_platform_name() == "aiocqhttp":
            try:
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                if isinstance(event, AiocqhttpMessageEvent):
                    client = event.bot

                    # 尝试多种方式获取用户信息
                    user_info = None

                    # 如果在群聊中，优先使用 get_group_member_info
                    if event.get_group_id():
                        try:
                            member_info = await client.api.call_action(
                                'get_group_member_info',
                                group_id=int(event.get_group_id()),
                                user_id=int(user_id)
                            )
                            user_info = member_info
                            self._debug_log(f"通过 get_group_member_info 获取: {json.dumps(member_info, ensure_ascii=False)}")
                        except Exception as e:
                            self._debug_log(f"get_group_member_info 失败: {e}")

                    # 如果群成员信息获取失败或在私聊中，尝试 get_stranger_info
                    if not user_info:
                        try:
                            stranger_info = await client.api.call_action('get_stranger_info', user_id=int(user_id))
                            user_info = stranger_info
                            self._debug_log(f"通过 get_stranger_info 获取: {json.dumps(stranger_info, ensure_ascii=False)}")
                        except Exception as e:
                            self._debug_log(f"get_stranger_info 失败: {e}")

                    if not user_info:
                        return None

                    # 提取性别信息
                    sex_value = user_info.get("sex", "unknown")
                    gender = self._parse_gender(sex_value, user_id)

                    # 获取昵称，优先使用群名片
                    nickname = user_info.get("card", "") or user_info.get("nickname", "未知")

                    # 提取群头衔（如果有）
                    title = user_info.get("title", "")

                    return {
                        "user_id": user_id,
                        "nickname": nickname,
                        "card": user_info.get("card", ""),
                        "title": title,
                        "gender": gender,
                        "raw_sex": sex_value,
                        "role": user_info.get("role", "member"),
                        "update_time": datetime.now().isoformat()
                    }

            except Exception as e:
                self._debug_log(f"获取用户 {user_id} 信息失败: {str(e)}")
                logger.error(f"获取用户信息异常: {type(e).__name__}: {str(e)}")
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

                    self._debug_log(f"API返回群成员数: {len(members)}")

                    for idx, member in enumerate(members):
                        user_id = str(member.get("user_id"))
                        sex_value = member.get("sex", "unknown")
                        gender = self._parse_gender(sex_value, user_id)

                        # 仅对前3个用户输出详细调试信息
                        if idx < 3 and self.config.get("show_debug_info", False):
                            self._debug_log(f"成员{idx+1} - ID:{user_id}, 性别原始值:{sex_value}, 解析后:{gender}")

                        # 获取最佳昵称（优先级：群头衔 > 群名片 > 昵称）
                        title = member.get("title", "")
                        card = member.get("card", "")
                        nickname = member.get("nickname", "未知")

                        display_name = title or card or nickname

                        scanned_users[user_id] = {
                            "user_id": user_id,
                            "nickname": nickname,
                            "card": card,
                            "title": title,
                            "display_name": display_name,
                            "gender": gender,
                            "raw_sex": sex_value,
                            "role": member.get("role", "member"),
                            "update_time": datetime.now().isoformat()
                        }

                        # 更新缓存
                        self._update_user_cache(user_id, scanned_users[user_id])

                    self._save_cache()

                    # 统计
                    male_count = sum(1 for u in scanned_users.values() if u.get("gender") == "男")
                    female_count = sum(1 for u in scanned_users.values() if u.get("gender") == "女")
                    unknown_count = sum(1 for u in scanned_users.values() if u.get("gender") in ["未知", "未设置"])

                    self._debug_log(f"扫描完成 - 总数:{len(scanned_users)}, 男:{male_count}, 女:{female_count}, 未知/未设置:{unknown_count}")

            except Exception as e:
                logger.error(f"扫描群成员失败: {type(e).__name__}: {str(e)}")

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
        # 优先从称呼优先级中获取
        if user_id in self.nickname_priorities and self.nickname_priorities[user_id]:
            return self.nickname_priorities[user_id][0]["nickname"]

        # 从缓存获取（优先级：群头衔 > 群名片 > 昵称）
        if user_id in self.user_cache:
            cache = self.user_cache[user_id]
            return cache.get("title") or cache.get("card") or cache.get("nickname")

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
                    # 检查缓存是否需要更新
                    if self._should_update_cache(user_info):
                        new_info = await self._get_user_info_from_platform(event, user_id)
                        if new_info:
                            user_info = new_info
                            self._update_user_cache(user_id, user_info)
                            self._save_cache()
                else:
                    user_info = await self._get_user_info_from_platform(event, user_id)
                    if user_info:
                        self._update_user_cache(user_id, user_info)
                        self._save_cache()

                if user_info:
                    gender = user_info.get("gender", "未知")
                    nickname = self._get_best_nickname(user_id) or user_info.get("nickname", "用户")

                    # 构建用户描述
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

    def _should_update_cache(self, user_info: Dict) -> bool:
        """检查是否需要更新缓存"""
        # 如果性别是未知且没有手动设置，应该尝试更新
        if user_info.get("gender") in ["未知", "未设置"]:
            user_id = user_info.get("user_id")
            if user_id and user_id not in self.manual_genders:
                return True
        return False

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

            # 构建基本信息
            if target_nickname == "你":
                result = f"你的性别是: {gender}"
            else:
                result = f"{nickname} 的性别是: {gender}"

            # 如果性别未知，提示可以手动设置
            if gender in ["未知", "未设置"] and self.config.get("manual_gender_settings", {}).get("enable_manual_set", True):
                result += "\n\n提示：性别未设置或无法获取，可以使用 /gender_set 命令手动设置"

            yield event.plain_result(result)

            # 显示称呼优先级（调试模式）
            if self.config.get("show_debug_info", False) and target_user_id in self.nickname_priorities:
                nicknames = [f"{item['nickname']}(优先级{item['priority']})"
                           for item in self.nickname_priorities[target_user_id]]
                yield event.plain_result(f"已缓存的称呼: {', '.join(nicknames)}")

            # 调试模式下显示原始数据
            if self.config.get("show_debug_info", False):
                raw_sex = user_info.get("raw_sex", "N/A")
                yield event.plain_result(f"[调试] 原始性别值: {raw_sex}")
        else:
            yield event.plain_result("无法获取用户信息，请稍后重试")

    @filter.command("gender_set", alias={"设置性别"})
    async def set_gender_manually(self, event: AstrMessageEvent, gender: str = None):
        """手动设置用户性别"""
        if not self.config.get("enable_plugin", True):
            yield event.plain_result("插件已禁用")
            return

        manual_settings = self.config.get("manual_gender_settings", {})
        if not manual_settings.get("enable_manual_set", True):
            yield event.plain_result("手动设置性别功能已禁用")
            return

        # 检查是否有 At（设置他人性别）
        target_user_id = None
        target_nickname = None

        for comp in event.message_obj.message:
            if isinstance(comp, Comp.At):
                target_user_id = str(comp.qq)
                # 检查权限
                if manual_settings.get("admin_only", True):
                    # 这里需要检查发送者是否是管理员
                    # 暂时简化处理
                    pass
                break

        # 如果没有 At，设置自己的性别
        if not target_user_id:
            target_user_id = event.get_sender_id()
            target_nickname = "你"

        # 解析性别参数
        if not gender:
            yield event.plain_result("请指定性别：男/女\n用法：/gender_set 男")
            return

        gender_lower = gender.lower().strip()
        if gender_lower in ["男", "male", "m", "男性"]:
            normalized_gender = "男"
        elif gender_lower in ["女", "female", "f", "女性"]:
            normalized_gender = "女"
        else:
            yield event.plain_result("无效的性别值，请使用：男/女")
            return

        # 保存手动设置的性别
        self.manual_genders[target_user_id] = normalized_gender
        self._save_manual_genders()

        # 更新缓存
        if target_user_id in self.user_cache:
            self.user_cache[target_user_id]["gender"] = normalized_gender
            self.user_cache[target_user_id]["update_time"] = datetime.now().isoformat()
            self._save_cache()

        # 获取昵称
        nickname = self._get_best_nickname(target_user_id) or "用户"

        if target_nickname == "你":
            yield event.plain_result(f"已设置你的性别为: {normalized_gender}")
        else:
            yield event.plain_result(f"已设置 {nickname} 的性别为: {normalized_gender}")

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
            unknown_count = sum(1 for u in scanned.values() if u.get("gender") in ["未知", "未设置"])

            result = f"扫描完成！\n"
            result += f"总人数: {len(scanned)}\n"
            result += f"男性: {male_count} 人\n"
            result += f"女性: {female_count} 人\n"
            result += f"未知/未设置: {unknown_count} 人"

            # 提示可以手动设置
            if unknown_count > 0 and self.config.get("manual_gender_settings", {}).get("enable_manual_set", True):
                result += f"\n\n提示：有 {unknown_count} 人性别未知，可使用 /gender_set 命令手动设置"

            # 调试模式下显示详细信息
            if self.config.get("show_debug_info", False) and unknown_count > 0:
                unknown_users = []
                for u in scanned.values():
                    if u.get("gender") in ["未知", "未设置"]:
                        display_name = u.get("display_name", u.get("nickname", "未知"))
                        unknown_users.append(f"{display_name}(sex={u.get('raw_sex')})")

                result += f"\n\n[调试] 未知性别用户:\n" + "\n".join(unknown_users[:10])
                if len(unknown_users) > 10:
                    result += f"\n... 还有 {len(unknown_users) - 10} 个未显示"

            yield event.plain_result(result)
        else:
            yield event.plain_result("扫描失败，请检查权限或稍后重试")

    @filter.command("gender_debug", alias={"gd", "性别调试"})
    async def debug_info(self, event: AstrMessageEvent):
        """调试命令 - 显示详细的API响应"""
        if not self.config.get("enable_plugin", True):
            yield event.plain_result("插件已禁用")
            return

        yield event.plain_result("开始诊断...")

        # 获取发送者信息
        sender_id = event.get_sender_id()

        if event.get_platform_name() == "aiocqhttp":
            try:
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                if isinstance(event, AiocqhttpMessageEvent):
                    client = event.bot

                    # 测试 get_stranger_info
                    try:
                        stranger_info = await client.api.call_action('get_stranger_info', user_id=int(sender_id))
                        yield event.plain_result(f"[get_stranger_info 响应]\n{json.dumps(stranger_info, ensure_ascii=False, indent=2)}")
                    except Exception as e:
                        yield event.plain_result(f"get_stranger_info 失败: {str(e)}")

                    # 如果在群里，测试 get_group_member_info
                    if event.get_group_id():
                        try:
                            member_info = await client.api.call_action(
                                'get_group_member_info',
                                group_id=int(event.get_group_id()),
                                user_id=int(sender_id)
                            )
                            yield event.plain_result(f"\n[get_group_member_info 响应]\n{json.dumps(member_info, ensure_ascii=False, indent=2)}")

                            # 解析性别
                            sex_value = member_info.get("sex", "unknown")
                            parsed_gender = self._parse_gender(sex_value, sender_id)
                            yield event.plain_result(f"\n[性别解析]\n原始值: {sex_value}\n解析结果: {parsed_gender}")

                        except Exception as e:
                            yield event.plain_result(f"get_group_member_info 失败: {str(e)}")

                    # 测试 get_login_info
                    try:
                        login_info = await client.api.call_action('get_login_info')
                        yield event.plain_result(f"\n[机器人信息]\n{json.dumps(login_info, ensure_ascii=False, indent=2)}")
                    except:
                        pass

                    # 显示缓存和手动设置信息
                    cache_info = "无"
                    if sender_id in self.user_cache:
                        cache_info = f"性别: {self.user_cache[sender_id].get('gender')}, 更新时间: {self.user_cache[sender_id].get('update_time')}"

                    manual_info = "无"
                    if sender_id in self.manual_genders:
                        manual_info = f"手动设置为: {self.manual_genders[sender_id]}"

                    yield event.plain_result(f"\n[本地数据]\n缓存信息: {cache_info}\n手动设置: {manual_info}")

            except Exception as e:
                yield event.plain_result(f"诊断过程出错: {str(e)}")
        else:
            yield event.plain_result(f"当前平台 {event.get_platform_name()} 不支持")

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
        self._save_manual_genders()

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
