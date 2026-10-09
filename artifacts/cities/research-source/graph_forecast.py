"""Small learned directional message-passing model for highway sensor speeds."""

import torch
from torch import nn

from atlas.forecast_v3 import graph_weights


class GraphForecaster(nn.Module):
    def __init__(self, adjacency, inputs=14, hidden=32, graph=True):
        super().__init__()
        self.graph = graph
        self.register_buffer("outgoing", torch.tensor(graph_weights(adjacency)).to_sparse())
        self.register_buffer("incoming", torch.tensor(graph_weights(adjacency.T)).to_sparse())
        self.encoder = nn.Linear(inputs, hidden)
        self.local = nn.Linear(hidden, hidden)
        self.out_message = nn.Linear(hidden, hidden, bias=False) if graph else None
        self.in_message = nn.Linear(hidden, hidden, bias=False) if graph else None
        self.output = nn.Linear(hidden, 1)

    @staticmethod
    def aggregate(weights, hidden):
        batch, sensors, channels = hidden.shape
        packed = hidden.permute(1, 0, 2).reshape(sensors, batch * channels)
        return torch.sparse.mm(weights, packed).reshape(sensors, batch, channels).permute(1, 0, 2)

    def forward(self, x):
        encoded = torch.relu(self.encoder(x))
        hidden = self.local(encoded)
        if self.graph:
            hidden = hidden + self.out_message(self.aggregate(self.outgoing, encoded))
            hidden = hidden + self.in_message(self.aggregate(self.incoming, encoded))
        return self.output(torch.relu(hidden)).squeeze(-1)
