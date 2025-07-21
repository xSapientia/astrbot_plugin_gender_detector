# astrbot_plugin_gender_detector（有bug）

智能管理用户信息并增强LLM对话体验的插件，支持QQ信息获取、历史消息分析、智能称呼管理等功能

<div align="center">

[![Version](https://img.shields.io/badge/version-v0.0.1-blue.svg)](https://github.com/xSapientia/astrbot_plugin_user_info_manager)
[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D3.4.0-green.svg)](https://github.com/Soulter/AstrBot)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

让你的 AstrBot 更智能地理解和管理用户信息！

</div>

## ✨ 功能特性

### 1. 智能用户信息管理
- 自动获取并缓存QQ用户的详细信息（昵称、群名片、群头衔、年龄、性别等）
- 支持设置缓存有效期，过期自动更新
- 每日定时扫描群成员信息，保持数据最新

### 2. 历史消息智能分析
- 自动分析历史对话，识别用户的各种称呼
- 智能管理称呼优先级（本人强调 > 他人称呼 > 群头衔/名片 > 昵称）
- 支持设置每个用户的最大称呼数量

### 3. LLM对话增强
- 在LLM请求时自动插入相关用户信息
- 智能识别对话中涉及的用户数量
- 为@消息和称呼自动附加用户详细信息

### 4. 灵活的配置选项
- 完善的可视化配置界面
- 支持开关各项功能
- 可调试模式，方便问题排查

## 🎯 使用方法

### 基础指令

| 指令 | 别名 | 说明 | 使用场景 |
|------|------|------|----------|
| `/gender` | `性别`, `sex` | 查询用户性别信息 | 所有场景 |
| `/gender_scan` | `gscan`, `扫描群成员` | 主动扫描群成员信息 | 仅群聊 |

### 使用示例

**查询性别：**
```
/gender @某人  # 查询指定用户的性别
/gender        # 查询自己的性别
/性别 小明      # 通过称呼查询（如果缓存中有）
```

**扫描群成员：**
```
/gscan         # 立即扫描当前群的所有成员信息
```

## ⚙️ 配置说明

插件支持在 AstrBot 管理面板中进行可视化配置：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enable_plugin` | bool | true | 插件总开关 |
| `cache_valid_days` | int | 7 | 用户信息缓存有效期（天） |
| `enable_daily_scan` | bool | true | 是否启用每日自动扫描 |
| `daily_scan_time` | string | "03:00" | 每日扫描时间（24小时制） |
| `history_messages_count` | int | 100 | 智能整理时读取的历史消息数 |
| `max_nicknames` | int | 5 | 每个用户最多缓存的称呼数量 |
| `enable_llm_prompt_insert` | bool | true | 是否在LLM请求时插入用户信息 |
| `show_debug_info` | bool | false | 是否显示调试信息 |
| `delete_on_uninstall` | bool | false | 卸载时是否删除所有数据 |

## 📊 工作原理

### 信息获取流程
1. **主动获取**：通过指令或定时任务主动获取用户信息
2. **被动缓存**：在处理消息时自动缓存相关用户信息
3. **智能更新**：缓存过期后自动更新，确保信息准确

### 称呼优先级系统
1. **最高优先级**：用户本人强调的称呼（如"叫我xxx"）
2. **次高优先级**：其他人对该用户的称呼
3. **默认优先级**：群头衔 > 群名片 > QQ昵称

### LLM增强机制
- 自动统计对话涉及的用户数量
- 在消息前缀插入发送者详细信息
- 为@消息和称呼附加用户属性

## 💾 数据存储

插件数据保存位置：
- 用户信息：`data/plugin_data/astrbot_plugin_user_info_manager/user_info.json`
- 称呼优先级：`data/plugin_data/astrbot_plugin_user_info_manager/nickname_priority.json`
- 插件配置：`data/config/astrbot_plugin_user_info_manager_config.json`

## 🔧 高级特性

### 智能称呼识别
- 自动学习群内的称呼习惯
- 支持多种称呼模式识别
- 智能管理称呼优先级

### 缓存管理
- 自动清理过期缓存
- 支持手动刷新缓存
- 高效的内存使用

### 平台兼容性
- 完美支持 AIOCQHTTP 平台
- 预留其他平台接口
- 优雅的降级处理

## 🐛 故障排除

### 插件无响应
1. 检查插件是否已启用
2. 查看 AstrBot 日志中的错误信息
3. 开启调试模式查看详细信息

### 信息获取失败
1. 确认机器人有获取成员信息的权限
2. 检查网络连接是否正常
3. 查看平台是否支持相关API

### 性能问题
1. 适当减少历史消息读取数量
2. 增加缓存有效期
3. 在用户较少的时段进行扫描

## 📝 更新日志

### v0.0.1 (2024-12-XX)
- ✅ 实现用户信息自动获取和缓存
- ✅ 添加智能称呼管理系统
- ✅ 实现LLM对话增强功能
- ✅ 支持定时扫描群成员
- ✅ 完善的配置系统
- ✅ 调试模式支持

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

### 开发计划
- [ ] 支持更多平台
- [ ] 添加用户画像功能
- [ ] 支持自定义信息模板
- [ ] 增加统计分析功能

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 👨‍💻 作者

- **xSapientia** - *Initial work* - [GitHub](https://github.com/xSapientia)

## 🙏 致谢

- 感谢 [AstrBot](https://github.com/Soulter/AstrBot) 项目提供的强大框架
- 感谢所有用户的反馈和建议

---

<div align="center">

如果这个插件对你有帮助，请给个 ⭐ Star！

[报告问题](https://github.com/xSapientia/astrbot_plugin_user_info_manager/issues) · [功能建议](https://github.com/xSapientia/astrbot_plugin_user_info_manager/issues) · [查看更多插件](https://github.com/xSapientia)

</div>
