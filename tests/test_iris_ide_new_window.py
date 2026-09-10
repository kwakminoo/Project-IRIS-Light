"""IRIS IDE "새 창"(welcome) 상태 회귀 방지.

예전엔 project_root_path가 없을 때도 project_root()(IRIS-Light 저장소 자체)를
Theia CLI의 워크스페이스 인자로 그대로 넘겨, Theia 입장에서는 항상 폴더가 열려
있는 것으로 보였다. 그 결과 workspaceService.opened가 always-true가 되어
IrisIdeStartWidget("새 창" 시작 화면)이 절대 뜨지 않았다.

이 테스트는 실제 Theia 프로세스를 띄우지 않고 subprocess.Popen을 가로채,
project_root_path가 비어 있을 때 theia_args에 워크스페이스 경로가 포함되지
않는지(= 새 창 상태로 진짜 열리는지) 검증한다.
"""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import MagicMock, patch

from iris.system.hermes_iris_control_sync import project_root
from iris.system.iris_ide_runtime import IrisIdeRuntimeManager

_REAL_POPEN = subprocess.Popen


def _installed() -> bool:
    return IrisIdeRuntimeManager().is_installed()


@unittest.skipUnless(_installed(), "IRIS IDE runtime not installed on this machine")
class IrisIdeNewWindowTests(unittest.TestCase):
    def _start_and_capture_args(self, project_root_path: str) -> list[str]:
        mgr = IrisIdeRuntimeManager()
        fake_proc = MagicMock()
        fake_proc.pid = 4242
        captured: list[list[str]] = []

        def _fake_popen(args, **kwargs):
            joined = " ".join(str(a) for a in args)
            if "theia.js" in joined or "standalone-bridge.js" in joined:
                captured.append(list(args))
                return fake_proc
            # node --version 등 다른 subprocess 호출(is_node_ready 등)은 실제로 흘려보낸다.
            return _REAL_POPEN(args, **kwargs)

        with patch("iris.system.iris_ide_runtime.subprocess.Popen", side_effect=_fake_popen), \
             patch("iris.system.iris_ide_runtime._free_port", side_effect=[59001, 59002]), \
             patch.object(IrisIdeRuntimeManager, "_write_state", return_value=None), \
             patch.object(IrisIdeRuntimeManager, "wait_until_ready", return_value=(True, "ready")):
            ok, msg = mgr.start(project_root_path)
        self.assertTrue(ok, msg)
        # captured[0] is the bridge process, captured[1] is the theia CLI process
        self.assertEqual(len(captured), 2)
        return captured[1]

    def test_no_project_root_omits_workspace_arg(self) -> None:
        """project_root_path 없이 시작 → Theia에 워크스페이스 경로를 넘기지 않는다.

        (예전 버그: project_root()=IRIS-Light 저장소 자체가 항상 마지막 인자로
        붙어서 Theia가 절대 "워크스페이스 없음" 상태가 되지 않았다.)
        """
        theia_args = self._start_and_capture_args("")
        fallback_repo_root = str(project_root().resolve())
        self.assertNotIn(fallback_repo_root, theia_args)
        # explicit_workspace=False면 마지막 인자는 항상 --플래그여야 한다(경로가 안 붙음).
        self.assertTrue(
            theia_args[-1].startswith("-"),
            f"expected last theia arg to be a flag, got trailing path: {theia_args!r}",
        )

    def test_explicit_project_root_passes_workspace_arg(self) -> None:
        """project_root_path가 실제 폴더면 여전히 워크스페이스로 넘긴다(기존 동작 보존)."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            theia_args = self._start_and_capture_args(tmp)
            self.assertIn(str(Path(tmp).resolve()), theia_args)
            self.assertFalse(theia_args[-1].startswith("-"))


if __name__ == "__main__":
    unittest.main()
