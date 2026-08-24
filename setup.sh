#!/usr/bin/env bash
# =====================================================
#  IRIS 자동 설치 · 환경 구성 (Linux / macOS)
#
#  사용법:
#    chmod +x setup.sh
#    ./setup.sh              # 기본 설치
#    ./setup.sh --recreate   # .venv 새로 만들기
#    ./setup.sh --run        # 설치 후 바로 실행
# =====================================================
set -uo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv"
MIN_MAJOR=3
MIN_MINOR=11
RECREATE=0
RUN_AFTER=0

for arg in "$@"; do
  case "$arg" in
    --recreate) RECREATE=1 ;;
    --run)      RUN_AFTER=1 ;;
    -h|--help)  sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "알 수 없는 옵션: $arg" >&2; exit 1 ;;
  esac
done

RED=$'\033[31m'; GREEN=$'\033[32m'; CYAN=$'\033[36m'; YELLOW=$'\033[33m'; GRAY=$'\033[90m'; OFF=$'\033[0m'
STEP=0
step() { STEP=$((STEP+1)); printf '\n%s[%d/6] %s%s\n' "$CYAN" "$STEP" "$1" "$OFF"; }
ok()   { printf '  %sOK%s   %s\n' "$GREEN" "$OFF" "$1"; }
info() { printf '  %s...  %s%s\n' "$GRAY" "$1" "$OFF"; }
warn() { printf '  %s경고 %s%s\n' "$YELLOW" "$1" "$OFF"; }
fail() {
  printf '\n%s설치 실패: %s%s\n' "$RED" "$1" "$OFF"
  shift
  if [ "$#" -gt 0 ]; then
    printf '\n%s해결 방법:%s\n' "$YELLOW" "$OFF"
    for h in "$@"; do printf '  - %s\n' "$h"; done
  fi
  echo
  exit 1
}

printf '\n%s===============================================%s\n' "$CYAN" "$OFF"
printf '%s  IRIS 자동 설치%s\n' "$CYAN" "$OFF"
printf '%s  경로: %s%s\n' "$GRAY" "$ROOT" "$OFF"
printf '%s===============================================%s\n' "$CYAN" "$OFF"

# ------------------------------------------------- 1. Python
step "Python 3.$MIN_MINOR 이상 확인"
PY=""
for cand in python3.13 python3.12 python3.11 python3 python; do
  command -v "$cand" >/dev/null 2>&1 || continue
  v="$("$cand" -c 'import sys; print("%d %d" % sys.version_info[:2])' 2>/dev/null)" || continue
  maj="${v% *}"; min="${v#* }"
  if [ "$maj" -gt "$MIN_MAJOR" ] || { [ "$maj" -eq "$MIN_MAJOR" ] && [ "$min" -ge "$MIN_MINOR" ]; }; then
    PY="$cand"; PYV="$maj.$min"; break
  fi
done
[ -n "$PY" ] || fail "Python $MIN_MAJOR.$MIN_MINOR 이상을 찾지 못했습니다." \
  "Ubuntu/Debian: sudo apt install python3.12 python3.12-venv" \
  "Fedora: sudo dnf install python3.12" \
  "macOS: brew install python@3.12"
ok "Python $PYV ($PY)"

# ------------------------------------------------- 2. venv
step "가상환경(.venv) 준비"
if [ "$RECREATE" -eq 1 ] && [ -d "$VENV" ]; then
  info "--recreate: 기존 .venv 삭제"
  rm -rf "$VENV"
fi
VENV_PY="$VENV/bin/python"
if [ -x "$VENV_PY" ]; then
  ok ".venv 이미 존재 — 재사용 (새로 만들려면 --recreate)"
else
  info "생성 중..."
  "$PY" -m venv "$VENV" || fail "가상환경 생성에 실패했습니다." \
    "Debian 계열은 venv 모듈이 별도 패키지입니다: sudo apt install python3-venv"
  [ -x "$VENV_PY" ] || fail "가상환경이 만들어지지 않았습니다." "sudo apt install python3-venv 후 재시도"
  ok "생성 완료: $VENV"
fi

# ------------------------------------------------- 3. pip
step "pip 업그레이드"
if "$VENV_PY" -m pip install --upgrade pip --disable-pip-version-check -q; then
  ok "pip 최신"
else
  warn "pip 업그레이드 실패 — 기존 pip으로 계속합니다"
fi

# ------------------------------------------------- 4. 의존성
step "의존성 설치 (requirements.txt) — 수 분 걸릴 수 있습니다"
"$VENV_PY" -m pip install -r "$ROOT/requirements.txt" --disable-pip-version-check \
  || fail "의존성 설치에 실패했습니다." \
       "네트워크/프록시 상태를 확인하세요" \
       "Linux에서 PyQt6 실행에는 시스템 라이브러리가 더 필요할 수 있습니다: sudo apt install libgl1 libegl1 libxkbcommon-x11-0 libxcb-cursor0" \
       "./setup.sh --recreate 로 가상환경을 새로 만들어 재시도"
ok "설치 완료"

# ------------------------------------------------- 5. .env
step "환경 설정(.env) 준비"
if [ -f "$ROOT/.env" ]; then
  ok ".env 이미 존재 — 건드리지 않음"
elif [ -f "$ROOT/.env.example" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  ok ".env.example → .env 복사"
  info "API 키는 나중에 앱의 시작 위저드에서 넣어도 됩니다"
else
  warn ".env.example 이 없어 건너뜁니다"
fi

# ------------------------------------------------- 6. 검증
step "설치 검증"
if "$VENV_PY" - <<'PYCHECK'
import importlib, sys
missing = []
for mod in ("PyQt6.QtWidgets", "PyQt6.QtWebEngineWidgets", "psutil", "mss",
            "PIL", "markdown", "dotenv", "yaml", "numpy"):
    try:
        importlib.import_module(mod)
    except Exception as exc:
        missing.append("%s (%s)" % (mod, exc.__class__.__name__))
if missing:
    print("MISSING: " + ", ".join(missing))
    sys.exit(1)
print("OK")
PYCHECK
then
  ok "핵심 패키지 정상 (PyQt6 포함)"
else
  fail "핵심 패키지 import 검증 실패" \
    "./setup.sh --recreate 로 재설치" \
    "Linux: sudo apt install libgl1 libegl1 libxkbcommon-x11-0 libxcb-cursor0"
fi

# ------------------------------------------------- 마무리
printf '\n%s===============================================%s\n' "$GREEN" "$OFF"
printf '%s  설치 완료%s\n' "$GREEN" "$OFF"
printf '%s===============================================%s\n\n' "$GREEN" "$OFF"
echo "실행:      ./run.sh"
echo "첫 실행 시 시작 위저드가 Ollama · Hermes 설치를 이어서 안내합니다."
echo
printf '%s참고: 시작 프로토콜의 자동 설치는 Windows(winget) 기준으로 작성돼 있습니다.%s\n' "$GRAY" "$OFF"
printf '%s      Linux/macOS 에서는 Ollama·Hermes 를 직접 설치해야 할 수 있습니다.%s\n\n' "$GRAY" "$OFF"

if [ "$RUN_AFTER" -eq 1 ]; then
  echo "IRIS 를 실행합니다..."
  exec "$ROOT/run.sh"
fi
