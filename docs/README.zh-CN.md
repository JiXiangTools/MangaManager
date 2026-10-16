# MangaManager

> Windows 优先、本地优先的漫画库管理工具，包含 FastAPI API、React Web UI 和 Electron 桌面启动器。

**语言：** [English](../README.md) | 简体中文 | [日本語](README.ja.md) | [한국어](README.ko.md)

[![Star History Chart](https://api.star-history.com/svg?repos=JiXiangTools/MangaManager&type=Date)](https://www.star-history.com/#JiXiangTools/MangaManager&Date)

MangaManager 面向希望在一台机器上管理、阅读、翻译和导出个人漫画库的用户。Windows 应用会自动启动本地 Web 服务，并可以让同一局域网内的其他设备访问 Web UI。

## 核心功能

- 管理漫画、章节、封面和页面图片。
- 从 Windows 桌面客户端按文件夹导入整本漫画。
- 通过拖拽调整章节顺序。
- 支持条漫模式和分页模式阅读。
- 阅读时可随时切换语言；缺少翻译时显示占位内容。
- 通过异步代理翻译流程翻译漫画、章节或单张图片。
- 配置翻译源语言、目标语言、模型、字体和并发数。
- 将整本漫画或单个章节导出为 ZIP，输出格式支持 `webp`、`jpg` 或 `png`。
- 浏览器和 Windows 桌面壳共用同一套 React UI。
- Web 访问需要临时密码，可信桌面客户端可直接访问。
- 使用嵌入式 Python 和 PostgreSQL 运行时打包自包含 Windows 构建。

## 项目状态

本项目正在积极开发中。当前应用版本为 `1.0.1`。

仓库目前包含应用源码、测试和 Windows 打包脚本。作为公开开源项目发布前，可按需补充项目治理文档。

## 架构

```text
MangaManager
|-- backend/   FastAPI、SQLAlchemy、Alembic、PostgreSQL-ready API
|-- frontend/  React + Vite + TypeScript 共享 UI
|-- windows/   Electron 启动器和 Windows 打包脚本
`-- shared/    共享产品元数据和目录资源
```

运行时数据存储在：

```text
data/
|-- library/   漫画图片、封面和翻译后的图片文件
|-- exports/   生成的 ZIP 导出文件
`-- tmp/       临时文件
```

## 环境要求

打包后的 Windows 应用需要：

- Windows 构建机器
- Node.js 18+
- 复制到 `windows/runtime/python` 的 Python 运行时
- 复制到 `windows/runtime/postgresql` 的 PostgreSQL 运行时

本地源码开发需要：

- Python 3.11+
- Node.js 18+
- PostgreSQL 16+，用于接近生产环境的开发
- Docker，可选，用于本地 PostgreSQL

## 快速启动

主要使用路径是先构建 Windows ZIP，然后通过 Windows 应用运行 MangaManager。应用会自动启动内嵌 PostgreSQL 数据库和 FastAPI 后端服务。

在 Windows 构建机器上准备内嵌运行时：

```powershell
cd windows
npm run prepare:runtime -- -PythonRoot "C:\Python311" -PostgresRoot "C:\PostgreSQL\16"
```

构建 Windows ZIP：

```bash
cd windows
npm install
npm run dist:win:zip
```

解压生成的 `windows/dist/MangaManager-<version>-win-x64.zip`，然后运行 `MangaManager.exe`。首次启动时，应用会在便携应用旁边的 `data/postgres` 下初始化 PostgreSQL，启动后端服务，等待 `/api/health` 就绪，并加载本地 Web UI。

## 本地开发

如果需要不打包直接进行源码开发，请手动启动 PostgreSQL：

```bash
docker compose up -d postgres
```

启动后端：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
export MANGAMANAGER_DATABASE_URL=postgresql+psycopg://mangamanager:mangamanager@localhost:55432/mangamanager
export MANGAMANAGER_TEMP_PASSWORD=devpass
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8765
```

启动前端：

```bash
cd frontend
npm install
npm run dev
```

打开终端中显示的 Vite 开发服务器地址。若要直接通过后端托管访问，请先构建前端，然后打开 `http://127.0.0.1:8765`。

```bash
cd frontend
npm run build
```

## Windows 桌面客户端

Electron 客户端是打包后正常使用的运行入口。它会按需启动内嵌 PostgreSQL 进程，启动本地 FastAPI 服务，等待 `/api/health` 就绪后加载本地 Web UI。在桌面模式下，API 请求会带上桌面客户端请求头，因此 Windows 应用不需要 Web 临时密码。浏览器和局域网访问仍然需要临时密码。

以开发模式运行桌面客户端：

```bash
cd windows
npm install
npm run dev
```

## 嵌入式运行时

打包后的 Windows 应用设计为自包含。它期望以下目录结构：

```text
windows/runtime/
  python/
    python.exe
    Lib/site-packages/...
  postgresql/
    bin/postgres.exe
    bin/initdb.exe
    bin/createdb.exe
```

创建 ZIP 前，请在 Windows 构建机器上准备运行时：

```powershell
cd windows
npm run prepare:runtime -- -PythonRoot "C:\Python311" -PostgresRoot "C:\PostgreSQL\16"
```

启动器首次运行时会在便携应用旁边的 `data/postgres` 下初始化 PostgreSQL，并将后端指向：

```text
postgresql+psycopg://mangamanager@127.0.0.1:<postgresPort>/mangamanager
```

详情请参见 [windows/runtime/README.md](../windows/runtime/README.md)。

## 构建 Windows ZIP

```bash
cd windows
npm install
npm run dist:win:zip
```

`npm run dist:win:zip` 会构建前端、验证嵌入式运行时，并使用 Electron Builder 创建 Windows ZIP 包。请将这个 ZIP 分发给 Windows 用户；用户解压后启动 `MangaManager.exe`，无需手动启动 PostgreSQL 或后端。

## 翻译

MangaManager 使用异步代理翻译流程：

```text
POST /api/v1/translated/async
GET  /api/v1/translated/async/{plugin_id}
download translated_url
```

漫画和章节翻译会将范围拆分为页面图片，并以有限并发处理。翻译请求包含：

- `source_language`
- `target_language`
- `model_id`
- `font_style`
- `from=manager`
- `version=<MangaManager version>`

## 配置

后端配置使用 `MANGAMANAGER_` 环境变量前缀。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MANGAMANAGER_DATABASE_URL` | `sqlite:///./data/mangamanager.db` | SQLAlchemy 数据库 URL。接近生产环境时建议使用 PostgreSQL。 |
| `MANGAMANAGER_DATA_DIR` | `./data` | 漫画库、导出文件和临时文件根目录。 |
| `MANGAMANAGER_TEMP_PASSWORD` | empty | Web 临时密码。 |
| `MANGAMANAGER_TEMP_PASSWORD_HASH` | empty | 可选的 Web 密码哈希。 |
| `MANGAMANAGER_SESSION_SECRET` | `dev-session-secret` | Web 会话签名密钥。 |
| `MANGAMANAGER_DESKTOP_TOKEN` | empty | 启动器使用的本地桌面访问令牌。 |
| `MANGAMANAGER_TRANSLATION_BASE_URL` | `https://www.mangatranslate.com` | 翻译账号 API 基础 URL。 |
| `MANGAMANAGER_TRANSLATION_PROXY_BASE` | `https://plugin-server.mangatranslate.com` | 异步代理 API 基础 URL。 |

## 测试

运行后端测试：

```bash
python -m pytest backend/tests/test_api.py backend/tests/test_translation_worker.py
```

构建前端：

```bash
cd windows
npm run build:frontend
```

## 安全说明

- Web UI 面向可信本机或局域网使用。
- 浏览器访问需要配置的临时密码。
- 桌面客户端被视为可信客户端，并按设计绕过临时密码。
- v1 不包含公开 HTTPS 部署、多用户权限和远程托管。

## 贡献

仓库发布后欢迎提交 issue 和 pull request。请保持变更范围清晰，为后端行为添加测试，并在提交 UI 变更前运行前端构建。

## 许可证

本项目基于 MIT License 授权。详情请参见 [LICENSE](../LICENSE)。
