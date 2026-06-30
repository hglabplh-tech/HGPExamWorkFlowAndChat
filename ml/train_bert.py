"""Fine-tune a Hugging Face BERT-compatible model for course text classification.

Expected CSV columns: text,label. Labels are integer class identifiers.
"""
import argparse

from datasets import load_dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer, DataCollatorWithPadding, Trainer, TrainingArguments


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file")
    parser.add_argument("--model", default="distilbert/distilbert-base-multilingual-cased")
    parser.add_argument("--output", default="artifacts/course-bert")
    parser.add_argument("--labels", type=int, required=True)
    args = parser.parse_args()

    dataset = load_dataset("csv", data_files=args.csv_file)["train"].train_test_split(test_size=0.15, seed=42)
    tokenizer = AutoTokenizer.from_pretrained(args.model)

    def tokenize(batch: dict) -> dict:
        return tokenizer(batch["text"], truncation=True, max_length=512)

    encoded = dataset.map(tokenize, batched=True)
    model = AutoModelForSequenceClassification.from_pretrained(args.model, num_labels=args.labels)
    training = TrainingArguments(
        output_dir=args.output,
        eval_strategy="epoch",
        save_strategy="epoch",
        learning_rate=2e-5,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=8,
        num_train_epochs=3,
        weight_decay=0.01,
        load_best_model_at_end=True,
        report_to="none",
    )
    trainer = Trainer(
        model=model,
        args=training,
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

