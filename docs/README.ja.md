# MangaManager

> Windows ファースト、ローカルファーストの漫画ライブラリ管理アプリです。FastAPI API、React Web UI、Electron デスクトップランチャーで構成されています。

**Languages:** [English](../README.md) | [简体中文](README.zh-CN.md) | 日本語 | [한국어](README.ko.md)

[![Star History Chart](https://api.star-history.com/svg?repos=JiXiangTools/MangaManager&type=Date)](https://www.star-history.com/#JiXiangTools/MangaManager&Date)

MangaManager は、1 台のマシンで個人の漫画ライブラリを管理、閲覧、翻訳、エクスポートしたいユーザー向けに設計されています。Windows アプリはローカル Web サービスを自動起動し、同じネットワーク内の他の端末から Web UI にアクセスできるようにします。

## 主な機能

- 漫画、チャプター、表紙、ページ画像を管理。
- Windows デスクトップクライアントからフォルダ単位で漫画をインポート。
- ドラッグアンドドロップでチャプター順を変更。
- 縦スクロール形式またはページ形式で閲覧。
- 閲覧中にいつでも言語を切り替え。翻訳がない場合はプレースホルダーを表示。
- 非同期プロキシ翻訳フローで、漫画、チャプター、単一画像を翻訳。
- 翻訳元言語、翻訳先言語、モデル、フォント、同時実行数を設定。
- 漫画全体または 1 チャプターを `webp`、`jpg`、`png` 形式の ZIP としてエクスポート。
- ブラウザと Windows デスクトップシェルで同じ React UI を使用。
- Web アクセスには一時パスワードが必要で、信頼済みデスクトップクライアントは直接アクセス可能。
- Python と PostgreSQL の組み込みランタイムを含む自己完結型 Windows ビルドをパッケージ化。

## プロジェクト状況

このプロジェクトは活発に開発中です。現在のアプリバージョンは `1.0.0` です。

リポジトリには現在、アプリケーションソース、テスト、Windows パッケージングスクリプトが含まれています。公開オープンソースプロジェクトとして公開する前に、必要に応じてプロジェクトガバナンス文書を確認してください。

## アーキテクチャ

```text
MangaManager
|-- backend/   FastAPI、SQLAlchemy、Alembic、PostgreSQL-ready API
|-- frontend/  React + Vite + TypeScript の共有 UI
|-- windows/   Electron ランチャーと Windows パッケージングスクリプト
`-- shared/    共有プロダクトメタデータとカタログリソース
```

ランタイムデータは以下に保存されます。

```text
data/
|-- library/   漫画画像、表紙、翻訳済み画像ファイル
|-- exports/   生成された ZIP エクスポート
`-- tmp/       一時ファイル
```

## 要件

ローカル開発:

- Python 3.11+
- Node.js 18+
- 本番に近い開発用の PostgreSQL 16+
- ローカル PostgreSQL 用の Docker、任意

Windows パッケージング:

- Windows ビルドマシン
- `windows/runtime/python` にコピーされた Python ランタイム
- `windows/runtime/postgresql` にコピーされた PostgreSQL ランタイム

## クイックスタート

PostgreSQL を起動します。

```bash
docker compose up -d postgres
```

バックエンドを起動します。

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

フロントエンドを起動します。

```bash
cd frontend
npm install
npm run dev
```

ターミナルに表示される Vite 開発サーバーを開きます。バックエンドから直接ホストする場合は、先にフロントエンドをビルドしてから `http://127.0.0.1:8765` を開きます。

```bash
cd frontend
npm run build
```

## Windows デスクトップクライアント

Electron クライアントはローカル FastAPI サービスを起動し、`/api/health` を待ってからローカル Web UI を読み込みます。デスクトップモードでは API リクエストにデスクトップクライアント用ヘッダーが含まれるため、Windows アプリでは Web 一時パスワードは不要です。ブラウザと LAN からのアクセスには引き続き一時パスワードが必要です。

開発モードでデスクトップクライアントを実行します。

```bash
cd windows
npm install
npm run dev
```

## 組み込みランタイム

パッケージ化された Windows アプリは自己完結型を想定しています。必要なレイアウトは以下のとおりです。

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

Windows ビルドマシンでランタイムを準備します。

```powershell
cd windows
npm run prepare:runtime -- -PythonRoot "C:\Python311" -PostgresRoot "C:\PostgreSQL\16"
```

ランチャーは初回起動時にポータブルアプリの隣の `data/postgres` に PostgreSQL を初期化し、バックエンドを以下に向けます。

```text
postgresql+psycopg://mangamanager@127.0.0.1:<postgresPort>/mangamanager
```

詳細は [windows/runtime/README.md](../windows/runtime/README.md) を参照してください。

## Windows ZIP のビルド

```bash
cd windows
npm install
npm run dist:win:zip
```

`npm run dist:win:zip` はフロントエンドをビルドし、組み込みランタイムを検証して、Electron Builder で Windows ZIP パッケージを作成します。

## 翻訳

MangaManager は非同期プロキシ翻訳フローを使用します。

```text
POST /api/v1/translated/async
GET  /api/v1/translated/async/{plugin_id}
download translated_url
```

漫画とチャプターの翻訳では対象範囲をページ画像に分割し、制限付きの同時実行で処理します。翻訳リクエストには以下が含まれます。

- `source_language`
- `target_language`
- `model_id`
- `font_style`
- `from=manager`
- `version=<MangaManager version>`

## 設定

バックエンド設定は `MANGAMANAGER_` 環境変数プレフィックスを使用します。

| 変数 | デフォルト | 説明 |
| --- | --- | --- |
| `MANGAMANAGER_DATABASE_URL` | `sqlite:///./data/mangamanager.db` | SQLAlchemy データベース URL。本番に近い用途では PostgreSQL を使用します。 |
| `MANGAMANAGER_DATA_DIR` | `./data` | ライブラリ、エクスポート、一時ファイルのルート。 |
| `MANGAMANAGER_TEMP_PASSWORD` | empty | Web 一時パスワード。 |
| `MANGAMANAGER_TEMP_PASSWORD_HASH` | empty | 任意の Web パスワードハッシュ。 |
| `MANGAMANAGER_SESSION_SECRET` | `dev-session-secret` | Web セッション署名シークレット。 |
| `MANGAMANAGER_DESKTOP_TOKEN` | empty | ランチャーが使用するローカルデスクトップアクセストークン。 |
| `MANGAMANAGER_TRANSLATION_BASE_URL` | `https://www.mangatranslate.com` | 翻訳アカウント API ベース URL。 |
| `MANGAMANAGER_TRANSLATION_PROXY_BASE` | `https://plugin-server.mangatranslate.com` | 非同期プロキシ API ベース URL。 |

## テスト

バックエンドテストを実行します。

```bash
python -m pytest backend/tests/test_api.py backend/tests/test_translation_worker.py
```

フロントエンドをビルドします。

```bash
cd windows
npm run build:frontend
```

## セキュリティメモ

- Web UI は信頼できるローカルまたは LAN での利用を想定しています。
- ブラウザアクセスには設定済みの一時パスワードが必要です。
- デスクトップクライアントは信頼済みとして扱われ、設計上、一時パスワードをバイパスします。
- v1 では公開 HTTPS デプロイ、マルチユーザー権限、リモートホスティングは対象外です。

## コントリビューション

リポジトリ公開後は issue と pull request を歓迎します。変更範囲を明確にし、バックエンドの挙動にはテストを追加し、UI 変更を提出する前にフロントエンドビルドを実行してください。

## ライセンス

このプロジェクトは MIT License の下でライセンスされています。詳細は [LICENSE](../LICENSE) を参照してください。
