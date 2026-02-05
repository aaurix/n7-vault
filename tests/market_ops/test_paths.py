from market_ops.utils.paths import repo_root


def test_repo_root_contains_readme():
    root = repo_root()
    assert (root / "README.md").exists()
