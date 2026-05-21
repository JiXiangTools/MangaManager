# MangaManager

> Windows 우선, 로컬 우선 만화 라이브러리 관리 앱입니다. FastAPI API, React Web UI, Electron 데스크톱 런처로 구성됩니다.

**Languages:** [English](../README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md) | 한국어

[![Star History Chart](https://api.star-history.com/svg?repos=JiXiangTools/MangaManager&type=Date)](https://www.star-history.com/#JiXiangTools/MangaManager&Date)

MangaManager는 한 대의 컴퓨터에서 개인 만화 라이브러리를 관리, 읽기, 번역, 내보내기하려는 사용자를 위해 설계되었습니다. Windows 앱은 로컬 Web 서비스를 자동으로 시작하며, 같은 네트워크의 다른 기기에서도 Web UI에 접근할 수 있습니다.

## 주요 기능

- 만화, 챕터, 표지, 페이지 이미지를 관리합니다.
- Windows 데스크톱 클라이언트에서 폴더 단위로 만화를 가져옵니다.
- 드래그 앤 드롭으로 챕터 순서를 조정합니다.
- 세로 스크롤 모드 또는 페이지 모드로 읽습니다.
- 읽는 중 언제든지 언어를 전환합니다. 번역이 없으면 플레이스홀더가 표시됩니다.
- 비동기 프록시 번역 흐름으로 만화, 챕터, 단일 이미지를 번역합니다.
- 번역 원본 언어, 대상 언어, 모델, 폰트, 동시 처리 수를 설정합니다.
- 전체 만화 또는 하나의 챕터를 `webp`, `jpg`, `png` 출력의 ZIP으로 내보냅니다.
- 브라우저와 Windows 데스크톱 셸에서 같은 React UI를 사용합니다.
- Web 접근에는 임시 비밀번호가 필요하며, 신뢰된 데스크톱 클라이언트는 직접 접근합니다.
- 내장 Python 및 PostgreSQL 런타임이 포함된 자체 포함 Windows 빌드를 패키징합니다.

## 프로젝트 상태

이 프로젝트는 활발히 개발 중입니다. 현재 앱 버전은 `1.0.0`입니다.

현재 저장소에는 애플리케이션 소스, 테스트, Windows 패키징 스크립트가 포함되어 있습니다. 공개 오픈 소스 프로젝트로 배포하기 전에 필요한 경우 프로젝트 거버넌스 문서를 검토하세요.

## 아키텍처

```text
MangaManager
|-- backend/   FastAPI, SQLAlchemy, Alembic, PostgreSQL-ready API
|-- frontend/  React + Vite + TypeScript 공유 UI
|-- windows/   Electron 런처 및 Windows 패키징 스크립트
`-- shared/    공유 제품 메타데이터와 카탈로그 리소스
```

런타임 데이터는 다음 위치에 저장됩니다.

```text
data/
|-- library/   만화 이미지, 표지, 번역된 이미지 파일
|-- exports/   생성된 ZIP 내보내기 파일
`-- tmp/       임시 파일
```

## 요구 사항

로컬 개발:

- Python 3.11+
- Node.js 18+
- 프로덕션과 유사한 개발을 위한 PostgreSQL 16+
- 로컬 PostgreSQL용 Docker, 선택 사항

Windows 패키징:

- Windows 빌드 머신
- `windows/runtime/python`에 복사된 Python 런타임
- `windows/runtime/postgresql`에 복사된 PostgreSQL 런타임

## 빠른 시작

PostgreSQL을 시작합니다.

```bash
docker compose up -d postgres
```

백엔드를 시작합니다.

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

프론트엔드를 시작합니다.

```bash
cd frontend
npm install
npm run dev
```

터미널에 표시되는 Vite 개발 서버를 엽니다. 백엔드에서 직접 호스팅하려면 먼저 프론트엔드를 빌드한 뒤 `http://127.0.0.1:8765`를 엽니다.

```bash
cd frontend
npm run build
```

## Windows 데스크톱 클라이언트

Electron 클라이언트는 로컬 FastAPI 서비스를 시작하고 `/api/health`를 기다린 다음 로컬 Web UI를 로드합니다. 데스크톱 모드에서는 API 요청에 데스크톱 클라이언트 헤더가 포함되므로 Windows 앱에는 Web 임시 비밀번호가 필요하지 않습니다. 브라우저와 LAN 접근에는 여전히 임시 비밀번호가 필요합니다.

개발 모드로 데스크톱 클라이언트를 실행합니다.

```bash
cd windows
npm install
npm run dev
```

## 내장 런타임

패키징된 Windows 앱은 자체 포함 형태를 의도합니다. 필요한 레이아웃은 다음과 같습니다.

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

Windows 빌드 머신에서 런타임을 준비합니다.

```powershell
cd windows
npm run prepare:runtime -- -PythonRoot "C:\Python311" -PostgresRoot "C:\PostgreSQL\16"
```

런처는 첫 실행 시 포터블 앱 옆의 `data/postgres` 아래에 PostgreSQL을 초기화하고 백엔드를 다음 주소로 연결합니다.

```text
postgresql+psycopg://mangamanager@127.0.0.1:<postgresPort>/mangamanager
```

자세한 내용은 [windows/runtime/README.md](../windows/runtime/README.md)를 참조하세요.

## Windows ZIP 빌드

```bash
cd windows
npm install
npm run dist:win:zip
```

`npm run dist:win:zip`은 프론트엔드를 빌드하고, 내장 런타임을 검증한 뒤 Electron Builder로 Windows ZIP 패키지를 생성합니다.

## 번역

MangaManager는 비동기 프록시 번역 흐름을 사용합니다.

```text
POST /api/v1/translated/async
GET  /api/v1/translated/async/{plugin_id}
download translated_url
```

만화와 챕터 번역은 범위를 페이지 이미지로 나누고 제한된 동시 처리로 실행합니다. 번역 요청에는 다음 항목이 포함됩니다.

- `source_language`
- `target_language`
- `model_id`
- `font_style`
- `from=manager`
- `version=<MangaManager version>`

## 설정

백엔드 설정은 `MANGAMANAGER_` 환경 변수 접두사를 사용합니다.

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `MANGAMANAGER_DATABASE_URL` | `sqlite:///./data/mangamanager.db` | SQLAlchemy 데이터베이스 URL입니다. 프로덕션과 유사한 사용에는 PostgreSQL을 사용하세요. |
| `MANGAMANAGER_DATA_DIR` | `./data` | 라이브러리, 내보내기, 임시 파일 루트입니다. |
| `MANGAMANAGER_TEMP_PASSWORD` | empty | Web 임시 비밀번호입니다. |
| `MANGAMANAGER_TEMP_PASSWORD_HASH` | empty | 선택적 Web 비밀번호 해시입니다. |
| `MANGAMANAGER_SESSION_SECRET` | `dev-session-secret` | Web 세션 서명 시크릿입니다. |
| `MANGAMANAGER_DESKTOP_TOKEN` | empty | 런처가 사용하는 로컬 데스크톱 접근 토큰입니다. |
| `MANGAMANAGER_TRANSLATION_BASE_URL` | `https://www.mangatranslate.com` | 번역 계정 API 기본 URL입니다. |
| `MANGAMANAGER_TRANSLATION_PROXY_BASE` | `https://plugin-server.mangatranslate.com` | 비동기 프록시 API 기본 URL입니다. |

## 테스트

백엔드 테스트를 실행합니다.

```bash
python -m pytest backend/tests/test_api.py backend/tests/test_translation_worker.py
```

프론트엔드를 빌드합니다.

```bash
cd windows
npm run build:frontend
```

## 보안 참고 사항

- Web UI는 신뢰할 수 있는 로컬 또는 LAN 사용을 의도합니다.
- 브라우저 접근에는 설정된 임시 비밀번호가 필요합니다.
- 데스크톱 클라이언트는 신뢰되며 설계상 임시 비밀번호를 우회합니다.
- 공개 HTTPS 배포, 다중 사용자 권한, 원격 호스팅은 v1 범위에 포함되지 않습니다.

## 기여

저장소가 공개되면 issue와 pull request를 환영합니다. 변경 범위를 명확히 유지하고, 백엔드 동작에는 테스트를 추가하며, UI 변경을 제출하기 전에 프론트엔드 빌드를 실행하세요.

## 라이선스

이 프로젝트는 MIT License에 따라 라이선스가 부여됩니다. 자세한 내용은 [LICENSE](../LICENSE)를 참조하세요.
