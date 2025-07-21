# astrbot_plugin_gender_detector

智能识别用户性别并自动添加到 LLM prompt 的插件，支持称呼缓存和群成员扫描

<div align="center">

[![Version](https://img.shields.io/badge/version-0.0.1-blue.svg)](https://github.com/xSapientia/astrbot_plugin_gender_detector)
[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D3.4.0-green.svg)](https://github.com/Soulter/AstrBot)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

让你的 AstrBot 更懂用户，自动识别性别和称呼！

</div>

## ✨ 功能特性

### 🔍 智能识别
- **自动性别识别**: 通过 QQ 平台 API 自动获取用户性别信息
- **智能称呼提取**: 从对话中智能识别用户的自我介绍和他人对其的称呼
- **多用户统计**: 智能统计消息中涉及的所有用户信息

### 💾 高效缓存
- **信息缓存**: 缓存用户性别和昵称信息，避免重复 API 调用
- **称呼优先级**: 按 `本人强调称呼 > 他人称呼 > 默认称呼` 的优先级管理
- **过期清理**: 自动清理过期缓存，保持数据新鲜

### 🤖 LLM 增强
- **Prompt 自动注入**: 在 LLM 请求时自动添加用户性别和称呼信息
- **人格适配**: 根据 AstrBot 设定的人格确定默认称呼习惯
- **上下文感知**: 识别对话中所有相关用户，提供完整的用户信息

### 📊 群组管理
- **群成员扫描**: 一键扫描群内所有成员的性别信息
- **定时扫描**: 支持每日定时自动扫描，保持信息更新
- **统计分析**: 提供群组性别分布统计

### 🛠️ 调试工具
- **调试模式**: 详细的调试日志，帮助定位问题
- **诊断命令**: `/gender_debug` 显示原始 API 响应

## 🎯 使用方法

### 基础指令

| 指令 | 别名 | 说明 | 使用场景 |
|------|------|------|----------|
| `/gender` | `性别` | 查看用户性别 | 可查看自己或@他人的性别 |
| `/gender_scan` | `gscan`, `群扫描` | 扫描群成员信息 | 仅限群聊使用 |
| `/gender_debug` | `gd`, `性别调试` | 显示API原始响应 | 调试使用 |

### 使用示例

```
# 查看自己的性别
/gender

# 查看他人的性别
/gender @某人

# 扫描群成员
/gscan

# 调试模式
/gender_debug
```

## ⚙️ 配置说明

插件支持在 AstrBot 管理面板中进行可视化配置：

### 基础配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enable_plugin` | bool | true | 插件总开关 |
| `show_debug_info` | bool | false | 是否显示调试信息 |
| `max_cached_nicknames` | int | 5 | 每个用户最多缓存的称呼数量 |

### 自动扫描配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enable_daily_scan` | bool | true | 是否启用每日自动扫描 |
| `daily_scan_time` | string | "03:00" | 每日扫描时间（24小时制） |

### 缓存设置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `cache_expire_days` | int | 30 | 缓存有效期（天） |
| `auto_clean_cache` | bool | true | 是否自动清理过期缓存 |

### 卸载清理

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `delete_plugin_data` | bool | false | 卸载时是否删除数据目录 |
| `delete_config` | bool | false | 卸载时是否删除配置文件 |

## 🔧 工作原理

### 称呼识别机制

1. **自我介绍识别**: 识别如 "我叫xxx"、"请叫我xxx" 等模式
2. **他人称呼识别**: 识别 "@xxx" 等称呼模式
3. **优先级管理**: 自动按优先级排序和管理多个称呼

### LLM Prompt 注入

在 LLM 请求时，插件会：
1. 识别消息中涉及的所有用户
2. 获取每个用户的性别和最佳称呼
3. 构建用户信息描述并注入到系统提示词中

示例注入内容：
```
当前对话涉及的用户: [发送者]小明(男), 小红(女)
称呼习惯: 对男性用户使用"哥哥"，对女性用户使用"姐姐"
```

## 💾 数据存储

插件数据保存位置：
- 用户缓存：`data/plugin_data/astrbot_plugin_gender_detector/user_cache.json`
- 称呼优先级：`data/plugin_data/astrbot_plugin_gender_detector/nickname_priority.json`
- 插件配置：`data/config/astrbot_plugin_gender_detector_config.json`

## 🚀 高级特性

### 智能缓存管理
- 自动更新过期用户信息
- 智能合并重复称呼
- 按优先级限制称呼数量

### 平台适配
- 完美支持 QQ 平台（通过 NapCat/Lagrange）
- 预留其他平台扩展接口

### 性能优化
- 异步 API 调用，不阻塞主流程
- 智能缓存减少 API 请求
- 批量扫描优化群组处理

## 🐛 故障排除

### 插件无响应
1. 检查插件是否已启用（`enable_plugin` 配置）
2. 查看 AstrBot 日志是否有错误信息
3. 确认使用的是支持的平台（QQ + NapCat/Lagrange）

### 性别显示为"未知"
1. 确认用户在 QQ 中设置了性别
2. 检查机器人是否有获取用户信息的权限
3. 尝试手动使用 `/gscan` 重新扫描
4. 使用 `/gender_debug` 查看原始 API 响应

### 称呼识别不准确
1. 开启调试模式查看识别过程
2. 检查称呼优先级设置
3. 手动清理错误的缓存数据

### API 响应问题
1. 确保 NapCat/Lagrange 版本是最新的
2. 检查协议端日志是否有异常
3. 使用 `/gender_debug` 命令查看 API 响应格式

## 📝 更新日志

### v0.0.1 (2024-01-26)
- ✅ 实现用户性别自动识别
- ✅ 实现智能称呼提取和优先级管理
- ✅ 实现 LLM Prompt 自动注入
- ✅ 添加群成员扫描功能
- ✅ 实现定时自动扫描
- ✅ 添加缓存管理和过期清理
- ✅ 支持调试模式和详细日志
- ✅ 添加 API 响应诊断工具

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

### 开发建议
- 添加更多平台支持
- 优化称呼识别算法
- 增加更多统计功能
- 改进缓存策略

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 👨‍💻 作者

- **xSapientia** - *Initial work* - [GitHub](https://github.com/xSapientia)

## 🙏 致谢

- 感谢 [AstrBot](https://github.com/Soulter/AstrBot) 项目提供的优秀框架
- 感谢 [NapCat](https://github.com/NapNeko/NapCatQQ) 提供的 QQ 机器人协议支持

---

<div align="center">

如果这个插件对你有帮助，请给个 ⭐ Star！

[报告问题](https://github.com/xSapientia/astrbot_plugin_gender_detector/issues) · [功能建议](https://github.com/xSapientia/astrbot_plugin_gender_detector/issues) · [查看更多插件](https://github.com/xSapientia)

</div>
