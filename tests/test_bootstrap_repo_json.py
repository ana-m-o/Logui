from logui.domain.entities.bootstrap import BootstrapConfig
from logui.infrastructure.repositories.bootstrap_repo_json import JsonBootstrapRepository


def test_bootstrap_repo_roundtrip(tmp_path):
    repo = JsonBootstrapRepository(tmp_path / "bootstrap.json")

    cfg = BootstrapConfig(data_directory="~/my_data")
    repo.save(cfg)

    loaded = repo.load()
    assert loaded.data_directory == "~/my_data"


def test_bootstrap_repo_empty_defaults(tmp_path):
    repo = JsonBootstrapRepository(tmp_path / "bootstrap.json")
    loaded = repo.load()
    assert loaded == BootstrapConfig.default()


def test_bootstrap_config_serialization_omits_empty():
    cfg = BootstrapConfig(data_directory=None)
    doc = cfg.to_dict()
    assert "data_directory" not in doc

    restored = BootstrapConfig.from_dict(doc)
    assert restored.data_directory is None
