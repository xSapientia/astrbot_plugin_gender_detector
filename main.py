# main.py
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.api.provider import ProviderRequest
import astrbot.api.message_components as Comp
import json
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import re

@register(
    "astrbot_plugin_gender_detector",
    "xSapientia",
    "识别用户性别并智能管理称呼的插件",
    "0.0.1",
    "https://github.com/xSapientia/astrbot_plugin_gender_detector",
)
class GenderDetector(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config if config else AstrBotConfig()

        # 默认配置
        default_config = {
            "enable_plugin": True,
            "max_cached_addresses": 5,
            "debug_mode": False,
            "male_default_address": "先生",
            "female_default_address": "女士",
            "unknown_default_address": "朋友",
            "auto_detect_from_history": True,
            "cache_expiry_days": 30
        }

        # 合并默认配置
        for key, value in default_config.items():
            if key not in self.config:
                self.config[key] = value

        # 数据目录
        self.data_dir = os.path.join("data", "plugin_data", "astrbot_plugin_gender_detector")
        os.makedirs(self.data_dir, exist_ok=True)

        # 缓存文件路径
        self.cache_file = os.path.join(self.data_dir, "gender_cache.json")
        self.address_cache_file = os.path.join(self.data_dir, "address_cache.json")

        # 加载缓存
        self.gender_cache = self._load_cache(self.cache_file)
        self.address_cache = self._load_cache(self.address_cache_file)

        logger.info("Gender Detector v0.0.1 加载成功！")
        if self.config.get("debug_mode"):
            logger.debug(f"缓存目录: {self.data_dir}")
            logger.debug(f"性别缓存数量: {len(self.gender_cache)}")
            logger.debug(f"称呼缓存数量: {len(self.address_cache)}")

    def _load_cache(self, file_path: str) -> Dict:
        """加载缓存文件"""
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载缓存文件失败: {file_path}, 错误: {e}")
        return {}

    def _save_cache(self):
        """保存缓存到文件"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.gender_cache, f, ensure_ascii=False, indent=2)
            with open(self.address_cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.address_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")

    def _detect_gender_from_name(self, name: str) -> Optional[str]:
        """从昵称智能推测性别"""
        # 女性常见字符
        female_chars = ['女', '姐', '妹', '娘', '媛', '婷', '莉', '丽', '美', '芳', '花', '萌', '小仙女']
        # 男性常见字符
        male_chars = ['男', '哥', '弟', '爷', '帅', '强', '刚', '勇', '威', '龙', '虎', '少爷']

        for char in female_chars:
            if char in name:
                return 'female'

        for char in male_chars:
            if char in name:
                return 'male'

        return None

    def _extract_addresses_from_message(self, message: str, user_id: str) -> List[Tuple[str, int]]:
        """从消息中提取称呼和优先级"""
        addresses = []

        # 检测是否是本人强调的称呼（优先级最高）
        self_patterns = [
            r'[我叫|请叫我|称呼我|喊我|叫我](.{1,4})',
            r'我是(.{1,4})[，。！]',
            r'本(.{1,4})在此'
        ]

        for pattern in self_patterns:
            matches = re.findall(pattern, message)
            for match in matches:
                if match and len(match) <= 4:
                    addresses.append((match, 3))  # 优先级3：本人强调

        # 检测其他人对该用户的称呼（优先级中等）
        other_patterns = [
            f'@.+? (.{{1,4}})[，。！\\s]',
            f'(.{{1,4}})[，。！\\s].*{user_id}'
        ]

        for pattern in other_patterns:
            matches = re.findall(pattern, message)
            for match in matches:
                if match and len(match) <= 4:
                    addresses.append((match, 2))  # 优先级2：他人称呼

        return addresses

    def _get_user_gender(self, user_id: str) -> str:
        """获取用户性别，带缓存"""
        # 检查缓存
        if user_id in self.gender_cache:
            cache_data = self.gender_cache[user_id]
            # 检查缓存是否过期
            cache_time = datetime.fromisoformat(cache_data['timestamp'])
            if (datetime.now() - cache_time).days < self.config.get('cache_expiry_days', 30):
                return cache_data['gender']

        # 这里可以调用实际的API获取性别
        # 示例：暂时返回unknown
        return 'unknown'

    def _update_gender_cache(self, user_id: str, gender: str):
        """更新性别缓存"""
        self.gender_cache[user_id] = {
            'gender': gender,
            'timestamp': datetime.now().isoformat()
        }
        self._save_cache()

    def _get_user_address(self, user_id: str, gender: str) -> str:
        """获取用户称呼"""
        # 检查称呼缓存
        if user_id in self.address_cache:
            addresses = self.address_cache[user_id]['addresses']
            if addresses:
                # 返回优先级最高的称呼
                return max(addresses, key=lambda x: x['priority'])['address']

        # 根据性别返回默认称呼
        if gender == 'male':
            return self.config.get('male_default_address', '先生')
        elif gender == 'female':
            return self.config.get('female_default_address', '女士')
        else:
            return self.config.get('unknown_default_address', '朋友')

    def _update_address_cache(self, user_id: str, address: str, priority: int, source: str = ""):
        """更新称呼缓存"""
        if user_id not in self.address_cache:
            self.address_cache[user_id] = {
                'addresses': [],
                'last_updated': datetime.now().isoformat()
            }

        addresses = self.address_cache[user_id]['addresses']

        # 检查是否已存在相同称呼
        for i, addr in enumerate(addresses):
            if addr['address'] == address:
                # 更新优先级（如果新的更高）
                if priority > addr['priority']:
                    addresses[i]['priority'] = priority
                    addresses[i]['source'] = source
                    addresses[i]['timestamp'] = datetime.now().isoformat()
                self._save_cache()
                return

        # 添加新称呼
        addresses.append({
            'address': address,
            'priority': priority,
            'source': source,
            'timestamp': datetime.now().isoformat()
        })

        # 保持最大缓存数量
        max_addresses = self.config.get('max_cached_addresses', 5)
        if len(addresses) > max_addresses:
            # 移除优先级最低的
            addresses.sort(key=lambda x: x['priority'], reverse=True)
            self.address_cache[user_id]['addresses'] = addresses[:max_addresses]

        self.address_cache[user_id]['last_updated'] = datetime.now().isoformat()
        self._save_cache()

    @filter.on_llm_request()
    async def modify_llm_prompt(self, event: AstrMessageEvent, req: ProviderRequest):
        """在LLM请求时注入性别和称呼信息"""
        if not self.config.get("enable_plugin", True):
            return

        try:
            user_id = event.get_sender_id()
            user_name = event.get_sender_name()

            # 获取性别
            gender = self._get_user_gender(user_id)

            # 尝试从昵称推测性别
            if gender == 'unknown' and user_name:
                detected_gender = self._detect_gender_from_name(user_name)
                if detected_gender:
                    gender = detected_gender
                    self._update_gender_cache(user_id, gender)

            # 获取称呼
            address = self._get_user_address(user_id, gender)

            # 构建提示信息
            gender_info = {
                'male': '男性',
                'female': '女性',
                'unknown': '性别未知'
            }.get(gender, '性别未知')

            prompt_addition = f"[用户信息: {user_name}({address}), {gender_info}]"

            # 修改prompt
            if hasattr(req, 'prompt'):
                req.prompt = f"{prompt_addition}\n{req.prompt}"

            # 同时修改系统提示词
            if hasattr(req, 'system_prompt') and req.system_prompt:
                req.system_prompt = f"{prompt_addition}\n\n{req.system_prompt}"

            if self.config.get("debug_mode"):
                logger.debug(f"已注入用户信息: {prompt_addition}")

        except Exception as e:
            logger.error(f"修改LLM请求时出错: {e}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def analyze_message_for_addresses(self, event: AstrMessageEvent):
        """分析消息中的称呼信息"""
        if not self.config.get("enable_plugin", True):
            return

        if not self.config.get("auto_detect_from_history", True):
            return

        try:
            message = event.message_str
            sender_id = event.get_sender_id()

            # 分析发送者自己的称呼声明
            self_addresses = self._extract_addresses_from_message(message, sender_id)
            for address, priority in self_addresses:
                if priority == 3:  # 本人强调的称呼
                    self._update_address_cache(sender_id, address, priority, f"self_{event.message_obj.message_id}")
                    if self.config.get("debug_mode"):
                        logger.debug(f"检测到用户 {sender_id} 的自我称呼: {address}")

            # 分析消息中提到的其他人的称呼
            # 这里可以扩展更复杂的逻辑

        except Exception as e:
            if self.config.get("debug_mode"):
                logger.error(f"分析消息时出错: {e}")

    @filter.command("gender")
    async def check_gender(self, event: AstrMessageEvent):
        """查看性别信息"""
        try:
            # 检查是否有@某人
            target_user_id = None
            target_user_name = None

            for comp in event.message_obj.message:
                if isinstance(comp, Comp.At):
                    target_user_id = str(comp.qq)
                    # 这里可以获取被@用户的昵称
                    target_user_name = f"用户{target_user_id}"
                    break

            # 如果没有@任何人，则查看发送者自己
            if not target_user_id:
                target_user_id = event.get_sender_id()
                target_user_name = event.get_sender_name()

            # 获取性别和称呼信息
            gender = self._get_user_gender(target_user_id)
            address = self._get_user_address(target_user_id, gender)

            # 构建回复
            gender_text = {
                'male': '男性',
                'female': '女性',
                'unknown': '性别未知'
            }.get(gender, '性别未知')

            result = f"👤 用户信息\n"
            result += f"昵称: {target_user_name}\n"
            result += f"ID: {target_user_id}\n"
            result += f"性别: {gender_text}\n"
            result += f"当前称呼: {address}\n"

            # 如果有缓存的称呼列表，显示出来
            if target_user_id in self.address_cache:
                addresses = self.address_cache[target_user_id]['addresses']
                if addresses:
                    result += f"\n📝 称呼记录:\n"
                    for addr in sorted(addresses, key=lambda x: x['priority'], reverse=True):
                        priority_text = {
                            3: "本人强调",
                            2: "他人称呼",
                            1: "默认称呼"
                        }.get(addr['priority'], "其他")
                        result += f"  • {addr['address']} ({priority_text})\n"

            yield event.plain_result(result)

        except Exception as e:
            logger.error(f"查询性别信息时出错: {e}")
            yield event.plain_result(f"查询失败: {str(e)}")

    @filter.command("gender_debug")
    async def debug_info(self, event: AstrMessageEvent):
        """查看调试信息（仅管理员）"""
        # 检查是否是管理员
        if not event.check_sender_role("admin"):
            yield event.plain_result("该命令仅管理员可用")
            return

        try:
            debug_info = f"🔧 Gender Detector 调试信息\n\n"
            debug_info += f"插件状态: {'启用' if self.config.get('enable_plugin', True) else '禁用'}\n"
            debug_info += f"调试模式: {'开启' if self.config.get('debug_mode', False) else '关闭'}\n"
            debug_info += f"自动检测: {'开启' if self.config.get('auto_detect_from_history', True) else '关闭'}\n"
            debug_info += f"最大缓存称呼数: {self.config.get('max_cached_addresses', 5)}\n"
            debug_info += f"缓存过期天数: {self.config.get('cache_expiry_days', 30)}\n"
            debug_info += f"\n📊 缓存统计:\n"
            debug_info += f"性别缓存数: {len(self.gender_cache)}\n"
            debug_info += f"称呼缓存数: {len(self.address_cache)}\n"
            debug_info += f"\n📁 数据文件:\n"
            debug_info += f"数据目录: {self.data_dir}\n"
            debug_info += f"性别缓存: {os.path.basename(self.cache_file)}\n"
            debug_info += f"称呼缓存: {os.path.basename(self.address_cache_file)}\n"

            yield event.plain_result(debug_info)

        except Exception as e:
            logger.error(f"获取调试信息时出错: {e}")
            yield event.plain_result(f"获取调试信息失败: {str(e)}")

    async def terminate(self):
        """插件卸载时保存缓存并清理"""
        self._save_cache()

        # 删除配置文件
        config_file = os.path.join("data", "config", "astrbot_plugin_gender_detector_config.json")
        if os.path.exists(config_file):
            try:
                os.remove(config_file)
                logger.info(f"已删除配置文件: {config_file}")
            except Exception as e:
                logger.error(f"删除配置文件失败: {e}")

        logger.info("astrbot_plugin_gender_detector 插件已卸载")
