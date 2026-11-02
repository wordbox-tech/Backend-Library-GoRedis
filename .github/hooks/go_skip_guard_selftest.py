"""Exercise the actual skipped-Go guard in the existing offline job."""
import os
from pathlib import Path

from pre_commit.languages.golang import ENVIRONMENT_DIR
from pre_commit.store import Store

import repository_hooks


def main() -> None:
    repository_hooks.verify_isolation()
    repository_hooks.verify_skipped_go()
    source = Path(Store().clone(
        "https://github.com/golangci/golangci-lint", "v1.60.3"
    ))
    marker = source / f"{ENVIRONMENT_DIR}-synthetic-assertion"
    if marker.exists():
        raise RuntimeError("Synthetic assertion marker already exists")
    marker.mkdir()
    try:
        repository_hooks.verify_skipped_go()
    except RuntimeError as error:
        if str(error) != "Skipped Go environment unexpectedly exists":
            raise
    else:
        raise RuntimeError("Skipped-Go guard accepted the synthetic environment")
    evidence = Path(os.environ["PRE_COMMIT_HOME"]).parent / "skipped-go-guard-fixture"
    evidence.mkdir()
    marker.rename(evidence / "injected-marker")
    repository_hooks.verify_skipped_go()
    print("Skipped-Go guard: clean=pass injected=reject restored=pass", flush=True)


if __name__ == "__main__":
    main()
