import os
import json
import asyncio
from typing import Dict, List, Optional, Set
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
        self.config = config

        # 初始化数据目录
        self.data_dir = Path("data/plugin_data/astrbot_plugin_gender_detector")
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 缓存文件路径
        self.cache_file = self.data_dir / "gender_cache.json"
        self.nickname_cache_file = self.data_dir / "nickname_cache.json"

        # 加载缓存
        self.gender_cache = self._load_cache(self.cache_file)
        self.nickname_cache = self._load_cache(self.nickname_cache_file)

        # 临时存储已处理的消息ID，避免重复处理
        self.processed_messages: Set[str] = set()

        # 启动异步任务
        asyncio.create_task(self._periodic_cache_save())

        if self.config.get("debug", False):
            logger.info(f"性别检测插件已启动，缓存数据: {len(self.gender_cache)} 条性别记录, {len(self.nickname_cache)} 条称呼记录")

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
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")

    async def _periodic_cache_save(self):
        """定期保存缓存"""
        while True:
            await asyncio.sleep(300)  # 每5分钟保存一次
            self._save_cache()

    async def _get_user_info_from_api(self, user_id: str, event: AstrMessageEvent) -> Optional[Dict]:
        """通过API获取用户信息"""
        if event.get_platform_name() != "aiocqhttp":
            return None

        try:
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
            if isinstance(event, AiocqhttpMessageEvent):
                client = event.bot

                # 获取群成员信息或陌生人信息
                if event.get_group_id():
                    result = await client.api.call_action(
                        'get_group_member_info',
                        group_id=event.get_group_id(),
                        user_id=user_id
                    )
                else:
                    result = await client.api.call_action(
                        'get_stranger_info',
                        user_id=user_id
                    )

                if result and 'data' in result:
                    return result['data']
        except Exception as e:
            if self.config.get("debug", False):
                logger.error(f"获取用户信息失败 {user_id}: {e}")

        return None

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

        # 从昵称或备注中推测
        nickname = user_info.get('nickname', '') or user_info.get('card', '')
        # 这里可以添加更复杂的性别推测逻辑

        return None

    def _extract_nickname_from_message(self, message: str, user_id: str) -> List[str]:
        """从消息中提取可能的称呼"""
        nicknames = []

        # 分析消息模式，寻找称呼
        # 示例模式：
        # "小明，你好" -> 提取 "小明"
        # "叫我阿凌" -> 提取 "阿凌"
        # "@某人 你是小天才" -> 提取 "小天才"

        patterns = [
            # 自我介绍模式
            (r'叫我(.{1,5})(?:吧|就好|就行)', 3),  # 优先级3：本人强调
            (r'我是(.{1,5})(?:，|。|！|$)', 3),

            # 他人称呼模式
            (r'^(.{1,5})[，,]', 2),  # 优先级2：他人称呼
            (r'@\S+\s+你?[是就]?(.{1,5})(?:吧|啊|呢|$)', 2),
        ]

        import re
        for pattern, priority in patterns:
            matches = re.findall(pattern, message)
            for match in matches:
                if match and 2 <= len(match) <= 5:  # 合理的称呼长度
                    nicknames.append((match.strip(), priority))

        return nicknames

    def _get_default_nickname(self, gender: str, persona_prompt: str = "") -> str:
        """根据性别和人格获取默认称呼"""
        # 分析人格prompt中的称呼偏好
        if "可爱" in persona_prompt or "萌" in persona_prompt:
            return "小可爱" if gender == "女" else "小哥哥"
        elif "御姐" in persona_prompt:
            return "姐姐" if gender == "女" else "先生"
        elif "傲娇" in persona_prompt:
            return "笨蛋" if gender == "女" else "家伙"
        else:
            # 默认称呼
            return "小姐姐" if gender == "女" else "小哥哥"

    @filter.on_llm_request()
    async def modify_llm_prompt(self, event: AstrMessageEvent, req: ProviderRequest):
        """在LLM请求时修改prompt添加性别和称呼信息"""
        try:
            user_id = event.get_sender_id()
            if not user_id:
                return

            # 检查是否已缓存性别信息
            if user_id not in self.gender_cache:
                user_info = await self._get_user_info_from_api(user_id, event)
                gender = self._detect_gender_from_info(user_info)
                if gender:
                    self.gender_cache[user_id] = {
                        'gender': gender,
                        'nickname': user_info.get('nickname', ''),
                        'update_time': asyncio.get_event_loop().time()
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
                    'nicknames': [(default_nickname, 1)],  # 优先级1：默认称呼
                    'selected': default_nickname
                }
                self.nickname_cache[user_id] = nickname_info

            selected_nickname = nickname_info.get('selected', '用户')

            # 修改系统提示
            gender_prompt = f"\n[用户信息: ID={user_id}, 性别={gender}, 称呼={selected_nickname}]"
            gender_prompt += f"\n请在回复时适当使用'{selected_nickname}'这个称呼。"

            req.system_prompt += gender_prompt

            if self.config.get("debug", False):
                logger.info(f"LLM请求已修改 - 用户: {user_id}, 性别: {gender}, 称呼: {selected_nickname}")

        except Exception as e:
            logger.error(f"修改LLM prompt失败: {e}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def analyze_nicknames(self, event: AstrMessageEvent):
        """分析消息中的称呼"""
        try:
            message = event.message_str
            user_id = event.get_sender_id()

            # 检查是否已处理过此消息
            msg_id = event.message_obj.message_id
            if msg_id in self.processed_messages:
                return
            self.processed_messages.add(msg_id)

            # 限制已处理消息集合大小
            if len(self.processed_messages) > 1000:
                self.processed_messages.clear()

            # 提取可能的称呼
            new_nicknames = self._extract_nickname_from_message(message, user_id)

            if new_nicknames and user_id:
                if user_id not in self.nickname_cache:
                    self.nickname_cache[user_id] = {
                        'nicknames': [],
                        'selected': None
                    }

                # 更新称呼列表
                existing = self.nickname_cache[user_id]['nicknames']
                max_nicknames = self.config.get('max_nicknames', 5)

                for nickname, priority in new_nicknames:
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
                self.nickname_cache[user_id]['nicknames'] = existing[:max_nicknames]
                self.nickname_cache[user_id]['selected'] = existing[0][0] if existing else None

                if self.config.get("debug", False):
                    logger.info(f"更新用户 {user_id} 的称呼: {existing}")

        except Exception as e:
            if self.config.get("debug", False):
                logger.error(f"分析称呼失败: {e}")

    @filter.command("gender", alias={"性别", "查看性别"})
    async def check_gender(self, event: AstrMessageEvent):
        """查看用户性别信息"""
        try:
            # 检查是否有@其他用户
            target_user_id = None
            target_nickname = None

            for comp in event.message_obj.message:
                if isinstance(comp, Comp.At):
                    target_user_id = str(comp.qq)
                    break

            # 如果没有@其他人，则查看发送者自己
            if not target_user_id:
                target_user_id = event.get_sender_id()
                target_nickname = event.get_sender_name()
            else:
                # 获取被@用户的信息
                user_info = await self._get_user_info_from_api(target_user_id, event)
                if user_info:
                    target_nickname = user_info.get('nickname', '') or user_info.get('card', '')

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

            # 构建回复
            reply = f"用户: {target_nickname or target_user_id}\n"
            reply += f"性别: {gender}\n"
            reply += f"当前称呼: {selected}\n"

            if nicknames:
                reply += "所有称呼: "
                for nick, priority in nicknames:
                    reply += f"{nick}(优先级{priority}) "

            yield event.plain_result(reply)

        except Exception as e:
            logger.error(f"查看性别信息失败: {e}")
            yield event.plain_result("查询失败，请稍后重试")

    async def terminate(self):
        """插件卸载时的清理工作"""
        self._save_cache()

        # 删除配置文件
        config_file = Path("data/config/astrbot_plugin_gender_detector_config.json")
        if config_file.exists():
            try:
                config_file.unlink()
                logger.info("已删除插件配置文件")
            except Exception as e:
                logger.error(f"删除配置文件失败: {e}")

        logger.info("astrbot_plugin_gender_detector 插件已卸载")
