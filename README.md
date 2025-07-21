# astrbot_plugin_gender_detector

一个智能识别用户性别并在LLM请求时添加合适称呼的AstrBot插件

## ✨ 功能特性

- 🔍 自动识别QQ用户性别
- 💬 智能学习和管理用户称呼
- 🧠 在LLM请求时自动注入性别和称呼信息
- 📊 支持查看用户性别和称呼信息
- ⚡ 高效缓存机制，避免重复API调用
- 🎯 称呼优先级管理系统
- 🔄 每日自动扫描群成员
- 🤖 智能识别消息中提到的用户

## 🎯 使用方法

### 基础指令

| 指令 | 别名 | 说明 | 权限 | 使用示例 |
|------|------|------|------|----------|
| `/gender` | `性别`, `查看性别` | 查看用户性别信息 | 所有人 | `/gender` 或 `/gender @某人` |
| `/gscan` | `/gender_scan`, `扫描群成员` | 扫描当前群所有成员 | 管理员 | `/gscan` (仅群聊) |
| `/gender_stats` | `性别统计` | 查看插件统计信息 | 所有人 | `/gender_stats` |
| `/gender_reload` | `重载性别配置` | 重载插件配置 | 管理员 | `/gender_reload` |
| `/gender_config` | `性别配置`, `查看配置` | 查看当前配置 | 管理员 | `/gender_config` |

### 功能说明

1. **自动性别识别**：插件会在用户首次互动时自动获取并缓存其性别信息

2. **智能称呼学习**：
   - 从聊天记录中智能提取称呼
   - 支持多种称呼模式识别
   - 按优先级管理称呼（本人强调 > 他人称呼 > 默认称呼）

3. **LLM集成**：
   - 自动在LLM请求时注入用户性别和称呼
   - 支持识别@的多个用户
   - 智能识别消息中提到但未@的用户
   - 让AI回复更加个性化和贴心

4. **自动扫描**：
   - 每天定时扫描所有群成员信息
   - 可手动触发扫描当前群

### 注意事项

- 为避免命令冲突，推荐使用 `/gscan` 来扫描群成员
- 扫描命令只能在群聊中使用
- @全体成员时不会触发性别识别功能
- 配置修改后使用 `/gender_reload` 重载

## ⚙️ 配置说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `debug` | bool | false | 开启调试模式，显示详细日志 |
| `max_nicknames` | int | 5 | 每个用户最多缓存的称呼数量 |
| `gender_api_timeout` | int | 5 | API请求超时时间(秒) |
| `cache_expire_days` | int | 30 | 缓存有效期(天) |
| `enable_nickname_learning` | bool | true | 是否启用自动称呼学习 |
| `enable_smart_user_detection` | bool | true | 是否智能识别消息中的用户 |
| `enable_daily_scan` | bool | true | 是否启用每日自动扫描 |
| `daily_scan_time` | string | "03:00" | 每日扫描时间 |
| `default_nicknames` | object | - | 不同性别的默认称呼配置 |

## 💾 数据存储

插件数据保存位置：
- 性别缓存：`data/plugin_data/astrbot_plugin_gender_detector/gender_cache.json`
- 称呼缓存：`data/plugin_data/astrbot_plugin_gender_detector/nickname_cache.json`
- 别名映射：`data/plugin_data/astrbot_plugin_gender_detector/user_alias.json`
- 扫描历史：`data/plugin_data/astrbot_plugin_gender_detector/scan_history.json`

## 🔧 高级特性

### 称呼优先级系统
- 优先级3：用户本人强调的称呼（如"叫我小明"）
- 优先级2：其他人对该用户的称呼
- 优先级1：基于性别和人格的默认称呼

### 智能用户识别
- 支持识别"告诉小明"、"叫班长来"等自然语言
- 基于群成员信息精确匹配
- 自动学习用户昵称和群名片

### 智能缓存机制
- 自动定期保存缓存（每5分钟）
- 支持缓存过期设置
- 避免重复API调用

## 🐛 故障排除

### 插件配置无法保存
- 确保有写入权限
- 使用 `/gender_reload` 重载配置
- 查看 `/gender_config` 确认当前配置

### 无法获取群成员信息
- 确保机器人在群内
- 确保机器人有相应权限
- 检查是否使用了正确的协议端（如Napcat）
- 开启调试模式查看详细错误信息

## 📝 更新日志

### v0.0.2 (2025-07-21)
- ✅ 修复配置保存问题
- ✅ 修复群成员获取问题
- ✅ 改进客户端获取逻辑
- ✅ 增强错误处理和日志输出

### v0.0.1 (2025-07-21)
- ✅ 实现基础性别识别功能
- ✅ 添加智能称呼学习系统
- ✅ 集成LLM prompt修改功能
- ✅ 实现高效缓存机制
- ✅ 添加gender查询指令
- ✅ 支持多人识别和智能用户检测
- ✅ 添加每日自动扫描功能
- ✅ 排除@全体成员的处理

## 🤝 贡献

欢迎提交Issue和Pull Request！

## 📄 许可证

本项目采用 MIT 许可证

## 👨‍💻 作者

- **xSapientia** - [GitHub](https://github.com/xSapientia)
