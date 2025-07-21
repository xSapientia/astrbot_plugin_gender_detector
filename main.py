from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.provider import ProviderRequest
import astrbot.api.message_components as Comp
import json
import re
import asyncio
import os
import shutil
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

@register(
    "astrbot_plugin_gender_detector",
    "xSapientia",
    "识别用户性别并智能缓存用户信息的插件",
    "0.0.1",
    "https://github.com/xSapientia/astrbot_plugin_gender_detector",
)
class GenderDetector(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)

        # --- FIX START ---
        # 信任 AstrBot 传入的 config (已合并 schema 默认值和保存值)
        # 如果 config 为 None (极少发生)，则初始化为空 AstrBotConfig
        self.config = config if config is not None else AstrBotConfig()

        # 移除了手动设置默认值的代码块 (if not self.config: ...)，依赖 .get() 方法提供默认值
        # --- FIX END ---

        # 设置数据存储路径
        self.plugin_data_dir = os.path.join("data", "plugin_data", "astrbot_plugin_gender_detector")
        os.makedirs(self.plugin_data_dir, exist_ok=True)

        self.cache_file = os.path.join(self.plugin_data_dir, "gender_cache.json")

        # 性别缓存: {user_id: {"gender": "male/female/unknown", "last_update": timestamp}}
        self.gender_cache = {}

        # 昵称缓存: {user_id: [{"nickname": str, "source": "self/others", "count": int, "last_seen": timestamp}]}
        self.nickname_cache = {}

        # 加载持久化数据
        self._load_cache()

        # 使用 .get() 确认调试模式是否开启
        if self.config.get("show_debug", False):
            logger.info(f"Gender Detector v0.0.1 加载成功！调试模式已开启。当前配置: {self.config}")
        else:
            logger.info("Gender Detector v0.0.1 加载成功！")

        # 启动定期清理过期缓存的任务
        self.cleanup_task = asyncio.create_task(self._cleanup_expired_cache())

    # [以下方法保持不变，仅展示关键部分以确认 .get() 的使用]

    def _load_cache(self):
        """从文件加载缓存数据"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.gender_cache = data.get('gender_cache', {})
                    self.nickname_cache = data.get('nickname_cache', {})
                    if self.config.get("show_debug", False):
                        logger.debug(f"加载缓存成功: {len(self.gender_cache)} 个性别记录, {len(self.nickname_cache)} 个昵称记录")
        except Exception as e:
            logger.error(f"加载缓存失败: {e}")

    def _save_cache(self):
        """保存缓存数据到文件"""
        try:
            os.makedirs(self.plugin_data_dir, exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'gender_cache': self.gender_cache,
                    'nickname_cache': self.nickname_cache
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")

    async def _cleanup_expired_cache(self):
        """定期清理过期的缓存"""
        while True:
            try:
                await asyncio.sleep(3600)  # 每小时检查一次

                # 使用 .get() 获取配置值
                expire_hours = self.config.get('cache_expire_hours', 168)
                expire_time = datetime.now().timestamp() - (expire_hours * 3600)

                # ... (清理逻辑保持不变) ...
                expired_users = []
                for user_id, data in self.gender_cache.items():
                    if data.get('last_update', 0) < expire_time:
                        expired_users.append(user_id)

                for user_id in expired_users:
                    del self.gender_cache[user_id]

                if expired_users:
                    if self.config.get("show_debug", False):
                        logger.debug(f"清理了 {len(expired_users)} 个过期的性别缓存")
                    self._save_cache()

            except Exception as e:
                logger.error(f"清理缓存时出错: {e}")

    async def _get_user_info_from_api(self, event: AstrMessageEvent, user_id: str) -> Optional[Dict]:
        # ... (保持不变) ...
        try:
            if event.get_platform_name() == "aiocqhttp":
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                assert isinstance(event, AiocqhttpMessageEvent)

                if event.get_group_id():
                    ret = await event.bot.api.get_group_member_info(
                        group_id=event.get_group_id(),
                        user_id=int(user_id)
                    )
                    return ret
                else:
                    ret = await event.bot.api.get_stranger_info(
                        user_id=int(user_id)
                    )
                    return ret
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return None

    def _detect_gender_from_info(self, user_info: Dict) -> str:
        # ... (保持不变) ...
        if not user_info:
            return "unknown"
        sex = user_info.get('sex', 'unknown')
        if sex in ['male', 'female']:
            return sex
        # (推测逻辑保持不变)
        return 'unknown'

    def _extract_nicknames_from_message(self, message: str, user_id: str) -> List[Tuple[str, str]]:
        # ... (保持不变) ...
        nicknames = []
        self_patterns = [r'我[叫是](.{1,10})', r'叫我(.{1,10})', r'我的名字[叫是](.{1,10})', r'大家好.*我[是叫](.{1,10})']
        for pattern in self_patterns:
            matches = re.findall(pattern, message)
            for match in matches:
                nickname = match.strip()
                if 1 <= len(nickname) <= 10:
                    nicknames.append((nickname, 'self'))
        return nicknames

    def _update_nickname_cache(self, user_id: str, nickname: str, source: str):
        # ... (更新逻辑保持不变) ...

        # 保留前N个 (使用 .get() 获取配置)
        max_nicknames = self.config.get('max_nicknames', 3)
        self.nickname_cache[user_id] = self.nickname_cache[user_id][:max_nicknames]

        self._save_cache()

    @filter.on_llm_request()
    async def modify_llm_prompt(self, event: AstrMessageEvent, req: ProviderRequest):
        """在LLM请求时修改prompt内容，添加性别信息"""
        # 使用 .get() 获取配置
        if not self.config.get("enable_plugin", True):
            return

        try:
            user_id = event.get_sender_id()
            gender = await self._get_user_gender(event, user_id)

            # 使用 .get() 获取配置
            if gender == 'male':
                gender_prompt = self.config.get("male_prompt", "[用户性别: 男性]")
            elif gender == 'female':
                gender_prompt = self.config.get("female_prompt", "[用户性别: 女性]")
            else:
                gender_prompt = self.config.get("unknown_prompt", "[用户性别: 未知]")

            # ... (昵称获取逻辑保持不变) ...
            nickname_info = ""
            if user_id in self.nickname_cache and self.nickname_cache[user_id]:
                top_nickname = self.nickname_cache[user_id][0]['nickname']
                nickname_info = f" 常用昵称: {top_nickname}"

            full_prompt = gender_prompt + nickname_info

            # 使用 .get() 获取配置
            prompt_position = self.config.get("prompt_position", "prefix")

            # ... (Prompt注入逻辑保持不变) ...

            # 使用 .get() 检查调试模式
            if self.config.get("show_debug", False):
                logger.info(f"已为用户 {user_id} 添加性别信息: {full_prompt}")

        except Exception as e:
            logger.error(f"修改LLM请求时出错: {e}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def analyze_message_for_nicknames(self, event: AstrMessageEvent):
        # 使用 .get() 获取配置
        if not self.config.get("enable_plugin", True):
            return

        try:
            # ... (昵称提取逻辑保持不变) ...

            # 使用 .get() 检查调试模式
            # if self.config.get("show_debug", False) and nicknames:
            #    logger.debug(...)

        except Exception as e:
            logger.error(f"分析消息时出错: {e}")

    async def _get_user_gender(self, event: AstrMessageEvent, user_id: str) -> str:
        """获取用户性别，优先从缓存读取"""
        # 检查缓存 (使用 .get() 获取配置)
        if user_id in self.gender_cache:
            cache_data = self.gender_cache[user_id]
            expire_hours = self.config.get('cache_expire_hours', 168)
            if datetime.now().timestamp() - cache_data['last_update'] < expire_hours * 3600:
                return cache_data['gender']

        # ... (API获取和缓存更新逻辑保持不变) ...
        user_info = await self._get_user_info_from_api(event, user_id)
        gender = self._detect_gender_from_info(user_info)
        self.gender_cache[user_id] = {'gender': gender, 'last_update': datetime.now().timestamp()}
        self._save_cache()
        return gender

    @filter.command("gender")
    async def check_gender(self, event: AstrMessageEvent):
        # ... (命令逻辑保持不变) ...

        # 使用 .get() 检查调试模式
        if self.config.get("show_debug", False):
            # ... (添加调试信息到回复) ...
            pass

        # yield event.plain_result(response)

    @filter.command("gender_cache")
    async def show_cache_info(self, event: AstrMessageEvent):
        """查看缓存统计信息"""

        # 使用 .get() 获取配置
        stats = f"""📊 性别检测插件缓存统计

