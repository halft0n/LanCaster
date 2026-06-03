# LanCaster 架构与设计文档

## 1. 项目概述

LanCaster（LAN + Caster）是一款基于 DLNA/UPnP 协议的全功能视频投屏工具。它允许用户在同一 WiFi 局域网下，将 Windows PC 上的视频文件、在线视频 URL、甚至桌面画面投送到智能电视上播放。

### 1.1 名称由来

- **LAN** — Local Area Network（局域网）
- **Caster** — 投屏器
- **Lancaster** — 英文实词（兰开斯特），好记好拼

### 1.2 核心场景

| 场景 | 说明 | 状态 |
|------|------|------|
| 本地文件投屏 | 选择 PC 上的视频文件推送到电视播放 | Phase 1 已实现 |
| 在线 URL 投屏 | 将网络视频 URL 直接投送到电视 | Phase 2 |
| 媒体库共享 | PC 作为 DLNA Media Server，电视主动浏览 | Phase 3 |
| 桌面镜像 | PC 桌面实时画面串流到电视 | Phase 3 |

---

## 2. 技术架构

### 2.1 分层设计

```
┌─────────────────────────────────────────────────┐
│           Presentation Layer                    │
│  ┌───────────────┐  ┌────────────────────────┐  │
│  │  lancaster-cli│  │  GUI (未来)            │  │
│  │  (Click+Rich) │  │  PyQt6 / Tauri / Web   │  │
│  └───────┬───────┘  └──────────┬─────────────┘  │
├──────────┼─────────────────────┼────────────────┤
│          │    lancaster-core   │                 │
│  ┌───────▼─────────────────────▼──────────────┐ │
│  │  DeviceDiscovery  │  MediaController       │ │
│  │  MediaServer      │  Transcoder            │ │
│  │  DesktopMirror    │  URLProxy              │ │
│  │  HTTPFileServer   │  DIDLBuilder           │ │
│  └───────────────────┴────────────────────────┘ │
├─────────────────────────────────────────────────┤
│           External Dependencies                 │
│  async_upnp_client  │  aiohttp  │  FFmpeg      │
└─────────────────────────────────────────────────┘
```

### 2.2 设计原则

1. **核心库与 UI 分离** — `lancaster/` 是纯 Python 库，不依赖任何 GUI 框架。CLI、Web UI、桌面 GUI 都是独立的消费者。
2. **异步优先** — 所有 I/O 操作基于 `asyncio`，与 `async_upnp_client` 的事件循环统一。
3. **渐进式功能** — 每个模块独立可用，用户可以只用设备发现，也可以只用文件服务器。
4. **容错优先** — 网络设备不可靠，所有设备交互都有超时和异常处理。

---

## 3. DLNA/UPnP 协议基础

### 3.1 三角色模型

LanCaster 的 DLNA 实现基于 UPnP AV 架构的三角色模型：

```
      ┌──────────────────────┐
      │  DMC (Controller)    │
      │  LanCaster 软件      │
      └──────┬───────┬───────┘
             │       │
    SOAP     │       │  SOAP
  控制命令   │       │  浏览请求
             │       │
      ┌──────▼──┐ ┌──▼─────────┐
      │  DMR    │ │  DMS       │
      │  电视   │ │  PC/NAS    │
      │(播放端) │ │(媒体源)    │
      └────┬────┘ └──────┬─────┘
           │              │
           │   HTTP GET   │
           │◄─────────────┘
           │  (拉取媒体流)
```

| 角色 | UPnP 设备类型 | LanCaster 中的体现 |
|------|--------------|-------------------|
| DMS (Digital Media Server) | MediaServer | `HTTPFileServer` — 提供本地文件的 HTTP 访问 |
| DMR (Digital Media Renderer) | MediaRenderer | 电视 — 接收并播放媒体 |
| DMC (Digital Media Controller) | Control Point | `MediaController` — 发现设备、控制播放 |

### 3.2 协议栈

