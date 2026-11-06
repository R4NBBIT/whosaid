import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """테스트마다 빈 데이터 폴더를 씁니다. 실제 사용자 데이터에 손대지 않습니다."""
    home = tmp_path / "whosaid-home"
    monkeypatch.setenv("WHOSAID_HOME", str(home))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return home