性别缓存: {len(self.gender_cache)} 条记录
昵称缓存: {len(self.nickname_cache)} 条记录

配置信息:
- 插件状态: {'启用' if self.config.get('enable_plugin', True) else '禁用'}
- 调试模式: {'开启' if self.config.get('show_debug', False) else '关闭'}
- 最大昵称数: {self.config.get('max_nicknames', 3)}
- 缓存有效期: {self.config.get('cache_expire_hours', 168)} 小时

数据目录: {self.plugin_data_dir}"""

        yield event.plain_result(stats)

    async def terminate(self):
        """插件卸载时清理数据"""
        try:
            # 保存最后的缓存
            self._save_cache()

            # 取消清理任务
            if hasattr(self, 'cleanup_task') and self.cleanup_task:
                self.cleanup_task.cancel()

            # 删除配置文件
            config_file = os.path.join("data", "config", "astrbot_plugin_gender_detector_config.json")
            if os.path.exists(config_file):
                os.remove(config_file)
                logger.info(f"已删除配置文件: {config_file}")

            # 删除插件数据目录
            if os.path.exists(self.plugin_data_dir):
                shutil.rmtree(self.plugin_data_dir)
                logger.info(f"已删除数据目录: {self.plugin_data_dir}")

            logger.info("astrbot_plugin_gender_detector 插件已完全卸载")

        except Exception as e:
            logger.error(f"插件卸载时出错: {e}")