```
┌─────────────────────────────────┐
│  DLNA Guidelines                │  ← 格式/Profile 规范
├─────────────────────────────────┤
│  UPnP AV                       │
│  ├─ ContentDirectory (Browse)   │  ← 媒体库浏览
│  ├─ AVTransport (Play/Pause...) │  ← 播放控制
│  ├─ RenderingControl (Volume)   │  ← 音量/亮度
│  └─ ConnectionManager           │  ← 格式协商
├─────────────────────────────────┤
│  UPnP Device Architecture      │
│  ├─ SSDP (发现)                 │  ← UDP 239.255.255.250:1900
│  ├─ SOAP (控制)                 │  ← HTTP POST + XML
│  ├─ GENA (事件)                 │  ← HTTP SUBSCRIBE/NOTIFY
│  └─ Device Description (XML)    │  ← HTTP GET
├─────────────────────────────────┤
│  HTTP / TCP / UDP / IP          │
└─────────────────────────────────┘
```

### 3.3 投屏工作流

```
时间线 →

PC (LanCaster)                              电视 (DMR)
     │                                          │
     │── SSDP M-SEARCH (UDP 多播) ──────────────>│
     │<── SSDP Response (Location URL) ─────────│
     │                                          │
     │── HTTP GET description.xml ──────────────>│
     │<── Device Description XML ───────────────│
     │                                          │
     │  [启动本地 HTTP 服务器 :8200]              │
     │                                          │
     │── SOAP SetAVTransportURI ────────────────>│
     │   (告诉电视：播放 http://pc:8200/file/xx) │
     │<── 200 OK ──────────────────────────────│
     │                                          │
     │── SOAP Play ─────────────────────────────>│
     │<── 200 OK ──────────────────────────────│
     │                                          │
     │                    │<── HTTP GET /file/xx │
     │                    │── 206 Partial ──────>│
     │                    │    (视频数据)         │
     │                    │                      │
     │── SOAP GetPositionInfo ──────────────────>│
     │<── 当前播放位置 ────────────────────────│
```

---

## 4. 模块详细设计

### 4.1 DeviceDiscovery (`lancaster/discovery.py`)

**职责**：在局域网中发现 DLNA 设备（电视、音箱、NAS 等）。

**实现**：
- 使用 `async_upnp_client.ssdp_listener.SsdpListener` 监听 SSDP 多播
- 发送 M-SEARCH 请求后等待指定超时时间
- 收到响应后通过 `UpnpFactory` 获取设备描述 XML
- 根据设备/服务类型分类为 Renderer 或 Server
- 内部缓存已发现设备，支持按名称/IP 查找

**API**：

```python
class DeviceDiscovery:
    async def scan(timeout=5.0) -> list[DLNADevice]     # 一次性扫描
    async def watch(callback) -> SsdpListener            # 持续监听
    async def stop_watch() -> None                       # 停止监听
    def find_by_name(name) -> DLNADevice | None          # 按名称模糊匹配
    def find_by_ip(ip) -> DLNADevice | None              # 按 IP 精确匹配
    @property renderers -> list[DLNADevice]               # 所有渲染器
    @property servers -> list[DLNADevice]                 # 所有服务器
```

**边界条件**：
- 多网卡环境：`SsdpListener` 自动绑定，或可指定 `source` IP
- 设备描述获取失败时静默跳过（网络不稳定场景）
- 相同 UDN 的设备不会重复注册

### 4.2 HTTPFileServer (`lancaster/http_server.py`)

**职责**：提供本地文件和实时流的 HTTP 访问，供电视拉取。

**实现**：
- 基于 `aiohttp.web` 异步 HTTP 服务器
- 两类端点：`/file/{id}` 静态文件、`/stream/{id}` 实时流
- 每个文件/流注册后返回唯一 URL

**HTTP Range 支持**（电视 seek 必需）：
- 解析 `Range: bytes=start-end` 请求头
- 有 Range 时返回 `206 Partial Content` + `Content-Range`
- 无 Range 时返回 `200 OK` + 完整文件
- 256KB 分块传输，大文件友好

