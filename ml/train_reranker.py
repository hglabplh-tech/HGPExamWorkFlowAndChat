# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Fine-tune mBERT or XLM-RoBERTa as a query/passage relevance reranker.

Expected CSV columns: query,passage,label where label is 0 or 1.
"""
import argparse

from datasets import load_dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer, DataCollatorWithPadding, Trainer, TrainingArguments


MODELS = {
    "mbert": "google-bert/bert-base-multilingual-cased",
    "xlm-roberta": "FacebookAI/xlm-roberta-base",
}


def main() -> None:
    """Perform the main operation."""
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file")
    parser.add_argument("--family", choices=MODELS, default="mbert")
    parser.add_argument("--output", default="artifacts/multilingual-reranker")
    parser.add_argument("--epochs", type=int, default=2)
    args = parser.parse_args()
    dataset = load_dataset("csv", data_files=args.csv_file)["train"].train_test_split(test_size=0.15, seed=42)
    tokenizer = AutoTokenizer.from_pretrained(MODELS[args.family])

    def tokenize(batch: dict) -> dict:
        """Perform the tokenize operation."""
        return tokenizer(batch["query"], batch["passage"], truncation=True, max_length=384)

    encoded = dataset.map(tokenize, batched=True).rename_column("label", "labels")
    model = AutoModelForSequenceClassification.from_pretrained(MODELS[args.family], num_labels=2)
    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=args.output,
            eval_strategy="epoch",
            save_strategy="epoch",
            learning_rate=2e-5,
            per_device_train_batch_size=8,
            per_device_eval_batch_size=8,
            num_train_epochs=args.epochs,
            load_best_model_at_end=True,
            report_to="none",
        ),
        train_dataset=encoded["train"],
        eval_dataset=encoded["test"],
        processing_class=tokenizer,
        data_collator=DataCollatorWithPadding(tokenizer),
    )
    trainer.train()
    trainer.save_model(args.output)
    tokenizer.save_pretrained(args.output)


if __name__ == "__main__":
    main()
