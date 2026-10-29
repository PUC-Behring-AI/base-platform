"""Tests for the Terraform modules under deploy/terraform (the managed cluster,
docs/ADAPTATION.md §10).

No AWS call is made: `terraform init -backend=false` and `terraform validate`
read only the configuration and the providers. init downloads the providers
and the EKS module from the Terraform registry, so the first run needs
network. The provider lock file is read, never rewritten (`-lockfile=readonly`),
and the working data goes to a temporary directory (TF_DATA_DIR), so the run
leaves nothing in the checkout. Skipped, saying so, when terraform is absent.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.resolve()
TERRAFORM = ROOT / "deploy" / "terraform"
MODULES = ["persistent", "cluster"]

needs_terraform = pytest.mark.skipif(
    shutil.which("terraform") is None,
    reason="terraform not installed: fmt, init and validate were not run",
)


def _terraform(args: list[str], cwd: Path, data_dir: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "TF_DATA_DIR": str(data_dir), "TF_IN_AUTOMATION": "1"}
    return subprocess.run(
        ["terraform", *args], cwd=cwd, env=env, capture_output=True, text=True, check=False
    )


@needs_terraform
def test_fmt(tmp_path: Path) -> None:
    result = _terraform(["fmt", "-check", "-recursive", "-diff"], TERRAFORM, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


@needs_terraform
@pytest.mark.parametrize("module", MODULES)
def test_init_validate_and_test(module: str, tmp_path: Path) -> None:
    cwd = TERRAFORM / module
    init = _terraform(
        ["init", "-backend=false", "-input=false", "-lockfile=readonly", "-no-color"],
        cwd,
        tmp_path,
    )
    assert init.returncode == 0, init.stdout + init.stderr
    validate = _terraform(["validate", "-no-color"], cwd, tmp_path)
    assert validate.returncode == 0, validate.stdout + validate.stderr
    # tests/*.tftest.hcl render the manifests with every provider mocked.
    if (cwd / "tests").is_dir():
        test = _terraform(["test", "-no-color"], cwd, tmp_path)
        assert test.returncode == 0, test.stdout + test.stderr


@pytest.mark.parametrize("module", MODULES)
def test_lock_file_committed(module: str) -> None:
    lock = TERRAFORM / module / ".terraform.lock.hcl"
    assert lock.is_file(), f"{lock.relative_to(ROOT)} missing: providers would float"
    # One h1: hash per platform: CI runs linux_amd64, a Mac darwin_arm64. A
    # lock made by `init` alone holds only the platform it ran on.
    blocks = re.split(r"^provider ", lock.read_text(), flags=re.M)[1:]
    thin = [b.split("{", 1)[0].strip() for b in blocks if b.count("h1:") < 4]
    assert not thin, (
        f"{lock.relative_to(ROOT)}: too few platform hashes for {thin}; run terraform "
        "providers lock -platform=linux_amd64 -platform=linux_arm64 "
        "-platform=darwin_arm64 -platform=darwin_amd64"
    )


def _tf_files() -> list[Path]:
    return sorted(p for p in TERRAFORM.rglob("*.tf") if ".terraform" not in p.parts)


def test_no_account_id() -> None:
    hits = [
        f"{p.relative_to(ROOT)}:{n}: {line.strip()}"
        for p in _tf_files()
        for n, line in enumerate(p.read_text().splitlines(), 1)
        if re.search(r"(?<![0-9])[0-9]{12}(?![0-9])", line)
    ]
    assert not hits, "an account id in base Terraform:\n" + "\n".join(hits)


def test_region_only_in_variable_defaults() -> None:
    # A region name (us-east-1) or zone id (use1-az3) may only be a variable's
    # default; anywhere else it pins every instance to one place.
    region = re.compile(r"\b[a-z]{2}(-gov)?-[a-z]+-[0-9]\b|\b[a-z]{2,4}[0-9]-az[0-9]\b")
    hits = []
    for p in _tf_files():
        if p.name == "variables.tf":
            continue
        for n, line in enumerate(p.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            if region.search(code):
                hits.append(f"{p.relative_to(ROOT)}:{n}: {line.strip()}")
    assert not hits, "a region literal outside variables.tf:\n" + "\n".join(hits)


def test_names_no_instance() -> None:
    # The same list scripts/leak-check.sh reads; the gate runs that over the
    # whole repository too. Without the list, nothing can be checked.
    raw = os.environ.get("BASE_DENYLIST", "")
    if not raw and os.environ.get("BASE_DENYLIST_FILE"):
        raw = Path(os.environ["BASE_DENYLIST_FILE"]).read_text()
    terms = [t.strip().lower() for t in raw.splitlines() if t.strip()]
    if not terms:
        pytest.skip("neither BASE_DENYLIST nor BASE_DENYLIST_FILE set: instance names not checked")
    files = [*_tf_files(), *TERRAFORM.rglob("*.sh"), TERRAFORM / "README.md"]
    # Whole words, ignoring case, as leak-check.sh greps (-iwF).
    hits = [
        f"{p.relative_to(ROOT)}: {term}"
        for p in files
        for term in terms
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", p.read_text().lower())
    ]
    assert not hits, "base Terraform names an instance:\n" + "\n".join(hits)
