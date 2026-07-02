# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Train a small character LSTM for experimentation, not factual RAG answers."""
import argparse
import json
import random
import re
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset


class TextWindows(Dataset):
    """Represent textwindows."""
    def __init__(self, encoded: list[int], sequence_length: int):
        """Perform the init operation."""
        self.data, self.sequence_length = encoded, sequence_length

    def __len__(self) -> int:
        """Perform the len operation."""
        return max(0, len(self.data) - self.sequence_length)

    def __getitem__(self, index: int):
        """Perform the getitem operation."""
        x = torch.tensor(self.data[index:index + self.sequence_length], dtype=torch.long)
        y = torch.tensor(self.data[index + 1:index + self.sequence_length + 1], dtype=torch.long)
        return x, y


class CharLSTM(nn.Module):
    """Represent charlstm."""
    def __init__(self, vocabulary_size: int, embedding_size: int = 128, hidden_size: int = 256, dropout: float = 0.3):
        """Perform the init operation."""
        super().__init__()
        self.embedding = nn.Embedding(vocabulary_size, embedding_size)
        self.input_dropout = nn.Dropout(dropout)
        self.lstm = nn.LSTM(embedding_size, hidden_size, batch_first=True, num_layers=2, dropout=dropout)
        self.output_dropout = nn.Dropout(dropout)
        self.output = nn.Linear(hidden_size, vocabulary_size)

    def forward(self, tokens: torch.Tensor) -> torch.Tensor:
        """Perform the forward operation."""
        hidden, _ = self.lstm(self.input_dropout(self.embedding(tokens)))
        return self.output(self.output_dropout(hidden))


def shuffled_sentences(text: str, seed: int) -> str:
    """Restructure sentence order deterministically to weaken corpus-order shortcuts."""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    random.Random(seed).shuffle(sentences)
    return " ".join(sentences)


def evaluate(model: nn.Module, loader: DataLoader, loss_function: nn.Module, vocabulary_size: int) -> float:
    """Return mean held-out loss as the LSTM learning-progress measure."""
    model.eval()
    total = 0.0
    with torch.inference_mode():
        for x, y in loader:
            logits = model(x)
            total += loss_function(logits.reshape(-1, vocabulary_size), y.reshape(-1)).item()
    model.train()
    return total / max(1, len(loader))


def main() -> None:
    """Perform the main operation."""
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus")
    parser.add_argument("--output", default="artifacts/text-lstm.pt")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--sequence-length", type=int, default=160)
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--early-stopping-patience", type=int, default=2)
    parser.add_argument("--early-stopping-min-delta", type=float, default=0.0001)
    parser.add_argument("--vocab-file", default=None, help="Optional exported project vocabulary file to seed the character vocabulary.")
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    text = shuffled_sentences(Path(args.corpus).read_text(encoding="utf-8"), args.seed)
    vocabulary = sorted(set(text))
    if args.vocab_file:
        vocabulary = sorted(set(vocabulary) | set(Path(args.vocab_file).read_text(encoding="utf-8")))
    to_id = {character: index for index, character in enumerate(vocabulary)}
    dataset = TextWindows([to_id[c] for c in text], args.sequence_length)
    if not len(dataset):
        raise SystemExit("Corpus must be longer than the sequence length")
    split = max(1, int(len(dataset) * 0.9))
    train_set, validation_set = torch.utils.data.random_split(dataset, [split, len(dataset) - split], generator=torch.Generator().manual_seed(args.seed))
    loader = DataLoader(train_set, batch_size=64, shuffle=True)
    validation_loader = DataLoader(validation_set, batch_size=64, shuffle=False)
    device = torch.device("cpu")
    model = CharLSTM(len(vocabulary), dropout=args.dropout).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    loss_function = nn.CrossEntropyLoss()

    model.train()
    progress = []
    best_loss = float("inf")
    stale_epochs = 0
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
        training_loss = running / len(loader)
        validation_loss = evaluate(model, validation_loader, loss_function, len(vocabulary)) if len(validation_set) else training_loss
        progress.append({"epoch": epoch + 1, "training_loss": training_loss, "validation_loss": validation_loss})
        print(f"epoch={epoch + 1} training_loss={training_loss:.4f} validation_loss={validation_loss:.4f}")
        if validation_loss < best_loss - args.early_stopping_min_delta:
            best_loss = validation_loss
            stale_epochs = 0
        else:
            stale_epochs += 1
            if stale_epochs >= args.early_stopping_patience:
                print(f"early_stop epoch={epoch + 1} best_validation_loss={best_loss:.4f}")
                break

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "vocabulary": vocabulary, "configuration": vars(args)}, output)
    output.with_suffix(".learning-progress.json").write_text(json.dumps({
        "progress": progress,
        "shortcut_mitigation": ["dropout", "sentence_restructuring", "seeded_shuffle", "AdamW_weight_decay", "gradient_clipping"],
        "target_device": "cpu",
        "project_vocab_file": args.vocab_file,
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
