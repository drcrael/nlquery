"""Checksum and isolated wheel/sdist verification outside the source checkout."""

import hashlib
import os
import subprocess
import sys
import tarfile
import tempfile
import venv
from pathlib import Path

assets = Path(sys.argv[1]).resolve()
for line in (assets / "SHA256SUMS").read_text().splitlines():
    digest, name = line.split(maxsplit=1)
    assert hashlib.sha256((assets / name.strip()).read_bytes()).hexdigest() == digest
wheel = next(assets.glob("*.whl"))
sdist = next(assets.glob("*.tar.gz"))
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    with tarfile.open(sdist) as archive:
        archive.extractall(root / "source", filter="data")
    source = next((root / "source").iterdir())
    for name, artifact in [("wheel", wheel), ("sdist", sdist)]:
        env = root / name
        venv.EnvBuilder(with_pip=True).create(env)
        python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        extras = "[dev,postgres,neo4j,mongo,redis,mysql,openai,anthropic,yaml]"
        subprocess.run(
            [str(python), "-m", "pip", "install", str(artifact) + extras], check=True, cwd=root
        )
        subprocess.run([str(python), "-m", "pip", "check"], check=True, cwd=root)
        subprocess.run(
            [str(python), "-m", "pytest", str(source / "tests"), "-q"], check=True, cwd=root
        )
        subprocess.run(
            [str(python), str(source / "examples/ecommerce.py")],
            check=True,
            cwd=root,
            stdout=subprocess.DEVNULL,
        )
