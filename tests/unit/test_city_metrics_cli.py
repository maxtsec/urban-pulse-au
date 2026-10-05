"""City operational reads need only the queue and never emit partial/secret failures."""

import json
from unittest.mock import Mock

import pytest

from urbanpulse.application.city_checkpoints import CONSUMER, RESULT_CONSUMER
from urbanpulse.application.durable_delivery import StorageUnavailable
from workers.city import main as cli


@pytest.mark.parametrize("failed_consumer", [None, CONSUMER, RESULT_CONSUMER])
def test_metrics_reads_both_registered_consumers_without_city_reconstruction(
    monkeypatch, capsys, failed_consumer
):
    engine = Mock()
    queue = Mock()

    def metrics(consumer):
        if consumer == failed_consumer:
            raise StorageUnavailable("private database credential must not escape")
        return {"consumer": consumer, "backlog_count": 0}

    queue.metrics.side_effect = metrics
    monkeypatch.setattr(cli, "engine_for", lambda url: engine)
    monkeypatch.setattr(cli, "PostgresRecoveryStore", lambda value: queue)
    monkeypatch.setattr(
        cli, "CityInputStore", lambda *args: pytest.fail("must not load city inputs")
    )
    monkeypatch.setattr(
        cli, "PostgisMembership", lambda *args: pytest.fail("must not query geometry")
    )
    monkeypatch.setattr("sys.argv", ["city", "metrics"])
    code = cli.main()
    result = json.loads(capsys.readouterr().out)
    engine.dispose.assert_called_once()
    if failed_consumer:
        assert code == 2
        assert result == {"error": "database-unavailable-or-schema-invalid"}
    else:
        assert code == 0
        assert [item["consumer"] for item in result["consumers"]] == [CONSUMER, RESULT_CONSUMER]