**DLNA 专属响应头**：
- `TransferMode.DLNA.ORG: Streaming` — 表明传输模式
- `ContentFeatures.DLNA.ORG: DLNA.ORG_OP=01;DLNA.ORG_FLAGS=...` — 支持 seek
- `Accept-Ranges: bytes` — 声明支持 Range 请求

**安全考虑**：
- 文件通过随机 UUID 映射，外部无法猜测路径
- 仅在局域网 IP 上监听

### 4.3 MediaController (`lancaster/controller.py`)

**职责**：封装对电视的所有播放控制操作。

**实现**：
- 通过 `UpnpFactory` 创建 `UpnpDevice`，再包装为 `DmrDevice`
- `DmrDevice` 提供 AVTransport 和 RenderingControl 的高层 API
- 缓存已创建的 `DmrDevice` 实例，避免重复建连

**支持的操作**：

| 操作 | UPnP Action | 方法 |
|------|------------|------|
| 播放 URL | SetAVTransportURI + Play | `play_url()` |
| 播放本地文件 | 启动 HTTP 服务 + SetURI + Play | `play_file()` |
| 暂停 | AVT:Pause | `pause()` |
| 继续 | AVT:Play | `resume()` |
| 停止 | AVT:Stop | `stop()` |
| 跳转 | AVT:Seek (ABS_TIME) | `seek()` |
| 设置音量 | RC:SetVolume | `set_volume()` |
| 获取音量 | RC:GetVolume | `get_volume()` |
| 获取状态 | AVT:GetTransportInfo + GetPositionInfo | `get_position()` |

**自动字幕发现**：
- `play_file()` 自动查找同名 `.srt` 文件
- 字幕通过 HTTP 服务器提供，在 DIDL-Lite 元数据中通过 `sec:CaptionInfoEx` 引用

### 4.4 DIDLBuilder (`lancaster/didl.py`)

**职责**：构建 UPnP 标准的 DIDL-Lite XML 元数据。

DIDL-Lite（Digital Item Declaration Language - Lite）是 UPnP 用于描述媒体元数据的 XML 格式。电视需要这些元数据来正确显示媒体标题、时长、格式等信息。

**示例输出**：

```xml
<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/"
           xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"
           xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"
           xmlns:sec="http://www.sec.co.kr/">
  <item id="0" parentID="-1" restricted="1">
    <dc:title>My Movie</dc:title>
    <upnp:class>object.item.videoItem</upnp:class>
    <res protocolInfo="http-get:*:video/mp4:*"
         duration="01:30:00">
      http://192.168.1.5:8200/file/abc123
    </res>
    <sec:CaptionInfoEx sec:type="srt">
      http://192.168.1.5:8200/file/def456
    </sec:CaptionInfoEx>
  </item>
</DIDL-Lite>
```

---

## 5. 数据模型

### 5.1 DLNADevice

表示一个已发现的 DLNA 设备。

| 字段 | 类型 | 说明 |
|------|------|------|
| name | str | 设备友好名称（如 "Living Room TV"） |
| ip | str | IP 地址 |
| location | str | UPnP description.xml 的 URL |
| device_type | DeviceType | renderer（电视）或 server（NAS） |
| manufacturer | str | 制造商 |
| model | str | 型号 |
| udn | str | 唯一设备标识（UUID） |

### 5.2 PlaybackInfo

当前播放状态快照。

| 字段 | 类型 | 说明 |
|------|------|------|
| state | TransportState | PLAYING / PAUSED / STOPPED / TRANSITIONING |
| position | timedelta | 当前播放位置 |
| duration | timedelta | 总时长 |
| volume | int | 音量 (0-100) |
| title | str | 当前播放的资源 URL |

---

## 6. CLI 设计

CLI 使用 Click 框架，每个功能对应一个子命令：

