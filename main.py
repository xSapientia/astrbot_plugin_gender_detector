import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Any, List

from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, register
import astrbot.api.message_components as Comp

# 插件元数据注册
@register(
    "astrbot_plugin_gender_detector",
    "xSapientia",
    "智能识别用户性别并将其信息注入到LLM请求中的插件。",
    "0.0.1",
    "https://github.com/xSapientia/astrbot_plugin_gender_detector",
)
class GenderDetector(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.cache_path = Path(f"data/plugin_data/{self.metadata.name}")
        self.cache_file = self.cache_path / "gender_cache.json"
        self.user_cache: Dict[str, Dict[str, Any]] = {}
        self.lock = asyncio.Lock() # 用于文件操作的异步锁

        # 初始化插件
        self._initialize_plugin()

    def _initialize_plugin(self):
        """初始化插件，包括创建数据目录和加载缓存"""
        try:
            # 确保数据目录存在
            self.cache_path.mkdir(parents=True, exist_ok=True)
            # 加载缓存
            self._load_cache()
            logger.info(f"'{self.metadata.name}' v{self.metadata.version} 加载成功。")
            logger.info(f"缓存已从 {self.cache_file} 加载, 共 {len(self.user_cache)} 条用户记录。")
        except Exception as e:
            logger.error(f"'{self.metadata.name}' 初始化失败: {e}")

    def _load_cache(self):
        """从文件加载缓存"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.user_cache = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"无法加载缓存文件 {self.cache_file}: {e}。将创建一个新的缓存。")
            self.user_cache = {}

    async def _save_cache(self):
        """异步安全地保存缓存到文件"""
        async with self.lock:
            try:
                with open(self.cache_file, "w", encoding="utf-8") as f:
                    json.dump(self.user_cache, f, ensure_ascii=False, indent=4)
            except IOError as e:
                logger.error(f"无法保存缓存到 {self.cache_file}: {e}")

    async def _get_user_gender_info(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户性别信息。
        1. 查缓存
        2. (模拟)API调用/逻辑分析
        3. 更新缓存
        """
        # 1. 检查缓存
        if user_id in self.user_cache:
            return self.user_cache[user_id]

        # 2. 模拟API调用/分析
        # 在实际应用中，这里应替换为真实的性别识别API调用或基于历史消息的NLP分析
        logger.info(f"用户 {user_id} 不在缓存中, 正在进行模拟性别识别...")

        # 模拟逻辑：此处返回未知，等待用户通过指令或其他方式更新
        gender = "unknown"
        nickname = ""

        # 3. 更新缓存
        user_info = {"gender": gender, "nicknames": [nickname] if nickname else []}
        async with self.lock:
            self.user_cache[user_id] = user_info

        # 异步保存缓存，不阻塞当前请求
        asyncio.create_task(self._save_cache())

        return user_info

    @filter.on_llm_request()
    async def modify_llm_prompt(self, event: AstrMessageEvent, req: ProviderRequest):
        """在LLM请求时根据用户性别修改prompt"""
        if not self.config.get("enable_plugin", True):
            return

        try:
            user_id = event.get_sender_id()
            user_info = await self._get_user_gender_info(user_id)
            gender = user_info.get("gender", "unknown")

            prompt_map = {
                "male": self.config.get("male_prompt", "[用户身份：男性]"),
                "female": self.config.get("female_prompt", "[用户身份：女性]"),
                "unknown": self.config.get("unknown_prompt", "[用户身份：未知]")
            }
            gender_prompt = prompt_map.get(gender, prompt_map["unknown"])

            # 根据配置的位置插入提示词
            position = self.config.get("prompt_position", "prefix")
            if position == "prefix":
                req.prompt = f"{gender_prompt}\n{req.prompt}"
            else: # suffix
                req.prompt = f"{req.prompt}\n{gender_prompt}"

            logger.info(f"成功为用户 {user_id} (性别: {gender}) 注入提示词。")
        except Exception as e:
            logger.error(f"注入性别提示词时出错: {e}")

    @filter.command("gender", alias={'性别'})
    async def gender_command(self, event: AstrMessageEvent, *args):
        """
        查询或设置用户性别。
        - /gender: 查看自己的性别
        - /gender @用户: 查看被@用户的性别
        - /gender set [male/female]: 设置自己的性别
        """
        # 提取@的用户
        target_user_id = None
        target_user_name = None
        for component in event.message_obj.message:
            if isinstance(component, Comp.At):
                target_user_id = str(component.qq) # At组件的qq属性是用户ID
                # 尝试获取用户名（如果消息链中有的话）
                related_plain = next((c.text for c in event.message_obj.message if isinstance(c, Comp.Plain) and f'@{target_user_id}' not in c.text), None)
                target_user_name = related_plain or f"用户{target_user_id}"
                break

        # 如果没有@用户，则目标是发送者自己
        if not target_user_id:
            target_user_id = event.get_sender_id()
            target_user_name = event.get_sender_name()

        # 处理设置性别的逻辑
        if args and args[0].lower() == 'set' and len(args) > 1:
            if target_user_id != event.get_sender_id():
                 yield event.plain_result("不能为他人设置性别！")
                 return

            new_gender = args[1].lower()
            if new_gender in ["male", "female"]:
                async with self.lock:
                    self.user_cache.setdefault(target_user_id, {})["gender"] = new_gender
                await self._save_cache()
                yield event.plain_result(f"你的性别已成功设置为: {new_gender}")
            else:
                yield event.plain_result("设置失败，性别只能是 'male' 或 'female'。")
            return

        # 查询逻辑
        user_info = await self._get_user_gender_info(target_user_id)
        gender = user_info.get("gender", "unknown")

        reply_msg = f"查询对象: {target_user_name}\n识别性别: {gender}"

        # 如果开启了调试模式，附加更多信息
        if self.config.get("enable_debug", False):
            nicknames = user_info.get("nicknames", [])
            debug_info = (
                f"\n\n--- 调试信息 ---\n"
                f"用户ID: {target_user_id}\n"
                f"缓存状态: {'存在' if target_user_id in self.user_cache else '不存在'}\n"
                f"缓存昵称: {nicknames if nicknames else '无'}"
            )
            reply_msg += debug_info

        yield event.plain_result(reply_msg)

    async def terminate(self):
        """插件卸载/停用时调用，确保缓存被保存"""
        logger.info(f"'{self.metadata.name}' 正在卸载，开始保存缓存...")
        await self._save_cache()
        logger.info(f"'{self.metadata.name}' 缓存已保存，插件已卸载。")
