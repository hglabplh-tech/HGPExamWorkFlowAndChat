# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Fine-tune a Hugging Face BERT-compatible model for course text classification.

Expected CSV columns: text,label. Labels are integer class identifiers.
"""
import argparse
import json
import random
import re
from pathlib import Path

import numpy as np

def restructure_sentences(text: str, seed: int) -> str:
    """Create a deterministic sentence-order variant to reduce positional shortcuts."""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    if len(sentences) < 2:
        return text
    random.Random(seed).shuffle(sentences)
    return " ".join(sentences)


def classification_metrics(prediction) -> dict[str, float]:
    """Calculate accuracy as an interpretable learning-progress score."""
    labels = prediction.label_ids
    predicted = np.argmax(prediction.predictions, axis=-1)
    return {"accuracy": float((predicted == labels).mean())}


def main() -> None:
    """Perform the main operation."""
    from datasets import load_dataset
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, DataCollatorWithPadding, EarlyStoppingCallback, Trainer, TrainingArguments

    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file")
    parser.add_argument("--model", default="google-bert/bert-base-multilingual-cased")
    parser.add_argument("--output", default="artifacts/course-bert")
    parser.add_argument("--labels", type=int, required=True)
    parser.add_argument("--dropout", type=float, default=0.25)
    parser.add_argument("--learning-rate", type=float, default=2e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--label-smoothing", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--early-stopping-patience", type=int, default=2)
    parser.add_argument("--early-stopping-min-delta", type=float, default=0.0001)
    parser.add_argument("--vocab-file", default=None, help="Optional exported project vocabulary file recorded with the model artifact.")
    args = parser.parse_args()

    dataset = load_dataset("csv", data_files=args.csv_file)["train"]
    dataset = dataset.map(lambda row, index: {"text": restructure_sentences(row["text"], args.seed + index)}, with_indices=True)
    dataset = dataset.shuffle(seed=args.seed).train_test_split(test_size=0.15, seed=args.seed, stratify_by_column="label")
    tokenizer = AutoTokenizer.from_pretrained(args.model)

    def tokenize(batch: dict) -> dict:
        """Perform the tokenize operation."""
        return tokenizer(batch["text"], truncation=True, max_length=512)

    encoded = dataset.map(tokenize, batched=True)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.model, num_labels=args.labels,
        hidden_dropout_prob=args.dropout,
        attention_probs_dropout_prob=args.dropout,
    )
    training = TrainingArguments(
        output_dir=args.output,
        eval_strategy="epoch",
        save_strategy="epoch",
        learning_rate=args.learning_rate,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=8,
        num_train_epochs=3,
        weight_decay=args.weight_decay,
        label_smoothing_factor=args.label_smoothing,
        optim="adamw_torch",
        seed=args.seed,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        report_to="none",
    )
    trainer = Trainer(
        model=model,
        args=training,
        train_dataset=encoded["train"],
        eval_dataset=encoded["test"],
        processing_class=tokenizer,
        data_collator=DataCollatorWithPadding(tokenizer),
        compute_metrics=classification_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=args.early_stopping_patience, early_stopping_threshold=args.early_stopping_min_delta)],
    )
    training_result = trainer.train()
    evaluation = trainer.evaluate()
    trainer.save_model(args.output)
    tokenizer.save_pretrained(args.output)
    Path(args.output, "learning-progress.json").write_text(json.dumps({
        "training_loss": training_result.training_loss,
        "evaluation": evaluation,
        "shortcut_mitigation": ["dropout", "sentence_restructuring", "seeded_shuffle", "label_smoothing", "AdamW_weight_decay"],
        "base_model": args.model,
        "project_vocab_file": args.vocab_file,
        "artifact_type": "project-fine-tuned-mBERT",
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
