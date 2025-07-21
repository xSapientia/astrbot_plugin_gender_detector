# astrbot_plugin_gender_detector
识别用户性别并智能管理称呼的插件

# 性别检测与称呼管理 AstrBot 插件

<div align="center">

[![Version](https://img.shields.io/badge/version-v0.0.1-blue.svg)](https://github.com/xSapientia/astrbot_plugin_gender_detector)
[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D3.4.0-green.svg)](https://github.com/Soulter/AstrBot)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

智能识别用户性别，自动管理称呼，让你的 AstrBot 更懂用户！

</div>

## ✨ 功能特性

- 🔍 **智能性别识别** - 通过昵称智能推测用户性别
- 📝 **称呼管理系统** - 支持多级优先级的称呼缓存
- 🤖 **LLM提示词增强** - 自动将用户信息注入到LLM对话中
- 💾 **持久化缓存** - 性别和称呼信息持久保存
- 🔧 **灵活配置** - 支持自定义默认称呼和各种参数
- 📊 **调试模式** - 详细的调试信息输出

## 🎯 使用方法

### 基础指令

| 指令 | 说明 | 权限 | 示例 |
|------|------|------|------|
| `/gender` | 查看自己的性别信息 | 所有人 | `/gender` |
| `/gender @某人` | 查看指定用户的性别信息 | 所有人 | `/gender @张三` |
| `/gender_debug` | 查看插件调试信息 | 管理员 | `/gender_debug` |

### 称呼优先级系统

插件使用三级优先级系统管理用户称呼：

1. **优先级3 - 本人强调** - 用户自己声明的称呼（如"请叫我小王"）
2. **优先级2 - 他人称呼** - 其他人对该用户的称呼
3. **优先级1 - 默认称呼** - 根据性别设置的默认称呼

## ⚙️ 配置说明

插件支持在 AstrBot 管理面板中进行可视化配置：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enable_plugin` | bool | true | 插件总开关 |
| `max_cached_addresses` | int | 5 | 每个用户最多缓存的称呼数量 |
| `debug_mode` | bool | false | 是否开启调试模式 |
| `male_default_address` | string | "先生" | 男性默认称呼 |
| `female_default_address` | string | "女士" | 女性默认称呼 |
| `unknown_default_address` | string | "朋友" | 性别未知时的默认称呼 |
| `auto_detect_from_history` | bool | true | 是否自动从历史消息中检测称呼 |
| `cache_expiry_days` | int | 30 | 缓存过期天数 |

## 📊 工作原理

### 性别识别
1. 首先检查缓存中是否有该用户的性别信息
2. 如果没有，尝试从用户昵称中智能推测性别
3. 支持识别常见的性别相关字符（如"姐"、"哥"等）

### 称呼检测
插件会自动分析消息内容，识别以下模式：
- "请叫我XX" / "我叫XX" - 识别为本人强调的称呼
- "@某人 XX" - 识别为他人对该用户的称呼

### LLM增强
在每次LLM请求时，插件会自动注入用户信息：
```
[用户信息: 张三(先生), 男性]
```

## 💾 数据存储

插件数据保存在以下位置：
- 性别缓存：`data/plugin_data/astrbot_plugin_gender_detector/gender_cache.json`
- 称呼缓存：`data/plugin_data/astrbot_plugin_gender_detector/address_cache.json`
- 插件配置：`data/config/astrbot_plugin_gender_detector_config.json`

## 🔧 高级特性

### 智能称呼学习
- 插件会从对话中自动学习和更新用户的称呼偏好
- 支持同时缓存多个称呼，自动选择优先级最高的使用

### 缓存管理
- 自动清理过期缓存
- 限制每个用户的称呼缓存数量，防止存储膨胀

### 调试支持
- 完整的调试日志输出
- 管理员专用的调试命令

## 🐛 故障排除

### 性别识别不准确
1. 检查用户昵称是否包含性别特征
2. 可以通过API扩展来获取更准确的性别信息

### 称呼没有被记录
1. 确认 `auto_detect_from_history` 配置已开启
2. 检查消息是否符合识别模式
3. 查看调试日志了解详细信息

## 📝 更新日志

### v0.0.1 (2024-12-26)
- ✅ 实现基础的性别识别功能
- ✅ 添加多级称呼优先级系统
- ✅ 支持从历史消息中学习称呼
- ✅ 集成LLM提示词增强
- ✅ 实现持久化缓存机制
- ✅ 添加调试模式和管理命令

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

### 开发计划
- [ ] 支持更多的称呼识别模式
- [ ] 添加性别识别API接口
- [ ] 支持批量导入用户信息
- [ ] 添加称呼黑名单功能

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 👨‍💻 作者

- **xSapientia** - *Initial work* - [GitHub](https://github.com/xSapientia)

## 🙏 致谢

- 感谢 [AstrBot](https://github.com/Soulter/AstrBot) 项目提供的优秀框架
- 感谢所有提出建议和反馈的用户

---

<div align="center">

如果这个插件对你有帮助，请给个 ⭐ Star！

[报告问题](https://github.com/xSapientia/astrbot_plugin_gender_detector/issues) · [功能建议](https://github.com/xSapientia/astrbot_plugin_gender_detector/issues) · [查看更多插件](https://github.com/xSapientia)

</div>
```

这个插件实现了你要求的所有功能：

1. **性别识别和称呼管理**：通过智能分析用户昵称和历史消息来识别性别和管理称呼
2. **缓存机制**：缓存用户的性别信息和称呼，避免重复处理
3. **智能识别历史消息**：自动从对话中学习用户的称呼偏好
4. **优先级系统**：按照 `本人强调 > 他人称呼 > 默认称呼` 的优先级管理
5. **可配置缓存数量**：支持配置每个用户最多缓存的称呼数量
6. **数据存储位置**：遵循AstrBot规范，存储在 `data/plugin_data` 目录
7. **gender指令**：支持查看自己或@他人的性别信息
8. **调试模式**：配置中可以开启调试信息输出

插件会在LLM请求时自动注入用户的性别和称呼信息，帮助AstrBot更好地识别和称呼用户。
