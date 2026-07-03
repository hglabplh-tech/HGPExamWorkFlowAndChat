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
    query_expansion: dict | None = None


class ThesaurusOut(BaseModel):
    """Represent a stored full-text thesaurus."""
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    language: str
    source_format: str
    entries: list[dict]
    active: bool
    source_sha256: str
    created_at: datetime


class ThesaurusJsonImport(BaseModel):
    """Accept normalized thesaurus JSON from an administration client."""
    name: str = Field(min_length=2, max_length=120)
    language: str = Field(default="simple", max_length=20)
    entries: list[dict]
    active: bool = True


class SubmissionCreate(BaseModel):
    """Represent submissioncreate."""
    examination_id: uuid.UUID
    answers: dict[str, object]
    content_base64: str
    content_type: str = "application/json"
    signature_base64: str
    signing_certificate_pem: str = Field(min_length=100, max_length=20000)
    signed_at: datetime
    file_confirmed: bool = False
    ready_confirmed: bool = False
    confirmation_token: str | None = None
    replaces_submission_id: uuid.UUID | None = None
    exam_group_id: uuid.UUID | None = None

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
    correction_until: datetime | None
    supersedes_submission_id: uuid.UUID | None


class SubmissionPrepare(BaseModel):
    """Describe a real-exam file before the final confirmation step."""
    examination_id: uuid.UUID
    content_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")


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
    matriculation_number: str | None = Field(default=None, max_length=80)
    role: str = "student"
    permissions: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    """Represent userupdate."""
    display_name: str | None = None
    matriculation_number: str | None = Field(default=None, max_length=80)
    active: bool | None = None
    role: str | None = None
    permissions: list[str] | None = None
    client_cert_fingerprint: str | None = Field(default=None, pattern=r"^[A-Fa-f0-9:]{32,128}$")


class TotpVerify(BaseModel):
    """Verify and activate a user's TOTP authenticator setup."""
    code: str = Field(pattern=r"^\d{6}$")


class RegistrationStart(BaseModel):
    """Start self-registration for an administrator-created user entry."""
    user_id: str = Field(min_length=2, max_length=320)
    password: str = Field(min_length=12, max_length=1024)
    contact_email: str = Field(min_length=3, max_length=320)
    mobile_number: str | None = Field(default=None, max_length=40)


class RegistrationVerify(BaseModel):
    """Verify email/SMS codes and choose the later TOTP delivery channel."""
    user_id: str = Field(min_length=2, max_length=320)
    password: str = Field(min_length=12, max_length=1024)
    email_code: str = Field(pattern=r"^\d{6}$")
    mobile_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    totp_delivery_channel: str = Field(default="email", pattern="^(email|sms)$")


class QuestionDraftScore(BaseModel):
    """Score one practice-exam answer before final submission."""
    answer: str | list[str]


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
    purpose: str = Field(default="general", pattern="^(general|exam_preparation|exam_work)$")
    topic: str | None = Field(default=None, max_length=300)
    examination_id: uuid.UUID | None = None


class RandomExamGroupsCreate(BaseModel):
    """Configure random exam-preparation or group-exam assignment."""
    examination_id: uuid.UUID
    topics: list[str] = Field(min_length=1, max_length=100)
    group_size: int = Field(default=3, ge=2, le=20)
    purpose: str = Field(default="exam_preparation", pattern="^(exam_preparation|exam_work)$")
    seed: str | None = Field(default=None, max_length=128)


class ExamGroupCertificateAssign(BaseModel):
    """Register an externally issued X.509 certificate; private keys stay client-side."""
    certificate_pem: str = Field(min_length=100, max_length=20000)
    private_pki_id: uuid.UUID
    reason: str = Field(min_length=10, max_length=1000)


class MessageCreate(BaseModel):
    """Represent messagecreate."""
    body: str = Field(default="", max_length=4000)
    attachments: list[dict] = Field(default_factory=list)
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
        "full_text": 0.35,
        "bm25": 0.20,
        "semantic": 0.45,
    })
    semantic_profile: str = Field(default="economy", pattern="^(economy|quality)$")

    def validate_weights(self) -> None:
        """Perform the validate weights operation."""
        expected_grading = {"jaccard", "keywords", "semantic", "trained_scoring", "fact_entailment", "contradiction", "length"}
        if set(self.grading_weights) != expected_grading or set(self.search_weights) != {"full_text", "bm25", "semantic"}:
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
    group_mode: bool = False
    rule_set_id: uuid.UUID | None = None


