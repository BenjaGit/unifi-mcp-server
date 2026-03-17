"""Unit tests for integration runner environment loading."""

from tests.integration import run_all_tests


def _clear_runner_env(monkeypatch) -> None:
    """Clear env vars consulted by integration environment loader."""
    for key in [
        "UNIFI_LAB_API_KEY",
        "UNIFI_HOME_API_KEY",
        "UNIFI_LOCAL_API_KEY",
        "UNIFI_REMOTE_API_KEY",
        "UNIFI_NETWORK_API_KEY",
        "UNIFI_LOCAL_HOST",
        "UNIFI_LAB_HOST",
        "UNIFI_CLOUD_V1_API_KEY",
        "UNIFI_CLOUD_EA_API_KEY",
        "UNIFI_SITE_MANAGER_API_KEY",
        "UNIFI_CLOUD_SITE_LAB",
        "UNIFI_CLOUD_SITE_HOME",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_load_test_environments_uses_network_api_key_for_local(monkeypatch) -> None:
    """UNIFI_NETWORK_API_KEY should be enough to create unifi-lab env."""
    _clear_runner_env(monkeypatch)
    monkeypatch.setattr(run_all_tests, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "network-token")
    monkeypatch.setenv("UNIFI_LOCAL_HOST", "192.0.2.1")

    environments = run_all_tests.load_test_environments()
    by_name = {env.name: env for env in environments}

    assert "unifi-lab" in by_name
    assert by_name["unifi-lab"].api_key == "network-token"
    assert by_name["unifi-lab"].local_host == "192.0.2.1"


def test_load_test_environments_uses_local_api_key_alias_for_local(monkeypatch) -> None:
    """UNIFI_LOCAL_API_KEY should be sufficient to create unifi-lab env."""
    _clear_runner_env(monkeypatch)
    monkeypatch.setattr(run_all_tests, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("UNIFI_LOCAL_API_KEY", "local-token")
    monkeypatch.setenv("UNIFI_LOCAL_HOST", "192.0.2.2")

    environments = run_all_tests.load_test_environments()
    by_name = {env.name: env for env in environments}

    assert "unifi-lab" in by_name
    assert by_name["unifi-lab"].api_key == "local-token"
    assert by_name["unifi-lab"].local_host == "192.0.2.2"


def test_load_test_environments_uses_remote_key_for_cloud(monkeypatch) -> None:
    """UNIFI_SITE_MANAGER_API_KEY should create cloud envs when cloud-specific keys are unset."""
    _clear_runner_env(monkeypatch)
    monkeypatch.setattr(run_all_tests, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("UNIFI_SITE_MANAGER_API_KEY", "remote-token")

    environments = run_all_tests.load_test_environments()
    by_name = {env.name: env for env in environments}

    assert "unifi-cloud-v1-lab" in by_name
    assert by_name["unifi-cloud-v1-lab"].api_key == "remote-token"
    assert by_name["unifi-cloud-v1-lab"].api_type == "cloud-v1"


def test_load_test_environments_uses_remote_api_key_alias_for_cloud(monkeypatch) -> None:
    """UNIFI_REMOTE_API_KEY should create cloud envs when explicit cloud keys are unset."""
    _clear_runner_env(monkeypatch)
    monkeypatch.setattr(run_all_tests, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("UNIFI_REMOTE_API_KEY", "remote-alias-token")

    environments = run_all_tests.load_test_environments()
    by_name = {env.name: env for env in environments}

    assert "unifi-cloud-v1-lab" in by_name
    assert by_name["unifi-cloud-v1-lab"].api_key == "remote-alias-token"


def test_cloud_v1_api_key_takes_precedence_over_network_key(monkeypatch) -> None:
    """Explicit cloud-v1 key should override generic network key for cloud-v1 envs."""
    _clear_runner_env(monkeypatch)
    monkeypatch.setattr(run_all_tests, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("UNIFI_CLOUD_V1_API_KEY", "cloud-v1-token")
    monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "network-token")

    environments = run_all_tests.load_test_environments()
    by_name = {env.name: env for env in environments}

    assert "unifi-cloud-v1-lab" in by_name
    assert by_name["unifi-cloud-v1-lab"].api_key == "cloud-v1-token"


def test_remote_key_takes_precedence_over_network_for_cloud(monkeypatch) -> None:
    """When no cloud override is set, remote key should win over local key for cloud tests."""
    _clear_runner_env(monkeypatch)
    monkeypatch.setattr(run_all_tests, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("UNIFI_SITE_MANAGER_API_KEY", "remote-token")
    monkeypatch.setenv("UNIFI_NETWORK_API_KEY", "network-token")

    environments = run_all_tests.load_test_environments()
    by_name = {env.name: env for env in environments}

    assert "unifi-cloud-v1-lab" in by_name
    assert by_name["unifi-cloud-v1-lab"].api_key == "remote-token"
