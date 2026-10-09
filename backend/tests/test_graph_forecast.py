import numpy as np
import pytest
import torch
from atlas import config
from atlas.graph_forecast import GraphForecaster
from atlas.graph_runtime import predict_graph


def test_graph_messages_follow_directed_edges_and_gradients_reach_neighbors():
    weights = torch.tensor([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [0.0, 0.0, 0.0]]).to_sparse()
    x = torch.tensor([[[10.0], [20.0], [30.0]]], requires_grad=True)
    aggregated = GraphForecaster.aggregate(weights, x)
    assert aggregated.detach().flatten().tolist() == [20.0, 30.0, 0.0]
    aggregated[0, 0].sum().backward()
    assert x.grad.flatten().tolist() == [0.0, 1.0, 0.0]


def test_temporal_baseline_is_local_while_graph_model_propagates_neighbors():
    adjacency = np.array([[0.0, 1.0], [0.0, 0.0]])
    x = torch.ones((1, 2, 14))
    changed = x.clone()
    changed[:, 1] *= 2
    for graph in (False, True):
        model = GraphForecaster(adjacency, graph=graph)
        for p in model.parameters():
            torch.nn.init.constant_(p, 0.1)
        first, second = model(x), model(changed)
        if graph:
            assert first[0, 0] != second[0, 0]
        else:
            assert first[0, 0] == second[0, 0]


def test_native_graph_refuses_missing_checkpoints_before_untrusted_loading(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA", tmp_path)
    with pytest.raises(ValueError, match="unavailable"):
        predict_graph(np.ones((207, 6)) * 50, "2012-06-04T12:00", 5)
    with pytest.raises(ValueError, match="Unsupported"):
        predict_graph(np.ones((207, 6)) * 50, "2012-06-04T12:00", 7)
