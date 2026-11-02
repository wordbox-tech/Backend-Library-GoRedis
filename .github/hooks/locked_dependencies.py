# Retrieve verified wheel inputs; installation happens separately, offline.
from __future__ import annotations

import hashlib
import json
import platform
import sys
import urllib.request
from pathlib import Path

LOCK_SHA256 = "0f1ace71e5b88dcf63f673f4db7f9781a27b75064c2de627f1b2eb9003585ec0"
LOCK = Path(__file__).with_name("dependencies.lock.json")


def lock_data() -> dict:
    if hashlib.sha256(LOCK.read_bytes()).hexdigest() != LOCK_SHA256:
        raise RuntimeError("Dependency lock digest mismatch; review required")
    data = json.loads(LOCK.read_text(encoding="utf-8"))
    if data["format"] != 1 or sys.version_info[:2] != (3, 12):
        raise RuntimeError("Unsupported dependency lock/interpreter")
    return data


def target() -> str:
    value = f"{sys.platform}-{platform.machine().lower()}"
    if value not in {"linux-x86_64", "darwin-arm64"}:
        raise RuntimeError("Unsupported wheel platform")
    return value


def derived_files(data: dict) -> dict:
    chosen = target()
    bootstrap = "".join(
        f'{p["name"]}=={p["version"]} --hash=sha256:{p["wheels"][chosen]["sha256"]}\n'
        for p in data["packages"]
        if p["name"] in data["bootstrap"]
    )
    constraints = "".join(f'{p["name"]}=={p["version"]}\n' for p in data["packages"])
    return {"bootstrap.txt": bootstrap, "constraints.txt": constraints}


def verify(directory: Path) -> None:
    data = lock_data()
    expected = set(derived_files(data))
    for package in data["packages"]:
        wheel = package["wheels"][target()]
        name = wheel["filename"]
        if Path(name).name != name or not name.endswith(".whl"):
            raise RuntimeError("Invalid wheel filename")
        content = (directory / name).read_bytes()
        if (
            len(content) != wheel["bytes"]
            or hashlib.sha256(content).hexdigest() != wheel["sha256"]
        ):
            raise RuntimeError(f"Wheel hash/size mismatch: {name}")
        expected.add(name)
    for name, content in derived_files(data).items():
        if (directory / name).read_text(encoding="utf-8") != content:
            raise RuntimeError(f"Derived dependency input mismatch: {name}")
    if {p.name for p in directory.iterdir()} != expected:
        raise RuntimeError("Unexpected wheelhouse input")
    print(
        f"Verified {len(data['packages'])} locked wheels; lock {LOCK_SHA256}",
        flush=True,
    )


def download(directory: Path) -> None:
    data = lock_data()
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise RuntimeError("Cold retrieval requires an empty wheel directory")
    for package in data["packages"]:
        wheel = package["wheels"][target()]
        if not wheel["url"].startswith("https://files.pythonhosted.org/"):
            raise RuntimeError("Unexpected wheel host")
        with urllib.request.urlopen(wheel["url"], timeout=60) as response:
            if not response.geturl().startswith("https://files.pythonhosted.org/"):
                raise RuntimeError("Unexpected wheel redirect")
            content = response.read(wheel["bytes"] + 1)
        if (
            len(content) != wheel["bytes"]
            or hashlib.sha256(content).hexdigest() != wheel["sha256"]
        ):
            raise RuntimeError(f"Downloaded wheel hash mismatch: {wheel['filename']}")
        (directory / wheel["filename"]).write_bytes(content)
        print(
            f"Retrieved {package['name']}=={package['version']} sha256={wheel['sha256']}",
            flush=True,
        )
    for name, content in derived_files(data).items():
        (directory / name).write_text(content, encoding="utf-8")
    verify(directory)


if __name__ == "__main__":
    if sys.argv[1] == "download":
        download(Path(sys.argv[2]))
    elif sys.argv[1] == "verify":
        verify(Path(sys.argv[2]))
    else:
        raise SystemExit("Expected download or verify")
