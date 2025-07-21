import asyncio
import json
import os
import datetime
from typing import Dict, Any, Optional, List

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api.provider import ProviderRequest
from astrbot.api import logger, AstrBotConfig
import astrbot.api.message_components as Comp

@register(
    "astrbot_plugin_user_insights",
    "xSapientia",
    "深度用户洞察插件，缓存用户信息并注入LLM上下文。",
    "v0.0.1",
    "https://github.com/xSapientia/astrbot_plugin_user_insights"
)
class UserInsightsPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.context = context
        self.cache_file = os.path.join(self.get_plugin_data_path(), "user_cache.json")
        self.user_cache = self._load_cache()
        self.scan_task = None

        if self.config.get("enable_daily_scan", True):
            self.scan_task = asyncio.create_task(self._scheduled_scanner())

    def _debug_log(self, message: str):
        if self.config.get("show_debug_log", False):
            logger.info(f"[UserInsights Debug] {message}")

    # region Cache Management
    def _load_cache(self) -> Dict[str, Any]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.warning(f"无法解析缓存文件 {self.cache_file}，将初始化为空。")
        return {}

    def _save_cache(self):
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.user_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存缓存文件失败: {e}")

    def _get_cached_user(self, uid: str) -> Optional[Dict[str, Any]]:
        user_data = self.user_cache.get(uid)
        if not user_data:
            return None

        expiry_hours = self.config.get("cache_expiry_hours", 72)
        last_updated = datetime.datetime.fromisoformat(user_data.get("last_updated"))
        if datetime.datetime.now() - last_updated > datetime.timedelta(hours=expiry_hours):
            self._debug_log(f"用户 {uid} 缓存已过期。")
            return None

        return user_data

    def _update_cache(self, uid: str, data: Dict[str, Any]):
        data["last_updated"] = datetime.datetime.now().isoformat()
        self.user_cache[uid] = data
        self._save_cache()
    # endregion

    # region Platform Specific Info Fetching
    async def _fetch_user_info(self, platform_name: str, bot: Any, user_id: str, group_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """尝试从平台API获取用户信息 (主要支持 aiocqhttp)"""
        if platform_name != "aiocqhttp":
            return None

        try:
            if group_id:
                # 获取群成员信息
                payloads = {"group_id": int(group_id), "user_id": int(user_id), "no_cache": True}
                info = await bot.api.call_action('get_group_member_info', **payloads)
            else:
                # 获取陌生人/好友信息
                payloads = {"user_id": int(user_id), "no_cache": True}
                info = await bot.api.call_action('get_stranger_info', **payloads)

            if info and info.get('retcode') == 0:
                data = info.get('data', {})
                return self._normalize_qq_info(data)
        except Exception as e:
            self._debug_log(f"获取用户信息失败 (UID: {user_id}, GID: {group_id}): {e}")
        return None

    def _normalize_qq_info(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化QQ信息结构"""
        return {
            "nickname": data.get("nickname"),
            "sex": data.get("sex"),  # male, female, unknown
            "age": data.get("age"),
            "title": data.get("title"), # 群头衔
            "card": data.get("card") or data.get("nickname"), # 群名片
            # QQ API不直接提供生日，这里留空或使用其他方式推断
            "birthday": None,
        }
    # endregion

    # region Core Logic
    async def get_user_info(self, event: AstrMessageEvent, user_id: str) -> Dict[str, Any]:
        """获取用户信息，优先缓存，缓存失效则尝试更新"""
        uid = f"{event.get_platform_name()}:{user_id}"

        # 功能4: 优先更新缓存数据 (如果缓存过期)
        cached_data = self._get_cached_user(uid)
        if cached_data:
            return cached_data

        # 尝试从平台获取
        platform_name = event.get_platform_name()
        bot = getattr(event, 'bot', None) or getattr(event, 'client', None) # 兼容不同平台的bot/client属性

        if bot:
            group_id = event.get_group_id()
            fetched_data = await self._fetch_user_info(platform_name, bot, user_id, group_id)
            if fetched_data:
                # 功能2 (简化): 整理默认称呼
                nicknames = []
                if fetched_data.get("title"):
                    nicknames.append(fetched_data.get("title"))
                if fetched_data.get("card") and fetched_data.get("card") not in nicknames:
                    nicknames.append(fetched_data.get("card"))
                if fetched_data.get("nickname") and fetched_data.get("nickname") not in nicknames:
                     nicknames.append(fetched_data.get("nickname"))

                fetched_data["nicknames"] = nicknames[:self.config.get("nickname_cache_limit", 5)]

                self._update_cache(uid, fetched_data)
                return fetched_data

        # 无法获取或平台不支持
        return {"nickname": event.get_sender_name() if user_id == event.get_sender_id() else "未知用户", "sex": "unknown", "age": 0, "nicknames": []}

    def _format_user_context(self, user_data: Dict[str, Any]) -> str:
        """格式化用户信息为注入的上下文"""
        nickname = user_data.get('nickname', '未知')
        sex = user_data.get('sex', '未知')
        age = user_data.get('age', '未知')
        title = user_data.get('title', '无')
        card = user_data.get('card', nickname)

        return f"[用户: {nickname} (群名片:{card}, 头衔:{title}, 性别:{sex}, 年龄:{age})]"

    # 功能3: 在LLM请求时修改prompt内容
    @filter.on_llm_request()
    async def inject_user_context(self, event: AstrMessageEvent, req: ProviderRequest):
        if not self.config.get("enable_injection", True):
            return

        self._debug_log("开始注入用户上下文...")
        involved_users = set()
        context_injection = ""

        # 1. 处理发送者
        sender_id = event.get_sender_id()
        involved_users.add(sender_id)
        sender_info = await self.get_user_info(event, sender_id)
        context_injection += f"消息发送者信息: {self._format_user_context(sender_info)}\n"

        # 2. 处理@提及的用户
        for component in event.message_obj.message:
            if isinstance(component, Comp.At):
                at_user_id = str(component.qq) # qq属性通常用于存储目标ID
                if at_user_id and at_user_id != sender_id:
                    involved_users.add(at_user_id)
                    at_user_info = await self.get_user_info(event, at_user_id)
                    context_injection += f"被提及用户(@)信息: {self._format_user_context(at_user_info)}\n"

        # 3. (功能2简化实现) 尝试识别文本中的称呼 (此处实现较为复杂，依赖NLP，简化为仅依赖缓存的昵称匹配)
        # 注意：这部分实现非常基础，准确率有限
        message_text = event.message_str.lower()
        for uid_key, user_data in self.user_cache.items():
            platform, user_id = uid_key.split(':', 1)
            if user_id in involved_users or platform != event.get_platform_name():
                continue

            for nickname in user_data.get("nicknames", []):
                if nickname.lower() in message_text:
                    involved_users.add(user_id)
                    context_injection += f"消息中提到的用户({nickname})信息: {self._format_user_context(user_data)}\n"
                    break # 找到一个昵称就停止，避免重复添加

        # 注入信息
        user_count = len(involved_users)
        final_injection = f"【本次对话上下文信息】\n(涉及用户数: {user_count})\n{context_injection}【上下文信息结束】\n\n"

        if req.system_prompt:
            req.system_prompt = final_injection + req.system_prompt
        else:
            req.system_prompt = final_injection

        self._debug_log(f"注入完成。涉及用户数: {user_count}")

    # endregion

    # region Commands and Scanning

    # 功能1: 每日扫描
    async def _scheduled_scanner(self):
        while True:
            now = datetime.datetime.now()
            scan_time_str = self.config.get("daily_scan_time", "03:00")
            try:
                scan_hour, scan_minute = map(int, scan_time_str.split(':'))
                target_time = now.replace(hour=scan_hour, minute=scan_minute, second=0, microsecond=0)
            except ValueError:
                logger.error(f"每日扫描时间配置错误: {scan_time_str}。使用默认值 03:00。")
                target_time = now.replace(hour=3, minute=0, second=0, microsecond=0)

            if now > target_time:
                target_time += datetime.timedelta(days=1)

            wait_seconds = (target_time - now).total_seconds()
            self._debug_log(f"下一次扫描将在 {wait_seconds:.0f} 秒后执行 ({target_time})")
            await asyncio.sleep(wait_seconds)

            if self.config.get("enable_daily_scan", True):
                logger.info("开始执行每日群组扫描...")
                await self.scan_all_groups()

            # 确保任务在下一次循环前稍微等待，避免时间计算误差导致的重复执行
            await asyncio.sleep(60)

    async def scan_all_groups(self):
        # 获取所有加载的平台
        platforms = self.context.platform_manager.get_insts()
        for platform in platforms:
            if platform.platform_metadata.name == "aiocqhttp":
                await self._scan_aiocqhttp_groups(platform)

    async def _scan_aiocqhttp_groups(self, platform):
        try:
            # 假设平台实例有client属性
            client = getattr(platform, 'client', None)
            if not client:
                return

            # 获取群列表
            group_list_resp = await client.api.call_action('get_group_list')
            if group_list_resp and group_list_resp.get('retcode') == 0:
                groups = group_list_resp.get('data', [])
                self._debug_log(f"找到 {len(groups)} 个群组。")

                for group in groups:
                    group_id = str(group.get('group_id'))
                    await self._scan_group_members(client, group_id)
                    await asyncio.sleep(5) # 避免API调用过快
            else:
                self._debug_log("获取群列表失败。")
        except Exception as e:
            logger.error(f"扫描 aiocqhttp 群组时出错: {e}")

    async def _scan_group_members(self, client, group_id: str):
        try:
            member_list_resp = await client.api.call_action('get_group_member_list', group_id=int(group_id))
            if member_list_resp and member_list_resp.get('retcode') == 0:
                members = member_list_resp.get('data', [])
                self._debug_log(f"群 {group_id} 找到 {len(members)} 个成员。")

                for member in members:
                    user_id = str(member.get('user_id'))
                    uid = f"aiocqhttp:{user_id}"
                    normalized_info = self._normalize_qq_info(member)

                    # 更新缓存逻辑 (简化，只更新基础信息，不处理复杂昵称优先级)
                    nicknames = []
                    if normalized_info.get("title"):
                        nicknames.append(normalized_info.get("title"))
                    if normalized_info.get("card") and normalized_info.get("card") not in nicknames:
                        nicknames.append(normalized_info.get("card"))
                    if normalized_info.get("nickname") and normalized_info.get("nickname") not in nicknames:
                        nicknames.append(normalized_info.get("nickname"))

                    normalized_info["nicknames"] = nicknames[:self.config.get("nickname_cache_limit", 5)]
                    self._update_cache(uid, normalized_info)

                self._debug_log(f"群 {group_id} 缓存更新完成。")
        except Exception as e:
            logger.error(f"扫描群成员失败 (GID: {group_id}): {e}")

    # 要求2: 指令
    @filter.command("gender_scan", alias={"gscan"})
    @filter.permission_type(filter.PermissionType.ADMIN) # 限制管理员使用
    async def cmd_gscan(self, event: AstrMessageEvent):
        '''主动调用群聊扫描功能 (仅管理员)'''
        yield event.plain_result("开始手动扫描所有群组，请查看日志了解进度...")
        await self.scan_all_groups()
        yield event.plain_result("手动群组扫描完成。")

    @filter.command("gender")
    async def cmd_gender(self, event: AstrMessageEvent):
        '''查看自己或@提及的用户的性别'''
        target_id = None

        # 检查是否有@
        for component in event.message_obj.message:
            if isinstance(component, Comp.At):
                target_id = str(component.qq)
                break

        if not target_id:
            target_id = event.get_sender_id()

        user_info = await self.get_user_info(event, target_id)

        sex = user_info.get("sex", "unknown")
        nickname = user_info.get("nickname", "未知用户")

        if sex == "male":
            sex_str = "男性"
        elif sex == "female":
            sex_str = "女性"
        else:
            sex_str = "未知 (可能是平台不支持或用户未设置)"

        yield event.plain_result(f"用户 {nickname} (ID: {target_id}) 的性别是: {sex_str}")

    # endregion

    # 要求1: 卸载处理
    async def terminate(self):
        '''插件卸载/停用时的清理工作'''
        logger.info("astrbot_plugin_user_insights 正在卸载...")

        # 停止定时任务
        if self.scan_task:
            self.scan_task.cancel()
            self._debug_log("已停止每日扫描任务。")

        # 保存缓存
        self._save_cache()
        self._debug_log("已保存用户缓存。")

        # 数据清理
        if self.config.get("delete_data_on_uninstall", False):
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
                logger.info(f"已删除缓存文件: {self.cache_file}")

        # 配置清理 (AstrBotConfig 提供了获取配置文件路径的方法)
        if self.config.get("delete_config_on_uninstall", False):
            config_path = self.config.config_path
            if config_path and os.path.exists(config_path):
                os.remove(config_path)
                logger.info(f"已删除配置文件: {config_path}")
