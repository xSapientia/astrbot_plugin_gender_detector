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
from datetime import datetime

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
        # config 是一个 AstrBotConfig 实例，它与磁盘上的JSON文件动态链接
        self.config = config

        # 为配置对象填充默认值，但不会替换对象本身
        config_updated = False
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value
                config_updated = True

        # 如果添加了新的默认值，则保存一次，使其出现在UI中
        if config_updated:
            logger.info("性别检测插件：未找到部分配置，已写入默认值。")
            self.config.save_config()

        # 设置数据存储路径
        self.plugin_data_dir = os.path.join("data", "plugin_data", "astrbot_plugin_gender_detector")
        os.makedirs(self.plugin_data_dir, exist_ok=True)
        self.cache_file = os.path.join(self.plugin_data_dir, "gender_cache.json")

        self.gender_cache = {}
        self.nickname_cache = {}

        self._load_cache()

        logger.info("Gender Detector v0.0.1 加载成功！")
        self.cleanup_task = asyncio.create_task(self._cleanup_expired_cache())

    def _load_cache(self):
        """从文件加载缓存数据"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.gender_cache = data.get('gender_cache', {})
                    self.nickname_cache = data.get('nickname_cache', {})
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
                await asyncio.sleep(3600)

                expire_hours = self.config.get('cache_expire_hours', 168)
                if expire_hours <= 0: continue

                expire_time = datetime.now().timestamp() - (expire_hours * 3600)

                expired_users = [user_id for user_id, data in self.gender_cache.items() if data.get('last_update', 0) < expire_time]

                if expired_users:
                    for user_id in expired_users:
                        del self.gender_cache[user_id]
                    logger.debug(f"清理了 {len(expired_users)} 个过期的性别缓存")
                    self._save_cache()

            except asyncio.CancelledError:
                logger.info("缓存清理任务已取消。")
                break
            except Exception as e:
                logger.error(f"清理缓存时出错: {e}")

    async def _get_user_info_from_api(self, event: AstrMessageEvent, user_id: str) -> Optional[Dict]:
        """从API获取用户信息"""
        try:
            if event.get_platform_name() == "aiocqhttp":
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                assert isinstance(event, AiocqhttpMessageEvent)

                if event.get_group_id():
                    return await event.bot.api.get_group_member_info(group_id=event.get_group_id(), user_id=int(user_id))
                else:
                    return await event.bot.api.get_stranger_info(user_id=int(user_id))
        except Exception as e:
            if self.config.get("show_debug"):
                logger.warning(f"获取用户 {user_id} 信息失败: {e}")
            return None

    def _detect_gender_from_info(self, user_info: Dict) -> str:
        if not user_info: return "unknown"
        sex = user_info.get('sex')
        if sex in ['male', 'female']: return sex
        return "unknown"

    def _extract_nicknames_from_message(self, message: str) -> List[str]:
        """从消息中提取昵称"""
        nicknames = []
        self_patterns = [r'我[叫是](.{1,10})', r'叫我(.{1,10})', r'我的名字[是叫](.{1,10})']
        for pattern in self_patterns:
            for match in re.findall(pattern, message):
                nickname = match.strip(" .,!~")
                if 1 <= len(nickname) <= 10:
                    nicknames.append(nickname)
        return nicknames

    def _update_nickname_cache(self, user_id: str, nickname: str, source: str):
        """更新昵称缓存"""
        if user_id not in self.nickname_cache: self.nickname_cache[user_id] = []

        nicknames = self.nickname_cache[user_id]
        now = datetime.now().timestamp()

        existing_nick = next((item for item in nicknames if item['nickname'] == nickname), None)

        if existing_nick:
            existing_nick['count'] += 1
            existing_nick['last_seen'] = now
            if source == 'self' and existing_nick['source'] != 'self': existing_nick['source'] = 'self'
        else:
            nicknames.append({'nickname': nickname, 'source': source, 'count': 1, 'last_seen': now})

        nicknames.sort(key=lambda x: (x['source'] == 'self', x['count']), reverse=True)
        self.nickname_cache[user_id] = nicknames[:self.config.get('max_nicknames', 3)]
        self._save_cache()

    @filter.on_llm_request()
    async def modify_llm_prompt(self, event: AstrMessageEvent, req: ProviderRequest):
        """在LLM请求时修改prompt内容"""
        if not self.config.get("enable_plugin"): return

        try:
            user_id = event.get_sender_id()
            gender = await self._get_user_gender(event, user_id)
            gender_prompt = self.config.get(f"{gender}_prompt", self.config.get("unknown_prompt"))

            nickname_info = ""
            if user_id in self.nickname_cache and self.nickname_cache[user_id]:
                nickname_info = f" 常用昵称: {self.nickname_cache[user_id][0]['nickname']}"

            full_prompt = f"{gender_prompt}{nickname_info}"

            if self.config.get("prompt_position", "prefix") == "prefix":
                req.prompt = f"{full_prompt}\n{req.prompt}"
            else:
                req.prompt = f"{req.prompt}\n{full_prompt}"

            if self.config.get("show_debug"):
                logger.info(f"已为用户 {user_id} 添加信息: {full_prompt}")

        except Exception as e:
            logger.error(f"修改LLM请求时出错: {e}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def analyze_message_for_nicknames(self, event: AstrMessageEvent):
        """分析消息以提取昵称信息"""
        if not self.config.get("enable_plugin"): return

        try:
            for nickname in self._extract_nicknames_from_message(event.message_str):
                self._update_nickname_cache(event.get_sender_id(), nickname, 'self')
                if self.config.get("show_debug"):
                    logger.debug(f"检测到用户 {event.get_sender_id()} 的自称昵称: {nickname}")
        except Exception as e:
            logger.error(f"分析消息时出错: {e}")

    async def _get_user_gender(self, event: AstrMessageEvent, user_id: str) -> str:
        """获取用户性别，优先从缓存读取"""
        now = datetime.now().timestamp()
        expire_hours = self.config.get('cache_expire_hours', 168)

        if user_id in self.gender_cache:
            cache_data = self.gender_cache[user_id]
            if expire_hours <= 0 or now - cache_data.get('last_update', 0) < expire_hours * 3600:
                return cache_data['gender']

        user_info = await self._get_user_info_from_api(event, user_id)
        gender = self._detect_gender_from_info(user_info)

        self.gender_cache[user_id] = {'gender': gender, 'last_update': now}
        self._save_cache()
        return gender

    @filter.command("gender")
    async def check_gender(self, event: AstrMessageEvent):
        """查看用户性别"""
        at_user_id = next((str(seg.qq) for seg in event.message_obj.message if isinstance(seg, Comp.At)), None)

        target_user = at_user_id or event.get_sender_id()
        target_name = f"用户 {target_user}" if at_user_id else "你"

        gender = await self._get_user_gender(event, target_user)
        gender_text = {'male': '男性♂', 'female': '女性♀'}.get(gender, '未知')

        nickname_info = ""
        if target_user in self.nickname_cache and self.nickname_cache[target_user]:
            nicknames = [f"{n['nickname']}({n['source']})" for n in self.nickname_cache[target_user]]
            nickname_info = f"\n常用昵称: {', '.join(nicknames)}"

        response = f"{target_name}的性别是: {gender_text}{nickname_info}"

        if self.config.get("show_debug"):
            cache_status = "存在" if target_user in self.gender_cache else "不存在"
            response += f"\n\n[调试] 缓存状态: {cache_status}"

        yield event.plain_result(response)

    async def terminate(self):
        """插件卸载时清理数据"""
        try:
            if hasattr(self, 'cleanup_task') and self.cleanup_task:
                self.cleanup_task.cancel()

            self._save_cache()

            config_file = os.path.join("data", "config", "astrbot_plugin_gender_detector_config.json")
            if os.path.exists(config_file):
                os.remove(config_file)
                logger.info(f"已删除配置文件: {config_file}")

            if os.path.exists(self.plugin_data_dir):
                shutil.rmtree(self.plugin_data_dir)
                logger.info(f"已删除数据目录: {self.plugin_data_dir}")

            logger.info("astrbot_plugin_gender_detector 插件已完全卸载。")
        except Exception as e:
            logger.error(f"插件卸载时出错: {e}")
