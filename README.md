# AstrBot Gender Detector Plugin

一个用于识别用户性别并智能缓存用户信息的 AstrBot 插件。

## 功能特性

- 🔍 **自动性别识别**：通过 API 自动获取用户性别信息
- 💾 **智能缓存机制**：缓存用户性别和昵称信息，避免重复调用 API
- 📝 **昵称智能提取**：从用户消息中智能识别和记录用户的自称昵称
- 🎯 **优先级管理**：用户自己强调的昵称优先级高于他人的称呼
- 🔧 **灵活配置**：支持自定义提示词、缓存时长等参数
- 🐛 **调试模式**：可选的调试信息显示功能
- 🧹 **自动清理**：插件卸载时自动清理所有相关数据

## 安装方法

1. 在 AstrBot 管理面板的插件市场搜索 "Gender Detector"
2. 点击安装按钮
3. 重启 AstrBot 或重载插件

## 使用方法

### 基础命令

- `/gender` - 查看自己的性别信息
- `/gender @用户` - 查看指定用户的性别信息
- `/gender_cache` - 查看缓存统计信息

### 配置说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| enable_plugin | bool | true | 是否启用插件 |
| show_debug | bool | false | 是否显示调试信息 |
| max_nicknames | int | 3 | 每个用户最多缓存的昵称数量 |
| cache_expire_hours | int | 168 | 缓存有效期（小时） |
| male_prompt | string | [用户性别: 男性] | 男性用户的提示词 |
| female_prompt | string | [用户性别: 女性] | 女性用户的提示词 |
| unknown_prompt | string | [用户性别: 未知] | 性别未知用户的提示词 |
| prompt_position | string | prefix | 提示词插入位置 (prefix/suffix) |

## 工作原理

1. **性别检测**：
   - 首先尝试从缓存读取
   - 缓存过期或不存在时，调用平台 API 获取用户信息
   - 从 API 返回的性别字段获取性别
   - 如果 API 未返回性别，尝试从昵称推测

2. **昵称识别**：
   - 监听所有消息，识别自我介绍模式
   - 支持多种自我介绍格式（"我叫XX"、"叫我XX"等）
   - 记录昵称来源（self/others）和使用频率
   - 自动排序并保留最常用的昵称

3. **LLM 集成**：
   - 在 LLM 请求时自动注入用户性别信息
   - 可选添加用户常用昵称
   - 支持在 prompt 前后插入信息

## 数据存储

插件数据保存在以下位置：
- 缓存数据：`data/plugin_data/astrbot_plugin_gender_detector/gender_cache.json`
- 插件配置：`data/config/astrbot_plugin_gender_detector_config.json`

**注意**：插件卸载时会自动清理所有相关文件和目录。

## 注意事项

- 本插件需要平台支持获取用户信息的 API（如 QQ 平台的 get_group_member_info）
- 性别推测功能基于简单的关键词匹配，可能不够准确
- 插件会定期（每小时）自动清理过期缓存

## 更新日志

### v0.0.1 (2025-01-21)
- 初始版本发布
- 实现基础的性别识别和缓存功能
- 支持昵称智能提取
- 集成 LLM prompt 修改功能
- 完善数据存储和清理机制

## 问题反馈

如有问题或建议，请在 GitHub 仓库提交 Issue。

## 许可证

MIT License
