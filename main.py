from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.provider import ProviderRequest
import json
import os
from typing import Dict, Optional
import asyncio
from datetime import datetime, timedelta

@register(
    "astrbot_plugin_gender_detector",
    "xSapientia",
    "识别用户性别并添加到LLM prompt的插件",
    "0.0.1",
    "https://github.com/yourusername/astrbot_plugin_gender_detector",
)
class GenderDetector(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config if config else AstrBotConfig()

        # 默认配置
        if not self.config:
            self.config = {
                "enable_plugin": True,
                "enable_debug": False,
                "male_prompt": "[用户性别:男性] 对方是一位男性用户",
                "female_prompt": "[用户性别:女性] 对方是一位女性用户",
                "unknown_prompt": "[用户性别:未知] 对方性别未知",
                "prompt_position": "prefix",
                "cache_expire_hours": 24,
                "enable_honorific": True,
                "male_honorific": "先生",
                "female_honorific": "女士",
                "unknown_honorific": "朋友"
            }

        # 性别缓存文件路径
        self.cache_file = os.path.join("data", "gender_cache.json")
        self.gender_cache = self._load_cache()

        logger.info("Gender Detector v1.0.0 加载成功！")
        if self.config.get("enable_debug", False):
            logger.info(f"调试模式已启用，缓存文件路径: {self.cache_file}")

    def _load_cache(self) -> Dict:
        """加载性别缓存"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                    # 清理过期缓存
                    return self._clean_expired_cache(cache)
            return {}
        except Exception as e:
            logger.error(f"加载性别缓存失败: {e}")
            return {}

    def _save_cache(self):
        """保存性别缓存"""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.gender_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存性别缓存失败: {e}")

    def _clean_expired_cache(self, cache: Dict) -> Dict:
        """清理过期的缓存项"""
        expire_hours = self.config.get("cache_expire_hours", 24)
        current_time = datetime.now()
        cleaned_cache = {}

        for user_id, info in cache.items():
            if "timestamp" in info:
                cache_time = datetime.fromisoformat(info["timestamp"])
                if current_time - cache_time < timedelta(hours=expire_hours):
                    cleaned_cache[user_id] = info
                elif self.config.get("enable_debug", False):
                    logger.debug(f"清理过期缓存: {user_id}")

        return cleaned_cache

    async def _get_user_gender(self, event: AstrMessageEvent) -> Optional[str]:
        """获取用户性别，优先从缓存读取"""
        user_id = event.get_sender_id()

        # 检查缓存
        if user_id in self.gender_cache:
            cached_info = self.gender_cache[user_id]
            if self.config.get("enable_debug", False):
                logger.debug(f"从缓存获取性别信息: {user_id} -> {cached_info.get('gender')}")
            return cached_info.get("gender")

        # 尝试通过API获取性别
        gender = await self._fetch_gender_from_api(event)

        # 更新缓存
        if gender:
            self.gender_cache[user_id] = {
                "gender": gender,
                "timestamp": datetime.now().isoformat(),
                "nickname": event.get_sender_name()
            }
            self._save_cache()

        return gender

    async def _fetch_gender_from_api(self, event: AstrMessageEvent) -> Optional[str]:
        """通过平台API获取用户性别"""
        try:
            if event.get_platform_name() == "aiocqhttp":
                # QQ平台
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                if isinstance(event, AiocqhttpMessageEvent):
                    client = event.bot
                    user_id = event.get_sender_id()

                    # 调用get_stranger_info API
                    result = await client.api.call_action('get_stranger_info', user_id=user_id)

                    if self.config.get("enable_debug", False):
                        logger.debug(f"API返回数据: {result}")

                    if result and "data" in result:
                        sex = result["data"].get("sex", "unknown")
                        # QQ API: male=男, female=女, unknown=未知
                        return sex

            # 其他平台暂不支持
            return None

        except Exception as e:
            logger.error(f"获取用户性别失败: {e}")
            return None

    @filter.on_llm_request()
    async def modify_llm_prompt(self, event: AstrMessageEvent, req: ProviderRequest):
        """在LLM请求时根据性别修改prompt"""
        if not self.config.get("enable_plugin", True):
            return

        try:
            # 获取用户性别
            gender = await self._get_user_gender(event)

            # 选择对应的提示词
            if gender == "male":
                gender_prompt = self.config.get("male_prompt")
                honorific = self.config.get("male_honorific", "先生")
            elif gender == "female":
                gender_prompt = self.config.get("female_prompt")
                honorific = self.config.get("female_honorific", "女士")
            else:
                gender_prompt = self.config.get("unknown_prompt")
                honorific = self.config.get("unknown_honorific", "朋友")

            if self.config.get("enable_debug", False):
                logger.debug(f"用户 {event.get_sender_id()} 性别: {gender}")

            # 获取原始prompt
            original_prompt = req.prompt if hasattr(req, 'prompt') else ""

            # 如果启用了敬语，替换称呼
            if self.config.get("enable_honorific", True) and gender in ["male", "female"]:
                nickname = event.get_sender_name()
                honorific_prompt = f"(请称呼对方为{nickname}{honorific})"
                gender_prompt = f"{gender_prompt} {honorific_prompt}"

            # 根据配置的位置插入提示词
            prompt_position = self.config.get("prompt_position", "prefix")

            if prompt_position == "prefix":
                req.prompt = f"{gender_prompt}\n{original_prompt}"
            elif prompt_position == "suffix":
                req.prompt = f"{original_prompt}\n{gender_prompt}"

            # 同时修改系统提示词
            if hasattr(req, 'system_prompt') and req.system_prompt:
                req.system_prompt = f"{gender_prompt}\n\n{req.system_prompt}"
            elif hasattr(req, 'system_prompt'):
                req.system_prompt = gender_prompt

            logger.info(f"已为用户 {event.get_sender_id()} 插入性别提示: {gender}")

        except Exception as e:
            logger.error(f"修改LLM请求时出错: {e}")

    @filter.command("gender")
    async def check_gender(self, event: AstrMessageEvent):
        """查看用户性别信息"""
        gender = await self._get_user_gender(event)
        user_id = event.get_sender_id()
        nickname = event.get_sender_name()

        if gender == "male":
            gender_text = "男性"
            prompt = self.config.get("male_prompt")
            honorific = self.config.get("male_honorific", "先生")
        elif gender == "female":
            gender_text = "女性"
            prompt = self.config.get("female_prompt")
            honorific = self.config.get("female_honorific", "女士")
        else:
            gender_text = "未知"
            prompt = self.config.get("unknown_prompt")
            honorific = self.config.get("unknown_honorific", "朋友")

        cache_info = ""
        if user_id in self.gender_cache:
            cache_time = self.gender_cache[user_id].get("timestamp", "未知")
            cache_info = f"\n缓存时间: {cache_time}"

        yield event.plain_result(
            f"用户信息:\n"
            f"昵称: {nickname}\n"
            f"ID: {user_id}\n"
            f"性别: {gender_text}\n"
            f"敬语: {nickname}{honorific}\n"
            f"当前提示词: {prompt}\n"
            f"提示词位置: {self.config.get('prompt_position', 'prefix')}"
            f"{cache_info}"
        )

    @filter.command("gender_cache")
    async def show_cache(self, event: AstrMessageEvent):
        """查看性别缓存信息"""
        if not self.config.get("enable_debug", False):
            yield event.plain_result("调试模式未启用，无法查看缓存信息")
            return

        cache_count = len(self.gender_cache)
        cache_info = f"缓存用户数: {cache_count}\n"
        cache_info += f"缓存过期时间: {self.config.get('cache_expire_hours', 24)}小时\n\n"

        if cache_count > 0:
            cache_info += "缓存详情:\n"
            for user_id, info in list(self.gender_cache.items())[:10]:  # 最多显示10条
                gender = info.get("gender", "unknown")
                nickname = info.get("nickname", "未知")
                timestamp = info.get("timestamp", "未知")
                cache_info += f"- {nickname}({user_id}): {gender} | {timestamp}\n"

            if cache_count > 10:
                cache_info += f"\n... 还有 {cache_count - 10} 条记录"

        yield event.plain_result(cache_info)

    @filter.command("gender_clear_cache")
    async def clear_cache(self, event: AstrMessageEvent):
        """清除性别缓存"""
        if not self.config.get("enable_debug", False):
            yield event.plain_result("调试模式未启用，无法清除缓存")
            return

        cache_count = len(self.gender_cache)
        self.gender_cache = {}
        self._save_cache()

        yield event.plain_result(f"已清除 {cache_count} 条性别缓存记录")

    @filter.command("gender_debug")
    async def debug_info(self, event: AstrMessageEvent):
        """查看调试信息"""
        if not self.config.get("enable_debug", False):
            yield event.plain_result("调试模式未启用")
            return

        user_id = event.get_sender_id()
        gender = await self._get_user_gender(event)

        debug_info = f"""调试信息：
用户ID: {user_id}
昵称: {event.get_sender_name()}
平台: {event.get_platform_name()}
性别: {gender}
插件状态: {'启用' if self.config.get('enable_plugin', True) else '禁用'}
调试模式: {'启用' if self.config.get('enable_debug', False) else '禁用'}

当前配置:
- 男性提示词: {self.config.get('male_prompt')}
- 女性提示词: {self.config.get('female_prompt')}
- 未知提示词: {self.config.get('unknown_prompt')}
- 提示词位置: {self.config.get('prompt_position')}
- 启用敬语: {'是' if self.config.get('enable_honorific', True) else '否'}
- 缓存过期时间: {self.config.get('cache_expire_hours')}小时

缓存信息:
- 缓存文件: {self.cache_file}
- 缓存用户数: {len(self.gender_cache)}
- 当前用户是否在缓存中: {'是' if user_id in self.gender_cache else '否'}"""

        yield event.plain_result(debug_info)

    async def terminate(self):
        """插件卸载时保存缓存"""
        self._save_cache()
        logger.info("astrbot_plugin_gender_detector 插件已卸载")
