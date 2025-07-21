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
