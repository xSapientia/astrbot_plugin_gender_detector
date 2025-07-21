import os
import json
import asyncio
import re
from typing import Dict, List, Optional, Set, Tuple
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.provider import ProviderRequest
import astrbot.api.message_components as Comp

@register(
    "astrbot_plugin_gender_detector",
    "xSapientia",
    "识别用户性别并在LLM请求时添加合适称呼的智能插件",
    "0.0.1",
    "https://github.com/xSapientia/astrbot_plugin_gender_detector"
)
class GenderDetectorPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)

        # 正确处理配置
        self.config = config

        # 确保配置有默认值
        self._ensure_default_config()

        # 初始化数据目录
        self.data_dir = Path("data/plugin_data/astrbot_plugin_gender_detector")
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 缓存文件路径
        self.cache_file = self.data_dir / "gender_cache.json"
        self.nickname_cache_file = self.data_dir / "nickname_cache.json"
        self.user_alias_file = self.data_dir / "user_alias.json"  # 用户别名映射

        # 加载缓存
        self.gender_cache = self._load_cache(self.cache_file)
        self.nickname_cache = self._load_cache(self.nickname_cache_file)
        self.user_alias_cache = self._load_cache(self.user_alias_file)  # 别名到user_id的映射

        # 临时存储已处理的消息ID，避免重复处理
        self.processed_messages: Set[str] = set()

        # 临时存储群成员信息
        self.group_members_cache: Dict[str, Dict[str, Dict]] = {}  # group_id -> {user_id -> info}

        # 启动异步任务
        asyncio.create_task(self._periodic_cache_save())
        asyncio.create_task(self._periodic_group_members_update())

        if self.config.get("debug", False):
            logger.info(f"性别检测插件已启动，缓存数据: {len(self.gender_cache)} 条性别记录, {len(self.nickname_cache)} 条称呼记录")
            logger.info(f"当前配置: {dict(self.config)}")

    def _ensure_default_config(self):
        """确保配置有默认值"""
        defaults = {
            "debug": False,
            "max_nicknames": 5,
            "gender_api_timeout": 5,
            "cache_expire_days": 30,
            "enable_nickname_learning": True,
            "enable_smart_user_detection": True,  # 新增：启用智能用户识别
            "default_nicknames": {
                "male": "小哥哥",
                "female": "小姐姐",
                "unknown": "朋友"
            }
        }

        # 合并默认值和用户配置
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value
            elif key == "default_nicknames" and isinstance(value, dict):
                # 特殊处理嵌套的字典
                if not isinstance(self.config[key], dict):
                    self.config[key] = value
                else:
                    for sub_key, sub_value in value.items():
                        if sub_key not in self.config[key]:
                            self.config[key][sub_key] = sub_value

        # 保存配置以确保持久化
        self.config.save_config()

    def _load_cache(self, file_path: Path) -> Dict:
        """加载缓存文件"""
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载缓存文件失败 {file_path}: {e}")
        return {}

    def _save_cache(self):
        """保存缓存到文件"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.gender_cache, f, ensure_ascii=False, indent=2)
            with open(self.nickname_cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.nickname_cache, f, ensure_ascii=False, indent=2)
            with open(self.user_alias_file, 'w', encoding='utf-8') as f:
                json.dump(self.user_alias_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")

    async def _periodic_cache_save(self):
        """定期保存缓存"""
        while True:
            await asyncio.sleep(300)  # 每5分钟保存一次
            self._save_cache()

    async def _periodic_group_members_update(self):
        """定期更新群成员信息"""
        while True:
            await asyncio.sleep(600)  # 每10分钟更新一次
            # 清理过期的群成员缓存
            self.group_members_cache.clear()

    async def _get_user_info_from_api(self, user_id: str, event: AstrMessageEvent) -> Optional[Dict]:
        """通过API获取用户信息"""
        if event.get_platform_name() != "aiocqhttp":
            return None

        try:
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
            if isinstance(event, AiocqhttpMessageEvent):
                client = event.bot

                # 使用配置的超时时间
                timeout = self.config.get("gender_api_timeout", 5)

                # 获取群成员信息或陌生人信息
                if event.get_group_id():
                    result = await asyncio.wait_for(
                        client.api.call_action(
                            'get_group_member_info',
                            group_id=event.get_group_id(),
                            user_id=user_id
                        ),
                        timeout=timeout
                    )
                else:
                    result = await asyncio.wait_for(
                        client.api.call_action(
                            'get_stranger_info',
                            user_id=user_id
                        ),
                        timeout=timeout
                    )

                if result and 'data' in result:
                    return result['data']
        except asyncio.TimeoutError:
            logger.error(f"获取用户信息超时 {user_id}")
        except Exception as e:
            if self.config.get("debug", False):
                logger.error(f"获取用户信息失败 {user_id}: {e}")

        return None

    async def _get_group_members(self, group_id: str, event: AstrMessageEvent) -> Dict[str, Dict]:
        """获取群成员列表"""
        if event.get_platform_name() != "aiocqhttp":
            return {}

        # 检查缓存
        if group_id in self.group_members_cache:
            return self.group_members_cache[group_id]

        try:
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
            if isinstance(event, AiocqhttpMessageEvent):
                client = event.bot
                result = await client.api.call_action(
                    'get_group_member_list',
                    group_id=group_id
                )

                if result and 'data' in result:
                    members = {}
                    for member in result['data']:
                        user_id = str(member.get('user_id', ''))
                        if user_id:
                            members[user_id] = member

                            # 更新别名缓存
                            nickname = member.get('nickname', '')
                            card = member.get('card', '')  # 群名片

                            if nickname:
                                self._update_user_alias(nickname, user_id)
                            if card and card != nickname:
                                self._update_user_alias(card, user_id)

                    self.group_members_cache[group_id] = members
                    return members
        except Exception as e:
            if self.config.get("debug", False):
                logger.error(f"获取群成员列表失败 {group_id}: {e}")

        return {}

    def _update_user_alias(self, alias: str, user_id: str):
        """更新用户别名映射"""
        if alias and len(alias) >= 2:  # 至少2个字符的别名才记录
            if alias not in self.user_alias_cache:
                self.user_alias_cache[alias] = []

            if user_id not in self.user_alias_cache[alias]:
                self.user_alias_cache[alias].append(user_id)

                # 限制每个别名最多对应10个user_id
                if len(self.user_alias_cache[alias]) > 10:
                    self.user_alias_cache[alias] = self.user_alias_cache[alias][-10:]

    def _detect_gender_from_info(self, user_info: Dict) -> Optional[str]:
        """从用户信息中检测性别"""
        if not user_info:
            return None

        # 检查性别字段
        gender = user_info.get('sex', '').lower()
        if gender == 'male':
            return '男'
        elif gender == 'female':
            return '女'

        return None

    async def _detect_users_in_message(self, message: str, event: AstrMessageEvent) -> List[Tuple[str, str]]:
        """智能识别消息中提到的用户
        返回: [(user_id, nickname), ...]
        """
        if not self.config.get("enable_smart_user_detection", True):
            return []

        detected_users = []

        # 获取群成员信息（如果是群聊）
        group_members = {}
        if event.get_group_id():
            group_members = await self._get_group_members(event.get_group_id(), event)

        # 模式1：直接提到昵称或群名片
        # 例如："小明说得对" "告诉阿凌一声"
        for alias, user_ids in self.user_alias_cache.items():
            if alias in message:
                # 如果是群聊，优先匹配群内成员
                if group_members:
                    for user_id in user_ids:
                        if user_id in group_members:
                            detected_users.append((user_id, alias))
                            break
                else:
                    # 私聊或无群成员信息，取第一个匹配
                    if user_ids:
                        detected_users.append((user_ids[0], alias))

        # 模式2：称呼+动作模式
        # 例如："叫小天才过来" "让班长看看"
        patterns = [
            r'叫(.{1,5})(?:过来|来|去|看|说)',
            r'让(.{1,5})(?:来|去|看|说|做)',
            r'跟(.{1,5})(?:说|讲|聊)',
            r'告诉(.{1,5})(?:一声|说)',
            r'问(.{1,5})(?:一下|看看)',
            r'找(.{1,5})(?:聊|谈|说)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, message)
            for match in matches:
                if match in self.user_alias_cache:
                    user_ids = self.user_alias_cache[match]
                    if group_members:
                        for user_id in user_ids:
                            if user_id in group_members:
                                detected_users.append((user_id, match))
                                break
                    elif user_ids:
                        detected_users.append((user_ids[0], match))

        # 去重
        seen = set()
        unique_users = []
        for user_id, nickname in detected_users:
            if user_id not in seen:
                seen.add(user_id)
                unique_users.append((user_id, nickname))

        if self.config.get("debug", False) and unique_users:
            logger.info(f"智能识别到的用户: {unique_users}")

        return unique_users

    def _extract_nickname_from_message(self, message: str, user_id: str, mentioned_users: List[str] = None) -> List[tuple]:
        """从消息中提取可能的称呼
        mentioned_users: 消息中@的用户ID列表
        """
        if not self.config.get("enable_nickname_learning", True):
            return []

        nicknames = []

        # 扩展的称呼提取模式
        patterns = [
            # 自我介绍模式
            (r'叫我(.{1,5})(?:吧|就好|就行)', 3, None),  # 优先级3：本人强调
            (r'我是(.{1,5})(?:，|。|！|$)', 3, None),
            (r'我叫(.{1,5})(?:，|。|！|$)', 3, None),

            # 他人称呼模式（需要有@）
            (r'^(.{1,5})[，,]', 2, 'at_start'),  # 优先级2：他人称呼，需要消息开头有@
            (r'(.{1,5})(?:你|您)(?:好|早|晚上好)', 2, 'has_at'),  # 需要消息中有@
        ]

        # 检查消息中是否有@
        has_at = mentioned_users is not None and len(mentioned_users) > 0

        import re
        for pattern, priority, condition in patterns:
            # 检查条件
            if condition == 'has_at' and not has_at:
                continue
            if condition == 'at_start' and not (has_at and message.find('@') < 5):
                continue

            matches = re.findall(pattern, message)
            for match in matches:
                if match and 2 <= len(match) <= 5:  # 合理的称呼长度
                    # 如果是他人对某人的称呼，需要确定是对谁
                    if priority == 2 and mentioned_users:
                        # 假设是对第一个被@的人的称呼
                        target_user = mentioned_users[0]
                        nicknames.append((match.strip(), priority, target_user))
                    else:
                        nicknames.append((match.strip(), priority, user_id))

        return nicknames

    def _get_default_nickname(self, gender: str, persona_prompt: str = "") -> str:
        """根据性别和人格获取默认称呼"""
        default_nicknames = self.config.get("default_nicknames", {})

        # 先尝试从配置获取
        if gender == "男":
            default = default_nicknames.get("male", "小哥哥")
        elif gender == "女":
            default = default_nicknames.get("female", "小姐姐")
        else:
            default = default_nicknames.get("unknown", "朋友")

        # 根据人格调整
        if "可爱" in persona_prompt or "萌" in persona_prompt:
            return "小可爱" if gender == "女" else default
        elif "御姐" in persona_prompt:
            return "姐姐" if gender == "女" else "先生"
        elif "傲娇" in persona_prompt:
            return "笨蛋" if gender == "女" else "家伙"

        return default

    @filter.on_llm_request()
    async def modify_llm_prompt(self, event: AstrMessageEvent, req: ProviderRequest):
        """在LLM请求时修改prompt添加性别和称呼信息"""
        try:
            # 获取发送者信息
            sender_id = event.get_sender_id()
            if not sender_id:
                return

            # 收集所有需要处理的用户ID
            all_user_ids = [sender_id]

            # 检查消息中@的用户
            mentioned_users = []
            for comp in event.message_obj.message:
                if isinstance(comp, Comp.At):
                    user_id = str(comp.qq)
                    if user_id not in all_user_ids:
                        all_user_ids.append(user_id)
                        mentioned_users.append(user_id)

            # 智能识别消息中提到的用户
            detected_users = await self._detect_users_in_message(event.message_str, event)
            for user_id, _ in detected_users:
                if user_id not in all_user_ids:
                    all_user_ids.append(user_id)

            # 构建用户信息字符串
            users_info = []
            cache_expire_days = self.config.get("cache_expire_days", 30)
            current_time = asyncio.get_event_loop().time()

            for user_id in all_user_ids:
                # 检查是否已缓存性别信息
                if user_id not in self.gender_cache or self._is_cache_expired(
                    self.gender_cache[user_id].get('update_time', 0),
                    cache_expire_days
                ):
                    user_info = await self._get_user_info_from_api(user_id, event)
                    gender = self._detect_gender_from_info(user_info)
                    if gender:
                        self.gender_cache[user_id] = {
                            'gender': gender,
                            'nickname': user_info.get('nickname', ''),
                            'update_time': current_time
                        }

                # 获取用户性别和称呼
                gender_info = self.gender_cache.get(user_id, {})
                gender = gender_info.get('gender', '未知')

                # 获取或生成称呼
                nickname_info = self.nickname_cache.get(user_id, {})
                if not nickname_info:
                    # 使用默认称呼
                    default_nickname = self._get_default_nickname(gender, req.system_prompt)
                    nickname_info = {
                        'nicknames': [(default_nickname, 1)],
                        'selected': default_nickname
                    }
                    self.nickname_cache[user_id] = nickname_info

                selected_nickname = nickname_info.get('selected', '用户')

                # 构建信息字符串
                role = "发送者" if user_id == sender_id else "被提及用户"
                users_info.append(f"{role}: ID={user_id}, 性别={gender}, 称呼={selected_nickname}")

            # 修改系统提示
            if users_info:
                gender_prompt = "\n[对话用户信息]\n"
                gender_prompt += "\n".join(users_info)
                gender_prompt += "\n请在回复时根据不同用户使用对应的称呼。"

                req.system_prompt += gender_prompt

                if self.config.get("debug", False):
                    logger.info(f"LLM请求已修改 - 涉及用户数: {len(all_user_ids)}")

        except Exception as e:
            logger.error(f"修改LLM prompt失败: {e}")

    def _is_cache_expired(self, update_time: float, expire_days: int) -> bool:
        """检查缓存是否过期"""
        current_time = asyncio.get_event_loop().time()
        expire_seconds = expire_days * 24 * 60 * 60
        return (current_time - update_time) > expire_seconds

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def analyze_nicknames(self, event: AstrMessageEvent):
        """分析消息中的称呼并更新用户信息"""
        if not self.config.get("enable_nickname_learning", True):
            return

        try:
            message = event.message_str
            sender_id = event.get_sender_id()

            # 检查是否已处理过此消息
            msg_id = event.message_obj.message_id
            if msg_id in self.processed_messages:
                return
            self.processed_messages.add(msg_id)

            # 限制已处理消息集合大小
            if len(self.processed_messages) > 1000:
                self.processed_messages.clear()

            # 收集被@的用户
            mentioned_users = []
            for comp in event.message_obj.message:
                if isinstance(comp, Comp.At):
                    mentioned_users.append(str(comp.qq))

            # 提取可能的称呼
            new_nicknames = self._extract_nickname_from_message(message, sender_id, mentioned_users)

            # 更新称呼信息
            for nickname, priority, target_user_id in new_nicknames:
                if target_user_id not in self.nickname_cache:
                    self.nickname_cache[target_user_id] = {
                        'nicknames': [],
                        'selected': None
                    }

                # 更新称呼列表
                existing = self.nickname_cache[target_user_id]['nicknames']
                max_nicknames = self.config.get('max_nicknames', 5)

                # 检查是否已存在
                found = False
                for i, (existing_nick, existing_priority) in enumerate(existing):
                    if existing_nick == nickname:
                        # 更新优先级
                        if priority > existing_priority:
                            existing[i] = (nickname, priority)
                        found = True
                        break

                if not found and len(existing) < max_nicknames:
                    existing.append((nickname, priority))

                # 按优先级排序并选择最高优先级的称呼
                existing.sort(key=lambda x: x[1], reverse=True)
                self.nickname_cache[target_user_id]['nicknames'] = existing[:max_nicknames]
                self.nickname_cache[target_user_id]['selected'] = existing[0][0] if existing else None

                if self.config.get("debug", False):
                    logger.info(f"更新用户 {target_user_id} 的称呼: {existing}")

            # 更新发送者的别名映射
            if sender_id:
                sender_info = await self._get_user_info_from_api(sender_id, event)
                if sender_info:
                    nickname = sender_info.get('nickname', '')
                    card = sender_info.get('card', '')
                    if nickname:
                        self._update_user_alias(nickname, sender_id)
                    if card and card != nickname:
                        self._update_user_alias(card, sender_id)

        except Exception as e:
            if self.config.get("debug", False):
                logger.error(f"分析称呼失败: {e}")

    @filter.command("gender", alias={"性别", "查看性别"})
    async def check_gender(self, event: AstrMessageEvent):
        """查看用户性别信息，支持查看多个用户"""
        try:
            # 收集所有需要查询的用户
            target_users = []  # [(user_id, nickname), ...]

            # 检查是否有@其他用户
            has_at = False
            for comp in event.message_obj.message:
                if isinstance(comp, Comp.At):
                    has_at = True
                    user_id = str(comp.qq)
                    user_info = await self._get_user_info_from_api(user_id, event)
                    nickname = '未知'
                    if user_info:
                        nickname = user_info.get('nickname', '') or user_info.get('card', '') or '未知'
                    target_users.append((user_id, nickname))

            # 如果没有@其他人，则查看发送者自己
            if not has_at:
                sender_id = event.get_sender_id()
                sender_nickname = event.get_sender_name()
                target_users.append((sender_id, sender_nickname))

            # 查询每个用户的信息
            results = []
            for target_user_id, target_nickname in target_users:
                # 获取性别信息
                if target_user_id not in self.gender_cache:
                    user_info = await self._get_user_info_from_api(target_user_id, event)
                    gender = self._detect_gender_from_info(user_info)
                    if gender:
                        self.gender_cache[target_user_id] = {
                            'gender': gender,
                            'nickname': target_nickname,
                            'update_time': asyncio.get_event_loop().time()
                        }

                gender_info = self.gender_cache.get(target_user_id, {})
                gender = gender_info.get('gender', '未知')

                # 获取称呼信息
                nickname_info = self.nickname_cache.get(target_user_id, {})
                nicknames = nickname_info.get('nicknames', [])
                selected = nickname_info.get('selected', '无')

                # 构建单个用户的回复
                user_reply = f"👤 用户: {target_nickname or target_user_id}\n"
                user_reply += f"🚻 性别: {gender}\n"
                user_reply += f"📛 当前称呼: {selected}\n"

                if nicknames:
                    user_reply += "📝 所有称呼: "
                    for nick, priority in nicknames:
                        user_reply += f"{nick}(P{priority}) "
                    user_reply += "\n"

                results.append(user_reply)

            # 构建最终回复
            if len(results) == 1:
                yield event.plain_result(results[0].strip())
            else:
                reply = f"查询到 {len(results)} 位用户的信息：\n\n"
                reply += "\n".join(results)
                yield event.plain_result(reply.strip())

        except Exception as e:
            logger.error(f"查看性别信息失败: {e}")
            yield event.plain_result("查询失败，请稍后重试")

    @filter.command("gender_reload", alias={"重载性别配置"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def reload_config(self, event: AstrMessageEvent):
        """重载配置（仅管理员）"""
        try:
            # 强制保存当前配置
            self.config.save_config()

            # 重新确保默认值
            self._ensure_default_config()

            yield event.plain_result(f"✅ 配置已重载\n当前配置: {dict(self.config)}")
        except Exception as e:
            logger.error(f"重载配置失败: {e}")
            yield event.plain_result("重载失败，请检查日志")

    @filter.command("gender_stats", alias={"性别统计"})
    async def show_stats(self, event: AstrMessageEvent):
        """显示插件统计信息"""
        try:
            total_gender = len(self.gender_cache)
            total_nickname = len(self.nickname_cache)
            total_alias = len(self.user_alias_cache)

            male_count = sum(1 for info in self.gender_cache.values() if info.get('gender') == '男')
            female_count = sum(1 for info in self.gender_cache.values() if info.get('gender') == '女')
            unknown_count = total_gender - male_count - female_count

            reply = f"📊 性别检测插件统计\n\n"
            reply += f"👥 总用户数: {total_gender}\n"
            reply += f"🚹 男性: {male_count}\n"
            reply += f"🚺 女性: {female_count}\n"
            reply += f"❓ 未知: {unknown_count}\n"
            reply += f"📛 称呼记录: {total_nickname}\n"
            reply += f"🏷️ 别名映射: {total_alias}\n"

            if event.get_group_id() and event.get_group_id() in self.group_members_cache:
                reply += f"👥 当前群缓存成员: {len(self.group_members_cache[event.get_group_id()])}"

            yield event.plain_result(reply)

        except Exception as e:
            logger.error(f"显示统计信息失败: {e}")
            yield event.plain_result("获取统计信息失败")

    async def terminate(self):
        """插件卸载时的清理工作"""
        self._save_cache()

        # 保存配置
        self.config.save_config()

        logger.info("astrbot_plugin_gender_detector 插件已卸载")
