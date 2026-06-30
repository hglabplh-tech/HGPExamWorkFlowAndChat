"""Train a small character LSTM for experimentation, not factual RAG answers."""
import argparse
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset


class TextWindows(Dataset):
    def __init__(self, encoded: list[int], sequence_length: int):
        self.data, self.sequence_length = encoded, sequence_length

    def __len__(self) -> int:
        return max(0, len(self.data) - self.sequence_length)

    def __getitem__(self, index: int):
        x = torch.tensor(self.data[index:index + self.sequence_length], dtype=torch.long)
        y = torch.tensor(self.data[index + 1:index + self.sequence_length + 1], dtype=torch.long)
        return x, y


class CharLSTM(nn.Module):
    def __init__(self, vocabulary_size: int, embedding_size: int = 128, hidden_size: int = 256):
        super().__init__()
        self.embedding = nn.Embedding(vocabulary_size, embedding_size)
        self.lstm = nn.LSTM(embedding_size, hidden_size, batch_first=True, num_layers=2, dropout=0.2)
        self.output = nn.Linear(hidden_size, vocabulary_size)

    def forward(self, tokens: torch.Tensor) -> torch.Tensor:
        hidden, _ = self.lstm(self.embedding(tokens))
        return self.output(hidden)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus")
    parser.add_argument("--output", default="artifacts/text-lstm.pt")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--sequence-length", type=int, default=160)
    args = parser.parse_args()

    text = Path(args.corpus).read_text(encoding="utf-8")
    vocabulary = sorted(set(text))
    to_id = {character: index for index, character in enumerate(vocabulary)}
    dataset = TextWindows([to_id[c] for c in text], args.sequence_length)
    if not len(dataset):
        raise SystemExit("Corpus must be longer than the sequence length")
    loader = DataLoader(dataset, batch_size=64, shuffle=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")
    model = CharLSTM(len(vocabulary)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3)
    loss_function = nn.CrossEntropyLoss()

    model.train()
    for epoch in range(args.epochs):
        running = 0.0
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            logits = model(x)
            loss = loss_function(logits.reshape(-1, len(vocabulary)), y.reshape(-1))
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            running += loss.item()
        print(f"epoch={epoch + 1} loss={running / len(loader):.4f}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "vocabulary": vocabulary}, output)


if __name__ == "__main__":
    main()

