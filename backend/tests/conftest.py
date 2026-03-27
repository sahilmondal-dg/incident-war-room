import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--slow",
        action="store_true",
        default=False,
        help="Run slow tests that make real Vertex AI calls",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--slow"):
        skip_slow = pytest.mark.skip(reason="Use --slow to run")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)
