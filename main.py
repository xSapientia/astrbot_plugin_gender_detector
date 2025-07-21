import time
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.provider import ProviderRequest

@register(
    "astrbot_plugin_gender_identifier",
    "xSapientia",
    "通过调用平台API识别用户性别，并将其添加到LLM提示词中。",
    "0.0.2",
    "https://github.com/your_repo/astrbot_plugin_gender_identifier",
)
class GenderIdentifier(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config if config else AstrBotConfig()
        self.gender_cache = {}
        # 增加一个属性来方便地获取调试开关状态
        self.debug_enabled = self.config.get("enable_debug_log", False)
        logger.info(f"Gender Identifier v0.0.2 加载成功！调试模式: {'启用' if self.debug_enabled else '禁用'}")

    @filter.on_llm_request()
    async def modify_llm_prompt_with_gender(self, event: AstrMessageEvent, req: ProviderRequest):
        if not self.config.get("enable_plugin", True):
            return

        sender_id = event.get_sender_id()
        if not sender_id:
            return

        gender = await self._get_user_gender(event, sender_id)

        if gender == "male":
            prompt_to_add = self.config.get("male_prompt", "[男性用户]")
        elif gender == "female":
            prompt_to_add = self.config.get("female_prompt", "[女性用户]")
        else:
            prompt_to_add = self.config.get("unknown_prompt", "[性别未知]")

        original_prompt = req.prompt if hasattr(req, 'prompt') else ""
        prompt_position = self.config.get("prompt_position", "prefix")

        if prompt_position == "prefix":
            req.prompt = f"{prompt_to_add}\n{original_prompt}"
        else:
            req.prompt = f"{original_prompt}\n{prompt_to_add}"

        if self.debug_enabled:
            logger.debug(f"已为用户 {sender_id} (性别: {gender}) 的请求添加提示词。")

    async def _get_user_gender(self, event: AstrMessageEvent, user_id: str) -> str:
        cache_duration = self.config.get("cache_duration", 3600)

        # 实时获取最新的调试开关状态，以免插件需要重载才能生效
        self.debug_enabled = self.config.get("enable_debug_log", False)

        if cache_duration > 0 and user_id in self.gender_cache:
            gender, timestamp = self.gender_cache[user_id]
            if time.time() - timestamp < cache_duration:
                if self.debug_enabled:
                    logger.debug(f"从缓存中命中用户 {user_id} 的性别: {gender}")
                return gender

        gender = 'unknown'
        if event.get_platform_name() == "aiocqhttp":
            try:
                if self.debug_enabled:
                    logger.debug(f"正在为用户 {user_id} 调用 get_stranger_info API...")
                user_info = await event.bot.api.call_action('get_stranger_info', user_id=int(user_id))
                gender = user_info.get('sex', 'unknown')
            except Exception as e:
                if event.get_group_id():
                    try:
                        if self.debug_enabled:
                            logger.debug(f"get_stranger_info失败，尝试为用户 {user_id} 调用 get_group_member_info...")
                        member_info = await event.bot.api.call_action('get_group_member_info', group_id=int(event.get_group_id()), user_id=int(user_id))
                        gender = member_info.get('sex', 'unknown')
                    except Exception as e2:
                        logger.warning(f"获取群成员 {user_id} 信息失败: {e2}")
                else:
                    logger.warning(f"获取用户信息 {user_id} 失败: {e}")
        else:
            if self.debug_enabled:
                logger.debug(f"当前平台 {event.get_platform_name()} 不支持获取性别信息。")

        if cache_duration > 0:
            self.gender_cache[user_id] = (gender, time.time())
            if self.debug_enabled:
                logger.debug(f"已缓存用户 {user_id} 的性别信息: {gender}")

        return gender

    @filter.command("mygender")
    async def check_my_gender(self, event: AstrMessageEvent):
        sender_id = event.get_sender_id()
        if not sender_id:
            yield event.plain_result("无法获取你的用户信息。")
            return

        is_debug = self.config.get("enable_debug_log", False)
        gender = await self._get_user_gender(event, sender_id)

        reply_text = f"你好，{event.get_sender_name()}！\n"
        if gender == "male":
            reply_text += "我识别到你的性别是：男性"
        elif gender == "female":
            reply_text += "我识别到你的性别是：女性"
        else:
            reply_text += "暂时无法确定你的性别。"

        if is_debug:
            reply_text += f"\n[调试信息] 性别原始值: {gender}"

        yield event.plain_result(reply_text)

    async def terminate(self):
        logger.info("Gender Identifier 插件已卸载。")
        self.gender_cache.clear()
