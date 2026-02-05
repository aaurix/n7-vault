import os
import subprocess


def test_cli_help():
    env = dict(os.environ)
    r = subprocess.run(["python3", "-m", "scripts.market_ops", "--help"], capture_output=True, text=True, env=env)
    assert r.returncode == 0
    assert "symbol" in r.stdout
