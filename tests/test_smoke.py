"""Sanity check that the package layout imports."""


def test_packages_import():
    import assistant  # noqa: F401
    import credit  # noqa: F401
    import evals  # noqa: F401
    import guardrails  # noqa: F401
    import storage  # noqa: F401
