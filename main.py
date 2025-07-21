import time
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.provider import ProviderRequest

# 使用 register 装饰器注册插件
@register(
    # 插件的唯一名称，与 metadata.yaml 中的 name 一致
    "astrbot_plugin_gender_identifier",
    # 作者
    "xSapientia & 阿凌",
    # 插件描述
    "通过调用平台API识别用户性别，并将其添加到LLM提示词中。",
    # 插件版本
    "0.0.1",
    # 插件仓库地址（可选）
    "https://github.com/your_repo/astrbot_plugin_gender_identifier", # 请替换为你的仓库地址
)
class GenderIdentifier(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        # 加载配置，如果不存在则使用默认值
        self.config = config if config else AstrBotConfig()
        # 初始化缓存字典，用于存储用户ID和其对应的性别及时间戳
        # 格式: { "user_id": ("gender", timestamp) }
        self.gender_cache = {}
        logger.info("Gender Identifier v1.0.0 加载成功！")

    # 使用 @filter.on_llm_request() 事件钩子
    # 这个钩子会在 AstrBot 准备向大语言模型发送请求时触发
    @filter.on_llm_request()
    async def modify_llm_prompt_with_gender(self, event: AstrMessageEvent, req: ProviderRequest):
        """
        在LLM请求时，获取用户性别并修改prompt内容
        """
        # 检查插件是否在配置中启用
        if not self.config.get("enable_plugin", True):
            return

        sender_id = event.get_sender_id()
        if not sender_id:
            return

        gender = await self._get_user_gender(event, sender_id)

        # 根据获取到的性别选择对应的提示词
        if gender == "male":
            prompt_to_add = self.config.get("male_prompt", "[男性用户]")
        elif gender == "female":
            prompt_to_add = self.config.get("female_prompt", "[女性用户]")
        else: # 'unknown' 或其他情况
            prompt_to_add = self.config.get("unknown_prompt", "[性别未知]")

        # 获取原始的 prompt
        original_prompt = req.prompt if hasattr(req, 'prompt') else ""

        # 根据配置决定将提示词添加到前面还是后面
        prompt_position = self.config.get("prompt_position", "prefix")
        if prompt_position == "prefix":
            req.prompt = f"{prompt_to_add}\n{original_prompt}"
        else: # suffix
            req.prompt = f"{original_prompt}\n{prompt_to_add}"

        logger.debug(f"已为用户 {sender_id} (性别: {gender}) 的请求添加提示词。")


    async def _get_user_gender(self, event: AstrMessageEvent, user_id: str) -> str:
        """
        核心函数：获取用户性别。优先从缓存读取，否则调用API获取。
        """
        cache_duration = self.config.get("cache_duration", 3600)

        # 1. 检查缓存
        if cache_duration > 0 and user_id in self.gender_cache:
            gender, timestamp = self.gender_cache[user_id]
            # 如果缓存未过期
            if time.time() - timestamp < cache_duration:
                logger.debug(f"从缓存中命中用户 {user_id} 的性别: {gender}")
                return gender

        # 2. 如果缓存中没有或已过期，调用API
        # 目前主要针对 aiocqhttp 平台，因为它提供了丰富的API
        gender = 'unknown' # 默认为未知
        if event.get_platform_name() == "aiocqhttp":
            try:
                # 尝试调用 get_stranger_info API，这通常可以获取到非好友的用户信息
                # Napcat等协议端支持此API
                logger.debug(f"正在为用户 {user_id} 调用 get_stranger_info API...")
                user_info = await event.bot.api.call_action('get_stranger_info', user_id=int(user_id))

                # API返回的数据中，'sex'字段通常是 'male', 'female', 或 'unknown'
                gender = user_info.get('sex', 'unknown')

            except Exception as e:
                # 如果是群聊，get_stranger_info 可能会失败，此时可以尝试 get_group_member_info
                if event.get_group_id():
                    try:
                        logger.debug(f"get_stranger_info失败，尝试为用户 {user_id} 调用 get_group_member_info...")
                        member_info = await event.bot.api.call_action('get_group_member_info', group_id=int(event.get_group_id()), user_id=int(user_id))
                        gender = member_info.get('sex', 'unknown')
                    except Exception as e2:
                        logger.warning(f"获取群成员 {user_id} 信息失败: {e2}")
                else:
                    logger.warning(f"获取用户信息 {user_id} 失败: {e}")
        else:
            logger.debug(f"当前平台 {event.get_platform_name()} 不支持获取性别信息。")

        # 3. 更新缓存
        if cache_duration > 0:
            self.gender_cache[user_id] = (gender, time.time())
            logger.debug(f"已缓存用户 {user_id} 的性别信息: {gender}")

        return gender

    # 注册一个调试指令 /mygender
    @filter.command("mygender")
    async def check_my_gender(self, event: AstrMessageEvent):
        """一个简单的指令，用于回复用户其被识别的性别"""
        sender_id = event.get_sender_id()
        if not sender_id:
            yield event.plain_result("无法获取你的用户信息。")
            return

        gender = await self._get_user_gender(event, sender_id)

        reply_text = f"你好，{event.get_sender_name()}！\n"
        if gender == "male":
            reply_text += "我识别到你的性别是：男性"
        elif gender == "female":
            reply_text += "我识别到你的性别是：女性"
        else:
            reply_text += "暂时无法确定你的性别。"

        yield event.plain_result(reply_text)

    async def terminate(self):
        """插件被卸载或停用时调用，用于清理资源"""
        logger.info("Gender Identifier 插件已卸载。")
        self.gender_cache.clear()
