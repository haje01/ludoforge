"""S0 셋업 검증용 스모크 테스트: 패키지 임포트와 핵심 의존성이 살아있는지 확인."""

from __future__ import annotations


def test_package_imports() -> None:
    import ludoforge

    assert ludoforge.__version__


def test_cli_app_exists() -> None:
    from ludoforge.cli import app

    assert app is not None


def test_z3_available() -> None:
    import z3

    s = z3.Solver()
    x = z3.Int("x")
    s.add(x > 0, x < 0)
    assert s.check() == z3.unsat
