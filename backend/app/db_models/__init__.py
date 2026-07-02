"""Domain-organized ORM model exports.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""
from .base import Base, Role, UUIDMixin
from .identity import ActiveUserSession, Course, Enrollment, User
from .knowledge import Document, DocumentChunk, Thesaurus, VideoResource
from .examinations import DisciplineScoringProfile, Examination, ExamQuestion, ExamRuleSet, GradeEvent, Submission, SubmissionConfirmation
from .collaboration import Conversation, ConversationMember, ExamGroup, Message, ResearchHistory, ResearchHistoryEntry, ResearchInteraction
from .training import ModelTrainingRun, TrainingExample
from .audit import AuditEvent, RequestNonce
from .trust import OCSPQuery, PrivatePKI, SignatureValidation, TrustList, UserCertificate

__all__ = [name for name in globals() if not name.startswith("_")]
