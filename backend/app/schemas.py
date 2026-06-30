# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for schemas."""
import uuid
import base64
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CourseCreate(BaseModel):
    """Represent coursecreate."""
    code: str = Field(min_length=2, max_length=40)
    title: str = Field(min_length=2, max_length=240)
    discipline: str
    description: str = ""


class CourseOut(CourseCreate):
    """Represent courseout."""
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class DocumentCreate(BaseModel):
    """Represent documentcreate."""
    title: str
    course_id: uuid.UUID | None = None
    body_text: str
    source_uri: str | None = None
    metadata: dict = Field(default_factory=dict)


class VideoCreate(BaseModel):
    """Represent videocreate."""
    youtube_video_id: str
    youtube_url: HttpUrl
    title: str
    description: str = ""
    discipline: str
    question_tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    course_id: uuid.UUID | None = None


class SearchHit(BaseModel):
    """Represent searchhit."""
    kind: str
    id: uuid.UUID
    title: str
    excerpt: str
    score: float
    url: str | None = None
    score_components: dict[str, float] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Represent searchresponse."""
    query: str
    results: list[SearchHit]
    coverage_warning: str | None = None


class SubmissionCreate(BaseModel):
    """Represent submissioncreate."""
    examination_id: uuid.UUID
    answers: dict[str, str]
    content_base64: str
    content_type: str = "application/json"
    signature_base64: str
    signing_certificate_pem: str = Field(min_length=100, max_length=20000)
    signed_at: datetime

    def content_bytes(self) -> bytes:
        """Perform the content bytes operation."""
        return base64.b64decode(self.content_base64, validate=True)

    def signature_bytes(self) -> bytes:
        """Perform the signature bytes operation."""
        return base64.b64decode(self.signature_base64, validate=True)


class SubmissionOut(BaseModel):
    """Represent submissionout."""
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    examination_id: uuid.UUID
    student_id: uuid.UUID
    answers: dict
    ai_grade: dict | None
    teacher_grade: dict | None
    submitted_at: datetime
    state: str
    feedback_released_at: datetime | None
    returned_at: datetime | None


class GradeOverride(BaseModel):
    """Represent gradeoverride."""
    scores: dict[str, float]
    total: float
    feedback: str
    reason: str = Field(min_length=3, max_length=1000)


class InstructorReturn(BaseModel):
    """Represent instructorreturn."""
    signature_base64: str
    signing_certificate_pem: str = Field(min_length=100, max_length=20000)
    signed_at: datetime


class PublicKeyUpdate(BaseModel):
    """Represent publickeyupdate."""
    public_key_pem: str = Field(min_length=80, max_length=2000)


class UserCreate(BaseModel):
    """Represent usercreate."""
    email: str
    display_name: str
    password: str = Field(min_length=12, max_length=1024)
    role: str = "student"


class UserUpdate(BaseModel):
    """Represent userupdate."""
    display_name: str | None = None
    active: bool | None = None
    role: str | None = None
    client_cert_fingerprint: str | None = Field(default=None, pattern=r"^[A-Fa-f0-9:]{32,128}$")


class DeletionRequest(BaseModel):
    """Represent deletionrequest."""
    override_retention: bool = False
    reason: str = Field(min_length=10, max_length=2000)


class ConversationCreate(BaseModel):
    """Represent conversationcreate."""
    course_id: uuid.UUID
    title: str
    member_ids: list[uuid.UUID] = Field(min_length=1)
    kind: str = "direct"


class MessageCreate(BaseModel):
    """Represent messagecreate."""
    body: str = Field(default="", max_length=4000)
    shared_type: str | None = None
    shared_id: uuid.UUID | None = None


class TrustListCreate(BaseModel):
    """Represent trustlistcreate."""
    name: str = Field(min_length=2, max_length=240)
    framework: str = Field(pattern="^(eu_eidas|custom_etsi|us_private_pki|us_federal_profile)$")
    territory: str | None = Field(default=None, max_length=12)
    source_url: str | None = None
    xml_base64: str
    is_official: bool = False


class TrustListDecision(BaseModel):
    """Represent trustlistdecision."""
    enable: bool
    reason: str = Field(min_length=10, max_length=2000)


class SignatureValidationRequest(BaseModel):
    """Represent signaturevalidationrequest."""
    signed_document_base64: str
    framework: str = Field(pattern="^(eu_eidas|custom_etsi|us_private_pki|us_federal_profile)$")
    signature_format: str = Field(pattern="^(PAdES|XAdES|CAdES|JAdES|CMS|XMLDSig|PDF)$")
    trust_list_ids: list[uuid.UUID] = Field(default_factory=list)
    validation_time: datetime | None = None


class PrivatePKICreate(BaseModel):
    """Represent privatepkicreate."""
    name: str = Field(min_length=2, max_length=240)
    root_certificate_pem: str
    intermediate_bundle_pem: str = ""
    ocsp_responder_url: str | None = None
    ocsp_responder_certificate_pem: str | None = None


class UserCertificateAssign(BaseModel):
    """Represent usercertificateassign."""
    certificate_pem: str
    reason: str = Field(min_length=10, max_length=2000)


class CertificateRevoke(BaseModel):
    """Represent certificaterevoke."""
    reason: str = Field(pattern="^(unspecified|key_compromise|ca_compromise|affiliation_changed|superseded|cessation_of_operation|certificate_hold|privilege_withdrawn)$")
    comment: str = Field(min_length=10, max_length=2000)


class ScoringProfileCreate(BaseModel):
    """Represent scoringprofilecreate."""
    discipline: str = Field(min_length=2, max_length=120)
    grading_weights: dict[str, float] = Field(default_factory=lambda: {
        "jaccard": 0.10,
        "keywords": 0.15,
        "semantic": 0.25,
        "trained_scoring": 0.10,
        "fact_entailment": 0.20,
        "contradiction": 0.10,
        "length": 0.10,
    })
    search_weights: dict[str, float] = Field(default_factory=lambda: {
        "full_text": 0.40,
        "semantic": 0.60,
    })
    semantic_profile: str = Field(default="economy", pattern="^(economy|quality)$")

    def validate_weights(self) -> None:
        """Perform the validate weights operation."""
        expected_grading = {"jaccard", "keywords", "semantic", "trained_scoring", "fact_entailment", "contradiction", "length"}
        if set(self.grading_weights) != expected_grading or set(self.search_weights) != {"full_text", "semantic"}:
            raise ValueError("Weight keys do not match the supported scoring signals")
        for group in (self.grading_weights, self.search_weights):
            if any(value < 0 or value > 1 for value in group.values()) or sum(group.values()) <= 0:
                raise ValueError("Weights must be between 0 and 1 with a positive total")


class ExaminationCreate(BaseModel):
    """Represent examinationcreate."""
    course_id: uuid.UUID
    title: str = Field(min_length=2, max_length=300)
    instructions: str = ""
    kind: str = Field(default="practice", pattern="^(practice|real)$")
    closes_at: datetime | None = None


class QuestionCreate(BaseModel):
    """Represent questioncreate."""
    prompt: str = Field(min_length=2)
    reference_answer: str = Field(min_length=1)
    required_keywords: list[str] = Field(default_factory=list)
    expected_facts: list[str] = Field(default_factory=list)
    max_score: float = Field(gt=0, le=1000)


class ResearchQuestionCreate(BaseModel):
    """Represent researchquestioncreate."""
    course_id: uuid.UUID
    question: str = Field(min_length=2, max_length=4000)
    visibility: str = Field(default="private", pattern="^(private|conversation|course)$")
    conversation_id: uuid.UUID | None = None
    training_opt_in: bool = False


class ResearchVisibilityUpdate(BaseModel):
    """Represent researchvisibilityupdate."""
    visibility: str = Field(pattern="^(private|conversation|course)$")
    conversation_id: uuid.UUID | None = None
    training_opt_in: bool = False


class ExaminationRelease(BaseModel):
    """Represent examinationrelease."""
    closes_at: datetime | None = None
    reason: str = Field(min_length=3, max_length=1000)


class ExamDraftRequest(BaseModel):
    """Represent examdraftrequest."""
    course_id: uuid.UUID
    title: str
    learning_objectives: list[str] = Field(min_length=1)
    number_of_questions: int = Field(default=5, ge=1, le=30)
    kind: str = Field(default="practice", pattern="^(practice|real)$")


class TrainingApproval(BaseModel):
    """Represent trainingapproval."""
    approved: bool
    reason: str = Field(min_length=10, max_length=2000)
