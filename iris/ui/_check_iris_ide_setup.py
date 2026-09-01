"""Setup protocol IRIS IDE optional checks."""

from __future__ import annotations

import os

from iris.system.setup_protocol import OPTIONAL_IDS, SetupProtocol, load_setup_state


def main() -> None:
    assert "iris_ide" in OPTIONAL_IDS
    os.environ["IRIS_SETUP_DEMO"] = "1"
    try:
        proto = SetupProtocol(simulate=True, dry_run=False)

        def _user(_result) -> str:
            return "skip"

        ok = proto.run_optional("iris_ide", on_user=_user)
        assert ok
        st = load_setup_state(simulate=True)
        assert st["optional"]["iris_ide"]["status"] == "skipped"

        direct = proto.install_optional_step("iris_ide")
        assert direct.status == "done"
        assert "[데모]" in direct.message
    finally:
        os.environ.pop("IRIS_SETUP_DEMO", None)
    print("iris_ide_setup check ok")


if __name__ == "__main__":
    main()
