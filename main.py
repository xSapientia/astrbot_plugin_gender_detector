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
        self.config = config if config else AstrBotConfig()

        # 默认配置
        if not self.config:
            self.config = {
                "enable_plugin": True,
                "show_debug": False,
                "max_nicknames": 3,
                "cache_expire_hours": 168,  # 7天
                "male_prompt": "[用户性别: 男性]",
                "female_prompt": "[用户性别: 女性]",
                "unknown_prompt": "[用户性别: 未知]",
                "prompt_position": "prefix"
            }

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

        logger.info("Gender Detector v0.0.1 加载成功！")

        # 启动定期清理过期缓存的任务
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
                await asyncio.sleep(3600)  # 每小时检查一次

                expire_hours = self.config.get('cache_expire_hours', 168)
                expire_time = datetime.now().timestamp() - (expire_hours * 3600)

                # 清理过期的性别缓存
                expired_users = []
                for user_id, data in self.gender_cache.items():
                    if data.get('last_update', 0) < expire_time:
                        expired_users.append(user_id)

                for user_id in expired_users:
                    del self.gender_cache[user_id]

                if expired_users:
                    logger.debug(f"清理了 {len(expired_users)} 个过期的性别缓存")
                    self._save_cache()

            except Exception as e:
                logger.error(f"清理缓存时出错: {e}")

    async def _get_user_info_from_api(self, event: AstrMessageEvent, user_id: str) -> Optional[Dict]:
        """从API获取用户信息"""
        try:
            if event.get_platform_name() == "aiocqhttp":
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                assert isinstance(event, AiocqhttpMessageEvent)

                # 获取群成员信息
                if event.get_group_id():
                    ret = await event.bot.api.get_group_member_info(
                        group_id=event.get_group_id(),
                        user_id=int(user_id)
                    )
                    return ret
                else:
                    # 获取陌生人信息
                    ret = await event.bot.api.get_stranger_info(
                        user_id=int(user_id)
                    )
                    return ret
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            return None

    def _detect_gender_from_info(self, user_info: Dict) -> str:
        """从用户信息中检测性别"""
        if not user_info:
            return "unknown"

        # QQ API返回的性别字段
        sex = user_info.get('sex', 'unknown')
        if sex == 'male':
            return 'male'
        elif sex == 'female':
            return 'female'

        # 尝试从昵称或卡片名推测
        nickname = user_info.get('nickname', '')
        card = user_info.get('card', '')

        # 简单的性别推测规则（可以扩展）
        female_keywords = ['女', '姐', '妹', '娘', '姬', '媛', '嫦', '婷', '雅', '倩', '萌']
        male_keywords = ['男', '哥', '弟', '爷', '帅', '刚', '强', '伟', '军', '龙']

        text_to_check = nickname + card

        for keyword in female_keywords:
            if keyword in text_to_check:
                return 'female'

        for keyword in male_keywords:
            if keyword in text_to_check:
                return 'male'

        return 'unknown'

    def _extract_nicknames_from_message(self, message: str, user_id: str) -> List[Tuple[str, str]]:
        """从消息中提取昵称
        返回: [(昵称, 来源类型), ...]
        """
        nicknames = []

        # 检测自我介绍模式
        self_patterns = [
            r'我[叫是](.{1,10})',
            r'叫我(.{1,10})',
            r'我的名字[叫是](.{1,10})',
            r'大家好.*我[是叫](.{1,10})',
        ]

        for pattern in self_patterns:
            matches = re.findall(pattern, message)
            for match in matches:
                # 清理提取的昵称
                nickname = match.strip()
                if 1 <= len(nickname) <= 10:
                    nicknames.append((nickname, 'self'))

        return nicknames

    def _update_nickname_cache(self, user_id: str, nickname: str, source: str):
        """更新昵称缓存"""
        if user_id not in self.nickname_cache:
            self.nickname_cache[user_id] = []

        nicknames = self.nickname_cache[user_id]
        current_time = datetime.now().timestamp()

        # 查找是否已存在
        existing = None
        for item in nicknames:
            if item['nickname'] == nickname:
                existing = item
                break

        if existing:
            # 更新计数和时间
            existing['count'] += 1
            existing['last_seen'] = current_time
            if source == 'self' and existing['source'] != 'self':
                existing['source'] = 'self'  # 自称优先级更高
        else:
            # 添加新昵称
            nicknames.append({
                'nickname': nickname,
                'source': source,
                'count': 1,
                'last_seen': current_time
            })

        # 排序：self来源优先，然后按count降序
        nicknames.sort(key=lambda x: (x['source'] == 'self', x['count']), reverse=True)

        # 保留前N个
        max_nicknames = self.config.get('max_nicknames', 3)
        self.nickname_cache[user_id] = nicknames[:max_nicknames]

        self._save_cache()

    @filter.on_llm_request()
    async def modify_llm_prompt(self, event: AstrMessageEvent, req: ProviderRequest):
        """在LLM请求时修改prompt内容，添加性别信息"""
        if not self.config.get("enable_plugin", True):
            return

        try:
            user_id = event.get_sender_id()

            # 获取或更新性别信息
            gender = await self._get_user_gender(event, user_id)

            # 选择对应的提示词
            if gender == 'male':
                gender_prompt = self.config.get("male_prompt")
            elif gender == 'female':
                gender_prompt = self.config.get("female_prompt")
            else:
                gender_prompt = self.config.get("unknown_prompt")

            # 获取昵称信息
            nickname_info = ""
            if user_id in self.nickname_cache and self.nickname_cache[user_id]:
                top_nickname = self.nickname_cache[user_id][0]['nickname']
                nickname_info = f" 常用昵称: {top_nickname}"

            full_prompt = gender_prompt + nickname_info

            # 获取原始prompt
            original_prompt = req.prompt if hasattr(req, 'prompt') else ""

            # 根据配置的位置插入提示词
            prompt_position = self.config.get("prompt_position", "prefix")

            if prompt_position == "prefix":
                req.prompt = f"{full_prompt}\n{original_prompt}"
            elif prompt_position == "suffix":
                req.prompt = f"{original_prompt}\n{full_prompt}"

            # 同时修改系统提示词
            if hasattr(req, 'system_prompt') and req.system_prompt:
                req.system_prompt = f"{full_prompt}\n\n{req.system_prompt}"
            elif hasattr(req, 'system_prompt'):
                req.system_prompt = full_prompt

            if self.config.get("show_debug", False):
                logger.info(f"已为用户 {user_id} 添加性别信息: {gender_prompt}")

        except Exception as e:
            logger.error(f"修改LLM请求时出错: {e}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def analyze_message_for_nicknames(self, event: AstrMessageEvent):
        """分析消息以提取昵称信息"""
        if not self.config.get("enable_plugin", True):
            return

        try:
            user_id = event.get_sender_id()
            message = event.message_str

            # 提取昵称
            nicknames = self._extract_nicknames_from_message(message, user_id)

            for nickname, source in nicknames:
                self._update_nickname_cache(user_id, nickname, source)
                if self.config.get("show_debug", False):
                    logger.debug(f"检测到用户 {user_id} 的昵称: {nickname} (来源: {source})")

        except Exception as e:
            logger.error(f"分析消息时出错: {e}")

    async def _get_user_gender(self, event: AstrMessageEvent, user_id: str) -> str:
        """获取用户性别，优先从缓存读取"""
        # 检查缓存
        if user_id in self.gender_cache:
            cache_data = self.gender_cache[user_id]
            expire_hours = self.config.get('cache_expire_hours', 168)
            if datetime.now().timestamp() - cache_data['last_update'] < expire_hours * 3600:
                return cache_data['gender']

        # 从API获取
        user_info = await self._get_user_info_from_api(event, user_id)
        gender = self._detect_gender_from_info(user_info)

        # 更新缓存
        self.gender_cache[user_id] = {
            'gender': gender,
            'last_update': datetime.now().timestamp()
        }
        self._save_cache()

        return gender

    @filter.command("gender")
    async def check_gender(self, event: AstrMessageEvent):
        """查看用户性别"""
        # 提取At信息
        at_users = []
        for seg in event.message_obj.message:
            if isinstance(seg, Comp.At):
                at_users.append(str(seg.qq))

        # 确定要查询的用户
        if at_users:
            target_user = at_users[0]
            target_name = f"用户 {target_user}"
        else:
            target_user = event.get_sender_id()
            target_name = "你"

        # 获取性别信息
        gender = await self._get_user_gender(event, target_user)

        # 获取昵称信息
        nickname_info = ""
        if target_user in self.nickname_cache and self.nickname_cache[target_user]:
            nicknames = self.nickname_cache[target_user]
            nickname_list = [f"{n['nickname']}({n['source']})" for n in nicknames[:3]]
            nickname_info = f"\n常用昵称: {', '.join(nickname_list)}"

        # 构建回复
        gender_text = {
            'male': '男性♂',
            'female': '女性♀',
            'unknown': '未知'
        }.get(gender, '未知')

        response = f"{target_name}的性别是: {gender_text}{nickname_info}"

        if self.config.get("show_debug", False):
            cache_info = self.gender_cache.get(target_user, {})
            if cache_info:
                update_time = datetime.fromtimestamp(cache_info['last_update']).strftime('%Y-%m-%d %H:%M:%S')
                response += f"\n\n[调试信息]\n缓存更新时间: {update_time}"
                response += f"\n缓存性别数据: {len(self.gender_cache)} 条"
                response += f"\n缓存昵称数据: {len(self.nickname_cache)} 条"

        yield event.plain_result(response)

    @filter.command("gender_cache")
    async def show_cache_info(self, event: AstrMessageEvent):
        """查看缓存统计信息（仅管理员）"""
        # 这里可以添加权限检查

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
