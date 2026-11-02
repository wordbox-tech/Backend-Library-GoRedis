# Read-only overlap adapter for the reviewed WordContext hook configuration.
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

CONFIG_SHA256 = "f93af19d5906d939e0dc7c54ed1233e3f8bc70dfa0e1812856f45758f1b4ff12"
HOOK_COMMITS = {
    "https://github.com/pre-commit/pre-commit-hooks": (
        "v4.6.0", "2c9f875913ee60ca25ce70243dc24d5b6415598c",
    ),
    "https://github.com/golangci/golangci-lint": (
        "v1.60.3", "c2e095c022a97360f7fff5d49fbc11f273be929a",
    ),
}


def output(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def configuration(path: Path) -> dict:
    from pre_commit.clientlib import load_config

    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Local candidate requires explicit Python 3.12")
    if hashlib.sha256(path.read_bytes()).hexdigest() != CONFIG_SHA256:
        raise RuntimeError("Hook configuration changed; source review is required")
    return load_config(str(path))


def verify_isolation() -> None:
    """Prove the Linux hook namespace is offline and has no credential inputs."""
    for name in (
        "GITHUB_TOKEN",
        "ACTIONS_RUNTIME_TOKEN",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "SSH_AUTH_SOCK",
    ):
        if name in os.environ:
            raise RuntimeError("Credential environment input is forbidden")
    if sys.platform == "linux":
        import errno
        import socket

        if os.geteuid() == 0:
            raise RuntimeError("Hook container must be non-root")
        interfaces = sorted(p.name for p in Path("/sys/class/net").iterdir())
        if interfaces != ["lo"] or Path("/var/run/docker.sock").exists():
            raise RuntimeError("Unexpected network interface or Docker socket")
        for name in (".config/gh", ".config/gcloud", ".ssh"):
            if (Path.home() / name).exists():
                raise RuntimeError("Unexpected credential/session directory")
        with socket.socket() as probe:
            try:
                probe.connect(("192.0.2.1", 443))
            except OSError as error:
                if error.errno not in {errno.ENETUNREACH, errno.EHOSTUNREACH}:
                    raise RuntimeError(
                        "Network isolation probe was inconclusive"
                    ) from error
            else:
                raise RuntimeError("Network unexpectedly reachable")
        print(
            "Isolation proved: non-root, loopback only, no route, no credential inputs or Docker socket",
            flush=True,
        )


def verify_sources() -> None:
    from pre_commit.store import Store

    for repo, (rev, expected) in HOOK_COMMITS.items():
        cached = Store().clone(repo, rev)
        observed = output("git", "-C", cached, "rev-parse", "HEAD")
        if observed != expected:
            raise RuntimeError(f"Hook ref moved: {repo}@{rev}: {observed}")
        print(f"Verified {repo}@{rev} = {observed}", flush=True)


def prepare(config_path: Path) -> None:
    """Network-enabled source retrieval; no hook or build backend executes."""
    configuration(config_path)
    subprocess.run(["git", "init", "--quiet"], check=True)
    shutil.copyfile(config_path, ".pre-commit-config.yaml")
    verify_sources()


def verify_skipped_go() -> None:
    """Reject an installed environment for the intentionally skipped Go hook."""
    from pre_commit.languages.golang import ENVIRONMENT_DIR
    from pre_commit.store import Store

    repo = "https://github.com/golangci/golangci-lint"
    rev, _ = HOOK_COMMITS[repo]
    source = Path(Store().clone(repo, rev))
    if list(source.glob(f"{ENVIRONMENT_DIR}-*")):
        raise RuntimeError("Skipped Go environment unexpectedly exists")


def install(config_path: Path, wheels: Path) -> None:
    """Install only active hook environments; retain genuine skipped manifests."""
    from locked_dependencies import lock_data, verify
    from pre_commit.repository import all_hooks, install_hook_envs
    from pre_commit.store import Store

    config = configuration(config_path)
    verify_isolation()
    verify(wheels)
    verify_sources()
    skip = config.get("ci", {}).get("skip", [])
    if skip != ["golangci-lint"]:
        raise RuntimeError("Unexpected CI skip; review required")
    hooks = [h for h in all_hooks(config, Store()) if "pre-commit" in h.stages]
    if [h.id for h in hooks] != [
        "check-hooks-apply", "check-useless-excludes", "identity",
        "check-added-large-files", "end-of-file-fixer", "mixed-line-ending",
        "no-commit-to-branch", "trailing-whitespace", "golangci-lint",
    ]:
        raise RuntimeError("Hook manifest changed; review required")
    active = [h for h in hooks if h.id not in skip and h.alias not in skip]
    verify_skipped_go()
    install_hook_envs(active, Store())
    verify_skipped_go()
    hygiene = Path(Store().clone("https://github.com/pre-commit/pre-commit-hooks", "v4.6.0"))
    env_python = hygiene / "py_env-python3.12/bin/python"
    subprocess.run([str(env_python), "-m", "pip", "check"], check=True)
    expected = {
        p["name"].lower().replace("_", "-").replace(".", "-"): p["version"]
        for p in lock_data()["packages"]
    }
    expected["pre-commit-hooks"] = "4.6.0"
    packages = json.loads(output(str(env_python), "-m", "pip", "list", "--format=json"))
    for package in packages:
        name = package["name"].lower().replace("_", "-").replace(".", "-")
        if package["version"] != expected.get(name):
            raise RuntimeError(f"Unreviewed installed dependency: {name}")
    print(json.dumps({"activeHooks": [h.id for h in active], "skipped": skip,
                      "hygienePackages": packages}, sort_keys=True), flush=True)


def run(config_path: Path) -> int:
    """Run against the merge checkout, offline and without credentials."""
    from pre_commit import git
    from pre_commit.clientlib import load_config
    from pre_commit.commands.run import Classifier
    from pre_commit.repository import all_hooks
    from pre_commit.store import Store

    config = configuration(config_path)
    verify_isolation()
    skip = config.get("ci", {}).get("skip", [])
    if skip != ["golangci-lint"]:
        raise RuntimeError("Unexpected CI skip; review required")
    verify_skipped_go()
    os.environ["SKIP"] = ",".join(skip)
    loaded = load_config(str(config_path))
    filenames = sorted(git.get_all_files())
    classifier = Classifier.from_config(filenames, loaded["files"], loaded["exclude"])
    hooks = all_hooks(loaded, Store())
    selection = {
        hook.id: {
            "selectedFiles": list(classifier.filenames_for_hook(hook)),
            "passFilenames": hook.pass_filenames,
            "alwaysRun": hook.always_run,
            "args": hook.args,
            "entry": hook.entry,
            "stages": hook.stages,
        }
        for hook in hooks
    }
    print(
        json.dumps(
            {
                "commit": output("git", "rev-parse", "HEAD"),
                "parents": output("git", "show", "-s", "--format=%P", "HEAD"),
                "symbolicRef": subprocess.run(
                    ["git", "symbolic-ref", "-q", "HEAD"],
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                "python": sys.version,
                "preCommit": output("pre-commit", "--version"),
                "configSha256": CONFIG_SHA256,
                "ciSkip": skip,
                "trackedFiles": filenames,
                "hookFiles": selection,
                "stage": "pre-commit",
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )
    result = subprocess.call(
        [
            "pre-commit",
            "run",
            "--all-files",
            "--hook-stage",
            "pre-commit",
            "--color=never",
        ]
    )
    verify_skipped_go()
    return result


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare(Path(sys.argv[2]).resolve())
    elif sys.argv[1] == "install":
        install(Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve())
    elif sys.argv[1] == "run":
        raise SystemExit(run(Path(".pre-commit-config.yaml")))
    else:
        raise SystemExit("Expected prepare, install or run")
