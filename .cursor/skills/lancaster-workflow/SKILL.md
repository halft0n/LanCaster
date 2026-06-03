---
name: lancaster-workflow
description: LanCaster 项目开发规范与经验总结。提交代码前必须执行 lint 检查，遵循异步编码约定，参考已实现的稳定性模式。Use when developing, committing, or reviewing code in the LanCaster project.
---

# LanCaster 开发规范

## 提交前检查（必须）

提交代码前必须执行以下命令并确保通过：

```bash
python -m ruff format --check .
python -m ruff check .
python -m pytest tests/ -q
```

如果 format 检查失败，运行 `python -m ruff format .` 自动格式化后再提交。

## 代码规范

### 行长度
- 最大 100 字符（ruff 配置于 pyproject.toml）
- 长字符串拆分为多行拼接

### 异步编码
- 文件 I/O 使用 `asyncio.get_running_loop().run_in_executor(None, func)`
- 避免 `asyncio.get_event_loop()`，始终使用 `asyncio.get_running_loop()`
- 网络请求使用 `aiohttp.ClientTimeout` 明确超时

### 错误处理
- 瞬时错误（OSError, ConnectionError, TimeoutError）可重试
- 逻辑错误（ValueError, PlaybackError 无 retryable cause）立即抛出
- 下载/写入失败时清理临时文件（try/finally + unlink）

## 架构模式参考

### 重试机制
- `_with_retry` 装饰器仅重试 `_RETRYABLE_ERRORS`
- 重试前调用 `invalidate(udn)` 清除 DMR 缓存
- 指数退避: `0.5 * (attempt + 1)` 秒

### 并发保护
- per-UDN 锁保护 DMR 缓存创建
- `_queue_lock` + `_advancing` 标志防止队列重复推进
- `_register_lock` 保护设备注册

### 设备发现
- `scan()` 增量合并，不 `clear()` 避免列表闪烁
- `watch()` 常驻监听，location 变更时通知 controller 清缓存
- 新设备或 location 变更都触发 `_on_device_change`

### 进度持久化
- 使用实际 cast target（文件路径或 URL）作为 key，不用 TrackURI
- 每 30s 轮询保存一次
- 接近结尾（duration - 5s）时自动清除记录

## Git 规范

- commit message 风格: `feat:` / `fix:` / `chore:` 前缀
- `.githooks/commit-msg` 自动过滤 Co-authored-by: Cursor
- 确保 `git config core.hooksPath .githooks`
