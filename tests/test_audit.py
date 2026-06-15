from slide_examiner.audit import run_code_audit
from slide_examiner.cli import main


def test_code_audit_passes() -> None:
    result = run_code_audit()
    assert result["passed"] is True


def test_audit_cli() -> None:
    assert main(["audit"]) == 0

