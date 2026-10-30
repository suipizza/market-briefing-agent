from briefing import demo


def test_demo_runs_offline(capsys):
    demo.run()
    out = capsys.readouterr().out
    assert "불일치" not in out
    assert "6/6 통과" in out
    assert "반려: derivatives" in out and "contradicts tag flow=유입" in out
    assert "차단됨" in out
