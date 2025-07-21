# astrbot_plugin_gender_detector
一个通过对话和缓存智能识别用户性别，并将其注入LLM提示词的插件。

<div align="center">

[![Version](https://img.shields.io/badge/version-v0.0.1-blue.svg)](https://github.com/xSapientia/astrbot_plugin_gender_detector)
[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D3.4.36-green.svg)](https://github.com/AstrBotDevs/AstrBot)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

一个智能的用户性别识别插件，让您的 AstrBot 能够更好地理解对话上下文，实现更具个性化的回复。

</div>

## ✨ 功能特性
- **自动注入提示词**: 在每次LLM请求前，自动将识别出的用户性别（如`[用户身份：男性]`）添加到提示词中。
- **智能缓存**: 将识别出的用户性别信息进行本地缓存，避免重复识别，提高响应速度。
- **指令交互**: 提供简单的指令来查询自己或他人的性别，并支持用户主动设置自己的性别。
- **高度可配置**: 所有提示词、功能开关均可在 AstrBot 管理面板中进行可视化配置。
- **调试模式**: 内置调试开关，方便管理员查看插件的内部工作状态和缓存信息。
- **别名支持**: 核心指令支持中文别名，更符合使用习惯。


## 🎯 使用方法

### 基础指令

| 指令 | 别名 | 说明 | 权限 |
|------|------|------|------|
| `/gender` | `性别` | 查看自己的性别信息 | 所有人 |
| `/gender @用户` | `性别 @用户` | 查看被@用户的性别信息 | 所有人 |
| `/gender set [male/female]` | `性别 设置 [male/female]` | 设置自己的性别为'male'或'female' | 所有人 |

## ⚙️ 配置说明

插件支持在 AstrBot 管理面板中进行可视化配置：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enable_plugin` | bool | true | 插件总开关。 |
| `enable_debug` | bool | false | 调试模式开关。开启后`/gender`指令会返回更详细的缓存信息。 |
| `max_nickname_cache` | int | 3 | （为未来功能保留）每个用户可缓存的昵称上限。 |
| `prompt_position` | string | prefix | 性别提示词注入位置，可选`prefix`（前置）或`suffix`（后置）。 |
| `male_prompt` | text | `[用户身份：男性]` | 识别用户为男性时，注入的提示词内容。 |
| `female_prompt` | text | `[用户身份：女性]` | 识别用户为女性时，注入的提示词内容。 |
| `unknown_prompt`| text | `[用户身份：未知]` | 无法识别性别时，注入的提示词内容。 |

## 💾 数据存储

插件数据和配置保存在AstrBot的`data`目录下，以确保插件更新时数据不丢失：
- **缓存数据**: `data/plugin_data/astrbot_plugin_gender_detector/gender_cache.json`
- **插件配置**: `data/config/astrbot_plugin_gender_detector_config.json`

## 🔧 工作原理

1.  当用户发送消息给LLM时，插件会触发`on_llm_request`钩子。
2.  插件首先检查本地缓存中是否存在该用户的性别信息。
3.  如果缓存中不存在，插件会进行一个模拟的“性别识别”过程（**注意：v0.0.1版本中，此过程仅为占位符，默认返回“未知”。用户需要通过`/gender set`指令主动设置**）。
4.  获取到性别后，插件根据配置将对应的提示词（如`[用户身份：女性]`）添加到原始用户消息的前面或后面。
5.  最后，将修改后的完整请求发送给LLM。

## 🐛 故障排除 & FAQ

**Q: 为什么插件总是识别我的性别为“未知”？**
A: 这是设计的初始行为。v0.0.1版本不包含主动的性别分析功能。您需要通过指令 `/gender set male` 或 `/gender set female` 来主动设置一次您的性别，之后插件就会记住。

**Q: 插件无响应怎么办？**
1.  前往AstrBot管理面板，检查“插件管理”中本插件是否已启用。
2.  确认指令格式是否正确，例如 `/gender` 或 `/gender @张三`。
3.  查看AstrBot后台日志，确认是否有与 `astrbot_plugin_gender_detector` 相关的错误信息。

**Q: 我可以自己实现更高级的性别识别逻辑吗？**
A: 当然可以。您可以在`main.py`的`_get_user_gender_info`函数中，替换“模拟API调用/分析”部分的代码。例如，您可以调用一个外部的NLP API，或者编写一套基于用户历史发言的规则。

## 📝 更新日志

### v0.0.1 (开发中)
- ✅ 实现插件基础框架。
- ✅ 支持通过指令查询和设置性别。
- ✅ 实现性别信息本地化缓存。
- ✅ 实现LLM请求提示词注入功能。
- ✅ 添加完整的可视化配置项和调试模式。

## 🤝 贡献

欢迎通过提交 Issue 和 Pull Request 来为本项目做出贡献！

## 📄 许可证

本项目采用 MIT 许可证 - 详见 `LICENSE` 文件。

## 👨‍💻 作者

- **xSapientia** - *Initial work* - [GitHub](https://github.com/xSapientia)

## 🙏 致谢

- 感谢 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 项目提供的优秀插件框架。
- 感谢所有为开源社区做出贡献的开发者。

---

<div align="center">

如果这个插件对你有帮助，请在GitHub上给个 ⭐ Star！

</div>
