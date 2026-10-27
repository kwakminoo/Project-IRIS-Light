"""Windows 로그온 시 Hermes gateway를 백그라운드로 미리 켠다.

Iris UI 없이 `pythonw` + CLI만 돌린다. 작업은 하나(`ONLOGON`)만 둔다 —
루틴 깨우기(`routine_wake`)와 같은 schtasks 패턴이다.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from iris.system.routine_wake import _decode, python_runner

TASK_NAME = r"\IrisLight\HermesGatewayWarm"
_TIMEOUT_SEC = 15
_NOT_FOUND_HINTS = ("cannot find", "does not exist", "찾을 수 없", "없습니다")


@dataclass(frozen=True)
class WarmStatus:
    registered: bool
    detail: str = ""


def is_supported() -> bool:
    return platform.system() == "Windows"


def cli_script() -> Path:
    return Path(__file__).resolve().parents[1] / "hermes_login_warm_cli.py"


def build_task_command(runner: Path | None = None, script: Path | None = None) -> str:
    """schtasks /TR 값. 경로 공백용 따옴표는 routine_wake 와 같다."""
    run = runner or python_runner()
    src = script or cli_script()
    return f'"{run}" "{src}"'


def _run(args: list[str]) -> tuple[int, str]:
    try:
        done = subprocess.run(
            args,
            capture_output=True,
            timeout=_TIMEOUT_SEC,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return (-1, str(exc))
    text = _decode(done.stdout) + _decode(done.stderr)
    return (done.returncode, text.strip())


def _logon_user_id() -> str:
    user = os.environ.get("USERNAME", "").strip()
    domain = os.environ.get("USERDOMAIN", "").strip()
    if domain and user:
        return f"{domain}\\{user}"
    return user


def _task_xml(runner: Path, script: Path) -> str:
    """LogonTrigger + InteractiveToken.

    `/SC ONLOGON` CLI 는 관리자 권한이 필요해 일반 Iris 프로세스에서
    '액세스가 거부되었습니다' 로 실패한다. XML LogonTrigger 는 현재 사용자
    InteractiveToken 으로 같은 ONLOGON 동작을 비관리자로 등록한다.
    """
    uid = escape(_logon_user_id())
    command = escape(str(runner))
    arguments = escape(f'"{script}"')
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <Delay>PT30S</Delay>
      <UserId>{uid}</UserId>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{uid}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <Arguments>{arguments}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def query() -> WarmStatus:
    if not is_supported():
        return WarmStatus(registered=False, detail="Windows 에서만 지원합니다")
    code, text = _run(["schtasks", "/Query", "/TN", TASK_NAME])
    if code == 0:
        return WarmStatus(registered=True, detail="등록됨")
    low = text.lower()
    if any(h in low for h in _NOT_FOUND_HINTS):
        return WarmStatus(registered=False, detail="등록 안 됨")
    return WarmStatus(registered=False, detail=text[:200] or f"schtasks 종료 코드 {code}")


def register() -> WarmStatus:
    if not is_supported():
        return WarmStatus(registered=False, detail="Windows 에서만 지원합니다")
    script = cli_script()
    if not script.is_file():
        return WarmStatus(registered=False, detail=f"실행 파일을 찾을 수 없습니다: {script}")
    runner = python_runner()
    xml_path = Path(tempfile.gettempdir()) / "iris_hermes_login_warm.xml"
    try:
        xml_path.write_text(_task_xml(runner, script), encoding="utf-16")
        code, text = _run(
            ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml_path), "/F"]
        )
    except OSError as exc:
        return WarmStatus(registered=False, detail=str(exc))
    finally:
        try:
            xml_path.unlink(missing_ok=True)
        except OSError:
            pass
    if code == 0:
        return WarmStatus(registered=True, detail="로그인 시 Hermes 미리 기동")
    return WarmStatus(
        registered=False,
        detail=text[:300] or f"schtasks 종료 코드 {code}",
    )


def unregister() -> WarmStatus:
    if not is_supported():
        return WarmStatus(registered=False, detail="Windows 에서만 지원합니다")
    code, text = _run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
    if code == 0:
        return WarmStatus(registered=False, detail="해제됨")
    low = text.lower()
    if any(h in low for h in _NOT_FOUND_HINTS):
        return WarmStatus(registered=False, detail="원래 없음")
    return WarmStatus(registered=False, detail=text[:300] or f"schtasks 종료 코드 {code}")


def sync(wanted: bool) -> WarmStatus:
    current = query()
    if wanted:
        return current if current.registered else register()
    return unregister() if current.registered else WarmStatus(False, "필요 없음")


if __name__ == "__main__":
    assert TASK_NAME.startswith("\\Iris")

    cmd = build_task_command(
        Path(r"C:\py w\pythonw.exe"),
        Path(r"C:\proj\hermes_login_warm_cli.py"),
    )
    assert cmd == '"C:\\py w\\pythonw.exe" "C:\\proj\\hermes_login_warm_cli.py"'
    assert cmd.count('"') == 4

    assert cli_script().name == "hermes_login_warm_cli.py"
    runner = python_runner()
    assert runner.name in ("pythonw.exe", "python.exe", Path(sys.executable).name)

    if is_supported():
        before = query()
        assert isinstance(before.registered, bool)
        print("  현재 상태:", before.detail.encode("ascii", "replace").decode())
        # CI/일반 self-check 는 등록을 강제하지 않는다. 명시 환경에서만 왕복 검증.
        if os.environ.get("IRIS_TEST_SCHTASKS") == "1":
            on = register()
            assert on.registered, on.detail
            off = unregister()
            assert off.registered is False
            print("  schtasks register/unregister ok")
    else:
        assert register().registered is False
        assert query().registered is False

    print("hermes_login_warm self-check ok")
