# AstrBot 性别识别插件

自动识别用户性别并在 LLM 请求时插入相应提示词的插件。

## 功能特性

- 🔍 自动识别用户性别（支持 QQ 平台）
- 💾 性别信息缓存，避免重复 API 调用
- 🎯 根据性别在 LLM prompt 中插入不同提示词
- 🗣️ 支持自定义敬语称呼
- 🐛 调试模式，方便排查问题
- ⚡ 高性能缓存机制

## 使用方法

### 基础命令

- `/gender` - 查看自己的性别识别结果
- `/gender_cache` - 查看缓存信息（需启用调试模式）
- `/gender_clear_cache` - 清除所有缓存（需启用调试模式）
- `/gender_debug` - 查看详细调试信息（需启用调试模式）

### 配置说明

在 AstrBot 管理面板中可以配置以下选项：

1. **基础设置**
   - `enable_plugin`: 是否启用插件
   - `enable_debug`: 是否启用调试模式

2. **提示词设置**
   - `male_prompt`: 男性用户的提示词
   - `female_prompt`: 女性用户的提示词
   - `unknown_prompt`: 性别未知时的提示词
   - `prompt_position`: 提示词插入位置（prefix/suffix）

3. **敬语设置**
   - `enable_honorific`: 是否启用敬语
   - `male_honorific`: 男性敬语（如"先生"）
   - `female_honorific`: 女性敬语（如"女士"）
   - `unknown_honorific`: 性别未知时的称呼

4. **缓存设置**
   - `cache_expire_hours`: 缓存过期时间（小时）

## 工作原理

1. 用户发送消息时，插件会尝试获取其性别信息
2. 优先从本地缓存读取，缓存未命中则调用平台 API
3. 在 LLM 请求前，根据性别插入相应的提示词
4. 支持在提示词中加入敬语称呼

## 支持平台

- ✅ QQ (通过 aiocqhttp/NapCat/Lagrange)
- ❌ 其他平台暂不支持

## 注意事项

- 性别信息来自平台 API，可能存在用户未设置或设置为保密的情况
- 缓存文件存储在 `data/gender_cache.json`
- 建议定期清理过期缓存以节省存储空间
