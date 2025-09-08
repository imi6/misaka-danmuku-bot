# TMDB 代理配置说明

本系统支持通过代理访问 TMDB API，适用于网络受限或需要使用自建代理的场景。

## 配置方法

### 1. 环境变量配置

在 `.env` 文件中添加以下配置：

```bash
# TMDB API 密钥（必需）
TMDB_API_KEY=your_tmdb_api_key_here

# TMDB 代理URL（可选）
TMDB_PROXY_URL=https://your-tmdb-proxy.com/api/tmdb
```

### 2. 代理URL格式

代理URL应该指向您的TMDB代理服务器的基础路径，系统会自动添加 `/3` 后缀来构建完整的API路径。

**示例：**
- 代理URL: `https://tmdb-proxy.example.com`
- 实际API调用: `https://tmdb-proxy.example.com/3/search/tv`

如果您的代理URL已经包含 `/3` 路径，系统会自动识别并直接使用：
- 代理URL: `https://tmdb-proxy.example.com/api/v3`
- 实际API调用: `https://tmdb-proxy.example.com/api/v3/search/tv`

## 工作原理

1. **未配置代理时**：系统使用官方TMDB API (`https://api.themoviedb.org/3`)
2. **配置代理后**：系统自动切换到代理URL，所有TMDB API调用都会通过代理进行
3. **代理验证**：系统启动时会自动验证代理的可用性

## 日志输出

配置代理后，您会在日志中看到类似信息：

```
✅ 使用TMDB代理: https://your-proxy.com/3
✅ TMDB API 配置已加载并验证通过，将启用辅助搜索功能
```

## 注意事项

1. **API密钥兼容性**：确保您的代理服务器支持标准的TMDB API密钥验证
2. **网络连接**：代理服务器需要能够正常访问，否则TMDB功能将被禁用
3. **SSL证书**：确保代理服务器使用有效的SSL证书
4. **API兼容性**：代理服务器应该完全兼容TMDB API v3的接口规范

## 故障排除

如果代理配置不工作，请检查：

1. 代理URL是否正确且可访问
2. 代理服务器是否支持TMDB API
3. 网络连接是否正常
4. SSL证书是否有效

查看应用日志获取详细的错误信息。