```
lancaster
├── discover          扫描设备，输出 Rich 表格
├── cast <target>     投屏（自动判断文件 vs URL）
│   ├── -d <device>   指定目标设备（模糊匹配）
│   └── -t <timeout>  设备扫描超时
├── pause             暂停
├── resume            继续
├── stop              停止
├── seek <time>       跳转（支持 HH:MM:SS / MM:SS / SS）
├── volume <level>    音量 (0-100)
└── status            显示播放状态
```

所有命令支持 `-d` 参数指定设备，未指定时使用配置的默认设备或第一个发现的 Renderer。

---

## 7. 依赖关系

### 7.1 运行时依赖

| 包 | 版本 | 用途 |
|----|------|------|
| async-upnp-client | >=0.46.0 | UPnP/DLNA 核心：SSDP 发现、SOAP 控制、GENA 事件 |
| aiohttp | >=3.9.0 | HTTP 服务器（文件服务）+ HTTP 客户端 |
| python-didl-lite | >=1.5.0 | DIDL-Lite XML 处理 |
| click | >=8.0 | CLI 框架 |
| rich | >=13.0 | 终端美化输出 |

### 7.2 外部工具

| 工具 | 用途 | 必需性 |
|------|------|--------|
| FFmpeg | 视频转码、桌面采集 | Phase 2+ 需要 |

### 7.3 为什么选这些依赖

- **async_upnp_client**：唯一在 2026 年仍活跃维护的 Python UPnP 库，Home Assistant 月下载 10 万+，AVTransport 全部 Action 封装完整。
- **aiohttp**：async_upnp_client 已依赖 aiohttp，复用不引入新依赖。
- **click**：比 argparse 更适合多子命令 CLI，比 typer 更成熟稳定。
- **rich**：一行代码实现表格/进度条/彩色输出。

---

## 8. 路线图

| Phase | 内容 | 周期 | 状态 |
|-------|------|------|------|
| 1 | 核心投屏 MVP | 1-2 周 | 已完成 |
| 2 | FFmpeg 转码 + URL 代理 + 增强控制 | 2 周 | 计划中 |
| 3 | 媒体库共享 (DMS) + 桌面镜像 | 3 周 | 计划中 |
| 4 | GUI（PyQt6 / Tauri / Web） | 开放 | 计划中 |

---

## 9. 已知限制

| 限制 | 说明 | 缓解方案 |
|------|------|---------|
| 格式兼容性 | 电视只能播放它支持的编解码器 | Phase 2 FFmpeg 实时转码 |
| DRM 内容 | DLNA 不支持加密内容 | 无法绕过，仅支持未加密媒体 |
| 字幕 | 仅支持 SRT 外挂，依赖电视端渲染 | Phase 2 FFmpeg 硬字幕烧录 |
| 桌面镜像延迟 | DLNA 协议本身导致 1-3 秒延迟 | 协议限制，无法根本解决 |
| 防火墙 | Windows 防火墙可能阻断 SSDP/HTTP | 首次运行提示用户放行 |
| 跨子网 | SSDP 多播不跨子网 | 需路由器配置多播转发 |

---

## 10. 测试策略

### 10.1 单元测试

覆盖所有不依赖网络的模块：
- `test_models.py` — 数据模型构造与默认值
- `test_utils.py` — IP 检测、MIME 推断、时间格式化
- `test_didl.py` — DIDL-Lite XML 构建与转义
- `test_config.py` — 配置文件读写
- `test_http_server.py` — HTTP Range、DLNA 头、404 处理

### 10.2 集成测试（手动）

在实际电视或 VLC（配置为 DLNA Renderer）上验证：
1. `lancaster discover` 能发现设备
2. `lancaster cast video.mp4` 能投屏播放
3. `lancaster pause / resume / stop` 能控制播放
4. `lancaster seek 00:05:00` 能跳转
5. `lancaster volume 30` 能调节音量

### 10.3 用 VLC 作为测试 DMR

```bash
# 启动 VLC 的 UPnP Renderer 模式
vlc --intf dummy --extraintf http --http-port 8080
# 在 VLC 偏好设置 > 全部 > 流输出 > UPnP > 启用 UPnP Renderer
```
