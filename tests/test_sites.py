from worker.sites import parse_vote_url


def test_parse_valid_minecraft_server_url():
    url = "https://minecraft-server.eu/vote/index/208F7/"
    result = parse_vote_url(url)
    assert result is not None
    assert result["siteKey"] == "minecraft-server.eu"
    assert result["projectId"] == "208F7"
    assert result["normalizedUrl"].startswith("https://minecraft-server.eu")


def test_parse_unknown_url_returns_none():
    assert parse_vote_url("https://example.com/not-supported") is None


def test_parse_missing_project_id_returns_none():
    assert parse_vote_url("https://minecraft-server.eu/vote/index/") is None