class QuestionCreate(BaseModel):
    """Represent questioncreate."""
    prompt: str = Field(min_length=2)
    reference_answer: str = Field(min_length=1)
    required_keywords: list[str] = Field(default_factory=list)
    expected_facts: list[str] = Field(default_factory=list)
    max_score: float = Field(gt=0, le=1000)
    question_type: str = Field(default="free_text", pattern="^(free_text|single_choice|multiple_choice)$")
    choices: list[str] = Field(default_factory=list)
    correct_options: list[str] = Field(default_factory=list)
    partial_credit: bool = False

    def validate_question(self) -> None:
        """Ensure choice questions have unique options and valid answers."""
        if self.question_type == "free_text":
            return
        if len(self.choices) < 2 or len(set(self.choices)) != len(self.choices):
            raise ValueError("Choice questions require at least two unique choices")
        if not self.correct_options or not set(self.correct_options) <= set(self.choices):
            raise ValueError("Every correct option must occur in choices")
        if self.question_type == "single_choice" and len(self.correct_options) != 1:
            raise ValueError("Single-choice questions require exactly one correct option")


class ExaminationJsonCreate(BaseModel):
    """Create an examination and its reviewed questions from one JSON document."""
    title: str = Field(min_length=2, max_length=300)
    instructions: str = ""
    kind: str = Field(default="practice", pattern="^(practice|real)$")
    group_mode: bool = False
    rule_set_id: uuid.UUID | None = None
    questions: list[QuestionCreate] = Field(min_length=1)

    def validate_exam(self) -> None:
        """Validate every embedded question before database import."""
        for question in self.questions:
            question.validate_question()


class ExamRuleSetCreate(BaseModel):
    """Define course-specific format, citation, topic, and weighted quality rules."""
    course_id: uuid.UUID
    name: str = Field(min_length=2, max_length=200)
    version: int = Field(default=1, ge=1)
    page_count_min: int = Field(default=1, ge=1, le=10000)
    page_count_max: int = Field(default=20, ge=1, le=10000)
    citation_style: str = Field(default="APA", max_length=50)
    citation_check: str = Field(default="author_year_and_reference_list", max_length=200)
    topic: str = Field(min_length=2, max_length=1000)
    weights: dict[str, float] = Field(default_factory=lambda: {"context": 0.4, "design": 0.2, "wording": 0.2, "citations": 0.2})

    def validate_rules(self) -> None:
        """Validate page bounds and normalized scoring dimensions."""
        if self.page_count_min > self.page_count_max:
            raise ValueError("Minimum page count cannot exceed maximum")
        expected = {"context", "design", "wording", "citations"}
        if set(self.weights) != expected or any(value < 0 for value in self.weights.values()):
            raise ValueError("Weights must define non-negative context, design, wording, and citations")
        if abs(sum(self.weights.values()) - 1.0) > 0.000001:
            raise ValueError("Rule weights must sum to 1.0")


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


class ResearchHistoryCreate(BaseModel):
    """Create a new per-user research history, equivalent to a new chat."""
    label: str = Field(default="New chat", min_length=1, max_length=160)


class ResearchHistoryUpdate(BaseModel):
    """Update one research history label or stored state."""
    label: str | None = Field(default=None, min_length=1, max_length=160)
    stored: bool | None = None


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


class IntegrityCheckRequest(BaseModel):
    """Configure an instructor-requested academic-integrity review."""
    search_internet: bool = True
    check_grammar: bool = True
    check_apa: bool = True
    check_facts: bool = True
    maximum_queries: int = Field(default=5, ge=1, le=20)


class EmailRequest(BaseModel):
    """Describe an audited scoring or question email notification."""
    recipient_user_id: uuid.UUID
    kind: str = Field(pattern="^(scoring|question_answer)$")
    subject: str = Field(min_length=2, max_length=200)
    message: str = Field(min_length=2, max_length=10000)


class MailServerSettingsIn(BaseModel):
    """Represent administrator-entered SMTP and IMAP configuration."""
    smtp_host: str | None = Field(default=None, max_length=255)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = Field(default=None, max_length=255)
    smtp_password: str | None = Field(default=None, max_length=1024)
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    email_from: str | None = Field(default=None, max_length=320)
    support_email: str | None = Field(default=None, max_length=320)
    imap_host: str | None = Field(default=None, max_length=255)
    imap_port: int = Field(default=993, ge=1, le=65535)
    imap_username: str | None = Field(default=None, max_length=255)
    imap_password: str | None = Field(default=None, max_length=1024)
    imap_ssl: bool = True
    active: bool = True


class MailServerSettingsOut(BaseModel):
    """Return SMTP and IMAP configuration without exposing saved passwords."""
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password_set: bool
    smtp_starttls: bool
    smtp_ssl: bool
    email_from: str | None
    support_email: str | None
    imap_host: str | None
    imap_port: int
    imap_username: str | None
    imap_password_set: bool
    imap_ssl: bool
    active: bool
