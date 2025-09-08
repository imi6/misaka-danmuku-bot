# Changelog

本文档记录了项目的所有重要变更。

## [2025-09-08]

### 新增功能

- **feat**: 增强 webhook 匹配逻辑，严格区分电影和电视剧类型
  - 修改 search_video_by_keyword 函数，添加 media_type 参数支持类型过滤
  - 更新 webhook 电影匹配逻辑，确保只匹配电影类型资源
  - 更新 webhook 电视剧匹配逻辑，确保只匹配电视剧类型资源
  - 解决同名电影和电视剧的匹配冲突问题

## [2025-09-06]

### 新增功能

- **feat**: 添加 BGM 支持功能
- **feat**: 完善 IMDB 链接解析和自动导入功能
- **feat**: 添加豆瓣链接支持和媒体类型识别优化
- **feat**: 添加 TVDB 链接支持和智能回退机制
- **feat**: 优化/auto 命令交互流程：支持先输入后选择媒体类型，TMDB 链接自动识别类型直接导入

### 文档更新

- **docs**: 更新/auto 命令文档和提醒备注
- **docs**: 修改/url 命令描述

### 问题修复

- **fix**: 修复 TMDB 辅助搜索逻辑
- **fix**: 修复弹幕库选择流程中 ConversationHandler 状态管理问题
- **fix**: 修复分集刷新 all 功能：过滤无效的 episodeId，确保只处理有效的集数数据
- **fix**: 修复集数输入无响应问题

### 优化改进

- **optimize**: 优化刷新功能用户体验：在影视选择阶段输入 all 时给出明确提示，指导用户正确的操作流程
- **optimize**: 优化/refresh 功能：添加从弹幕库中选择的选项

## [2025-09-05]

### 新增功能

- **feat**: 支持 auto 文字和 tmdb 快速导入
- **feat**: 增加 token 管理
- **feat**: 增加 url 导入
- **feat**: 新命令自动中断上一层命令，避免中途操作后系统收不到新 command

### 问题修复

- **fix**: 自动导入输入 id 无响应
- **fix**: build 问题
- **fix**: Event loop is closed error

### 优化改进

- **optimize**: 标题解析 utf8
- **optimize**: 解析页面标题
- **optimize**: 优化 url 导入流程
- **optimize**: 完善 url 标题解析
- **optimize**: 解决 tg 连接池问题
- **optimize**: 优化系统性能

## [2025-09-04]

### 新增功能

- **feat**: 增加直接导入和分集导入/重构结构
- **feat**: 增加 tg 菜单

### 文档更新

- **docs**: 更新 readme 文档

### 优化改进

- **optimize**: 删除健康检查
- **optimize**: 修改健康检查内容
- **optimize**: 简化日志，只 log error
- **optimize**: 优化 workflow 流程
- **optimize**: 优化构建流程

## [2025-08-29]

### 项目初始化

- **init**: 初始化项目结构
  - 建立基础代码架构
  - 配置开发环境
  - 设置项目依赖

---

## 版本说明

- **feat**: 新功能
- **fix**: 问题修复
- **docs**: 文档更新
- **optimize**: 性能优化和改进
- **init**: 项目初始化

## 贡献指南

请在提交代码时遵循以下格式：

```
type: 简短描述

详细描述（可选）
```

其中 type 可以是：feat, fix, docs, optimize, refactor, test 等。
