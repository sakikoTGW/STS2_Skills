"""Tests for plugins.sts2.doctor."""

from __future__ import annotations

from plugins.sts2.doctor import (
    _check,
    _mod_installed,
    _tcp_reachable,
    format_doctor_report,
    format_status_report,
    run_doctor,
)


def test_check_shape():
    row = _check("label", True, "detail", hint="hint text")
    assert row["check"] == "label"
    assert row["ok"] is True
    assert row["detail"] == "detail"
    assert row["hint"] == "hint text"


def test_mod_installed_no_game():
    ok, detail = _mod_installed(None)
    assert ok is False
    assert "未检测" in detail


def test_tcp_unreachable_bad_port():
    ok, _ = _tcp_reachable("http://127.0.0.1:1", timeout=0.2)
    assert ok is False


def test_run_doctor_returns_structure():
    report = run_doctor()
    assert "checks" in report
    assert "runtime_host" in report
    assert "next_steps" in report
    assert any(c["check"] == "STS2_Skills 版本" for c in report["checks"])


def test_format_doctor_report_includes_version_line():
    report = run_doctor()
    text = format_doctor_report(report)
    assert "STS2 doctor" in text
    assert "建议下一步" in text


def test_format_status_report_header():
    text = format_status_report(include_doctor=False)
    assert "sts2-skills" in text
    assert "runtime_host:" in text
    assert "STS2 doctor" not in text
