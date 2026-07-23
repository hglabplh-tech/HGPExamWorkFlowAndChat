"""Domain-organized ORM model exports.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""
from .base import Base, Role, UUIDMixin
from .identity import ActiveUserSession, Course, Enrollment, User
from .knowledge import CourseKnowledgeBase, Document, DocumentChunk, Thesaurus, VideoResource
from .examinations import DisciplineScoringProfile, Examination, ExamQuestion, ExamRuleSet, GradeEvent, Submission, SubmissionConfirmation
from .collaboration import Conversation, ConversationMember, ExamGroup, Message, ResearchHistory, ResearchHistoryEntry, ResearchInteraction
from .training import ModelTrainingRun, TrainingExample
from .audit import AuditEvent, RequestNonce
from .trust import OCSPQuery, PrivatePKI, SignatureValidation, TrustList, UserCertificate
from .system import MailServerSettings

__all__ = [
    "ActiveUserSession", "AuditEvent", "Base", "Conversation",
    "ConversationMember", "Course", "CourseKnowledgeBase", "DisciplineScoringProfile", "Document",
    "DocumentChunk", "Enrollment", "ExamGroup", "ExamQuestion", "ExamRuleSet",
    "Examination", "GradeEvent", "MailServerSettings", "Message", "ModelTrainingRun", "OCSPQuery",
    "PrivatePKI", "RequestNonce", "ResearchHistory", "ResearchHistoryEntry",
    "ResearchInteraction", "Role", "SignatureValidation", "Submission",
    "SubmissionConfirmation", "Thesaurus", "TrainingExample", "TrustList",
    "UUIDMixin", "User", "UserCertificate", "VideoResource",
]
