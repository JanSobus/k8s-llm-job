from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_kind_minio_service_matches_cluster_port_mapping() -> None:
    manifest = (ROOT / "deploy" / "app" / "minio.yaml").read_text(encoding="utf-8")

    assert "type: NodePort" in manifest
    assert "nodePort: 30900" in manifest
    assert "nodePort: 30901" in manifest


def test_docker_runtime_commands_keep_installed_extras() -> None:
    expected = {
        "backend/Dockerfile": '"--extra", "backend"',
        "workers/pdf/Dockerfile": '"--extra", "worker-pdf"',
        "workers/tabular/Dockerfile": '"--extra", "worker-tabular"',
    }

    for relative_path, snippet in expected.items():
        dockerfile = (ROOT / relative_path).read_text(encoding="utf-8")
        assert snippet in dockerfile
