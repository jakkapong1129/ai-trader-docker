import os
import subprocess
import sys


def test_max_consecutive_losses_defaults_to_max_mg_level():
    env = os.environ.copy()
    env["MAX_MG_LEVEL"] = "5"
    env.pop("MAX_CONSECUTIVE_LOSSES", None)

    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import auto_loop; print(auto_loop.MAX_CONSECUTIVE_LOSSES)",
        ],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        text=True,
    )

    assert output.strip() == "5"


def test_max_consecutive_losses_can_be_overridden_by_env():
    env = os.environ.copy()
    env["MAX_MG_LEVEL"] = "5"
    env["MAX_CONSECUTIVE_LOSSES"] = "4"

    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import auto_loop; print(auto_loop.MAX_CONSECUTIVE_LOSSES)",
        ],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        text=True,
    )

    assert output.strip() == "4"
