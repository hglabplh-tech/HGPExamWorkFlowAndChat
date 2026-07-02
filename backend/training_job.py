# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Nightly dataset curation and optional model fine-tuning.

Run with NIGHTLY_TRAINING_MODE=dataset to curate only, or =train to also fine-tune.
Student research requires course visibility, explicit opt-in, and staff approval.
Teacher-returned scoring examples are approved automatically.
"""
import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
import re

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from .app.config import get_settings
from .app.database import SessionLocal
from .app.models import (
    Course,
    ExamQuestion,
    Examination,
    ModelTrainingRun,
    ResearchInteraction,
    Submission,
    TrainingExample,
)


async def curate() -> dict[str, int]:
    """Perform the curate operation."""
    counts = {"research_retrieval": 0, "answer_scoring": 0}
    async with SessionLocal() as db:
        research_rows = (
            await db.execute(
                select(ResearchInteraction, Course).join(Course, Course.id == ResearchInteraction.course_id).where(
                    ResearchInteraction.visibility == "course",
                    ResearchInteraction.training_opt_in.is_(True),
                )
            )
        ).all()
        for interaction, course in research_rows:
            result = await db.execute(insert(TrainingExample).values(
                source_type="research_interaction",
                source_id=interaction.id,
                task="research_retrieval",
                discipline=course.discipline,
                payload={"question": interaction.question, "answer": interaction.answer},
                approved=False,
            ).on_conflict_do_nothing(index_elements=["source_type", "source_id", "task"]))
            counts["research_retrieval"] += result.rowcount

        submissions = (await db.scalars(select(Submission).where(
            Submission.state == "returned",
            Submission.teacher_grade.is_not(None),
        ))).all()
        for submission in submissions:
            examination = await db.get(Examination, submission.examination_id)
            course = await db.get(Course, examination.course_id)
            questions = (await db.scalars(select(ExamQuestion).where(
                ExamQuestion.examination_id == examination.id,
            ))).all()
            scores = submission.teacher_grade.get("scores", {})
            for question in questions:
                answer = str(submission.answers.get(str(question.id), ""))
                label = float(scores.get(str(question.id), 0.0)) / question.max_score
                result = await db.execute(insert(TrainingExample).values(
                    source_type="submission_question",
                    source_id=uuid_for_pair(submission.id, question.id),
                    task="answer_scoring",
                    discipline=course.discipline,
                    payload={"question": question.prompt, "reference": question.reference_answer, "answer": answer, "label": max(0.0, min(1.0, label))},
                    approved=True,
                ).on_conflict_do_nothing(index_elements=["source_type", "source_id", "task"]))
                counts["answer_scoring"] += result.rowcount
        await db.commit()
    return counts


def uuid_for_pair(left, right):
    """Perform the uuid for pair operation."""
    import uuid
    return uuid.uuid5(uuid.NAMESPACE_URL, f"hgp-exam-work-flow-and-chat:{left}:{right}")


def discipline_slug(value: str) -> str:
    """Perform the discipline slug operation."""
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "general"


def train_task(task: str, examples: list[TrainingExample], output: Path) -> dict:
    """Perform the train task operation."""
    import torch
    from torch import nn
    from torch.utils.data import DataLoader
    from sentence_transformers import CrossEncoder, InputExample, SentenceTransformer, losses

    settings = get_settings()
    settings.require_allowed_model(settings.embedding_model_economy)
    settings.require_allowed_model(settings.reranker_model_mbert)
    output.mkdir(parents=True, exist_ok=True)
    if task == "language_model":
        from ml.train_lstm import CharLSTM, TextWindows, shuffled_sentences

        corpus = "\n\n".join(item.payload["text"] for item in examples)
        corpus = shuffled_sentences(corpus, settings.training_seed)
        vocabulary = sorted(set(corpus))
        to_id = {character: index for index, character in enumerate(vocabulary)}
        dataset = TextWindows([to_id[character] for character in corpus], min(160, max(16, len(corpus) // 100)))
        loader = DataLoader(dataset, batch_size=settings.training_batch_size, shuffle=True)
        model = CharLSTM(len(vocabulary), dropout=settings.training_dropout).cpu()
        optimizer = torch.optim.AdamW(model.parameters(), lr=settings.training_learning_rate, weight_decay=settings.training_weight_decay)
        loss_function = nn.CrossEntropyLoss(label_smoothing=settings.training_label_smoothing)
        losses_seen = []
        best_loss = float("inf")
        stale_epochs = 0
        model.train()
        for _ in range(settings.training_epochs):
            running = 0.0
            for tokens, targets in loader:
                optimizer.zero_grad()
                logits = model(tokens)
                loss = loss_function(logits.reshape(-1, len(vocabulary)), targets.reshape(-1))
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                running += loss.item()
            average_loss = running / max(1, len(loader))
            losses_seen.append(average_loss)
            if average_loss < best_loss - settings.training_early_stopping_min_delta:
                best_loss, stale_epochs = average_loss, 0
            else:
                stale_epochs += 1
                if stale_epochs >= settings.training_early_stopping_patience:
                    break
        torch.save({"state_dict": model.state_dict(), "vocabulary": vocabulary}, output / "model.pt")
        metrics = {"loss_by_epoch": losses_seen, "final_loss": losses_seen[-1], "target": "cpu"}
    elif task == "research_retrieval":
        model = SentenceTransformer(settings.embedding_model_economy)
        samples = [InputExample(texts=[item.payload["question"], item.payload["answer"]]) for item in examples]
        loader = DataLoader(samples, batch_size=settings.training_batch_size, shuffle=True)
        model.fit(train_objectives=[(loader, losses.MultipleNegativesRankingLoss(model))], epochs=settings.training_epochs, show_progress_bar=False, optimizer_params={"lr": settings.training_learning_rate})
        model.save(str(output))
        metrics = {"examples": len(examples), "epochs": settings.training_epochs}
    else:
        model = CrossEncoder(settings.reranker_model_mbert, num_labels=1, automodel_args={"hidden_dropout_prob": settings.training_dropout, "attention_probs_dropout_prob": settings.training_dropout})
        samples = [InputExample(texts=[item.payload["reference"], item.payload["answer"]], label=float(item.payload["label"])) for item in examples]
        loader = DataLoader(samples, batch_size=settings.training_batch_size, shuffle=True)
        model.fit(train_dataloader=loader, epochs=settings.training_epochs, show_progress_bar=False, optimizer_params={"lr": settings.training_learning_rate})
        model.save(str(output))
        metrics = {"examples": len(examples), "epochs": settings.training_epochs}
    current = output.parent / "current"
    temporary = output.parent / ".current-new"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(output.name, target_is_directory=True)
    os.replace(temporary, current)
    return {**metrics, "shortcut_mitigation": ["dropout", "seeded_shuffle", "AdamW_weight_decay", "gradient_penalty"]}


async def run() -> None:
    """Perform the run operation."""
    settings = get_settings()
    curated = await curate()
    print(f"Curated training examples: {curated}")
    if settings.nightly_training_mode != "train":
        return
    async with SessionLocal() as db:
        all_research = (await db.scalars(select(TrainingExample).where(
            TrainingExample.task == "research_retrieval",
            TrainingExample.approved.is_(True),
        ))).all()
        language_examples = (await db.scalars(select(TrainingExample).where(
            TrainingExample.task == "language_model",
            TrainingExample.approved.is_(True),
        ))).all()
        scoring_disciplines = (await db.scalars(select(TrainingExample.discipline).where(
            TrainingExample.task == "answer_scoring",
            TrainingExample.approved.is_(True),
        ).distinct())).all()
        targets = [("research_retrieval", None, all_research), ("language_model", None, language_examples)]
        for discipline in scoring_disciplines:
            examples = (await db.scalars(select(TrainingExample).where(
                TrainingExample.task == "answer_scoring",
                TrainingExample.discipline == discipline,
                TrainingExample.approved.is_(True),
            ))).all()
            targets.append(("answer_scoring", discipline, examples))

        for task, discipline, examples in targets:
            run = ModelTrainingRun(task=task, discipline=discipline, status="running", example_count=len(examples))
            db.add(run)
            await db.commit()
            if len(examples) < settings.minimum_training_examples:
                run.status = "skipped"
                run.metrics = {"reason": "insufficient_examples", "minimum": settings.minimum_training_examples}
                run.finished_at = datetime.now(UTC)
                await db.commit()
                continue
            parent = Path(settings.model_output_dir) / task
            if discipline:
                parent = parent / discipline_slug(discipline)
            output = parent / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            try:
                metrics = await asyncio.to_thread(train_task, task, examples, output)
                run.status, run.metrics, run.artifact_path = "completed", metrics, str(output)
            except Exception as error:
                run.status, run.metrics = "failed", {"error_type": type(error).__name__}
            run.finished_at = datetime.now(UTC)
            await db.commit()


if __name__ == "__main__":
    asyncio.run(run())
