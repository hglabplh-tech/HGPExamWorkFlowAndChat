# HGPExamWorkFlowAndChat effectiveness test report

This report is generated from the domain-specific text outputs created by the pytest effectiveness tests.

## ASAG scoring effectiveness

### Test description

Scores one intentionally strong answer and one intentionally weak answer for an Apple M3 microprocessor-programming question. The test verifies that the AI-assisted ASAG signals separate correct from incorrect answers, preserve deterministic expected values, keep fact and contradiction signals healthy, and complete within the configured latency budget.

### Metrics

| Metric | Value |
| --- | --- |
| accuracy | 1.0 |
| precision | 1.0 |
| recall | 1.0 |
| f1 | 1.0 |
| good_normalized_score | 0.909 |
| bad_normalized_score | 0.139875 |
| score_separation | 0.7691 |
| threshold | 0.6 |
| good_passed | True |
| bad_rejected | True |
| ai_cross_encoder_good | 0.96 |
| ai_cross_encoder_bad | 0.12 |
| ai_cross_encoder_margin | 0.84 |
| ai_embedding_good | 0.94 |
| ai_embedding_bad | 0.15 |
| ai_semantic_margin | 0.79 |
| ai_fact_coverage_good | 0.92 |
| ai_fact_coverage_bad | 0.1 |
| ai_fact_coverage_margin | 0.82 |
| ai_quality_gate_passed | True |
| hallucination_risk_bad_case | high |
| teacher_review_signal_active | False |
| max_absolute_error | 0.0 |
| exact_values_match_expected | True |
| latency_ms | 0.153 |
| answers_per_second | 13096.8 |
| latency_target_ms | 50 |
| meets_latency_target | True |
| performance_verdict | performant |

### Evidence details

| No. | Detail |
| --- | --- |
| 1 | good case score=9.09/10.0 normalized=0.909 signals={'cross_encoder': 0.96, 'embedding_similarity': 0.94, 'jaccard': 0.5, 'bm25': 1.0, 'context_match': 0.94, 'fact_coverage': 0.92, 'contradiction_safety': 0.98} |
| 2 | bad case score=1.399/10.0 normalized=0.139875 signals={'cross_encoder': 0.12, 'embedding_similarity': 0.15, 'jaccard': 0.09375, 'bm25': 0.25, 'context_match': 0.15, 'fact_coverage': 0.1, 'contradiction_safety': 0.3} |

## Hybrid search effectiveness

### Test description

Ranks a controlled knowledge corpus with BM25, full-text scores, and semantic scores. The test verifies that the relevant Apple M3 documents outrank an unrelated German-history distractor, that weighted fusion preserves the expected top results, and that retrieval latency remains below the target threshold.

### Metrics

| Metric | Value |
| --- | --- |
| top_result_relevant | True |
| precision_at_2 | 1.0 |
| recall_at_2 | 1.0 |
| mrr | 1.0 |
| ndcg_at_3 | 1.0 |
| exact_top_two_match_expected | True |
| ai_relevant_documents_in_top_2 | 2 |
| ai_irrelevant_distractor_retrieved | False |
| ai_grounded_source_coverage | 1.0 |
| ai_fusion_confidence_margin | 0.332902 |
| ai_semantic_channel_used | True |
| ai_bm25_channel_used | True |
| ai_full_text_channel_used | True |
| ai_ranking_quality_gate_passed | True |
| bm25_top_title | Apple M3 cache programming |
| hybrid_top_title | Apple M3 cache programming |
| latency_ms | 0.49 |
| documents_per_second | 6120.36 |
| latency_target_ms | 50 |
| meets_latency_target | True |
| performance_verdict | performant |

### Evidence details

| No. | Detail |
| --- | --- |
| 1 | query=Apple M3 unified memory cache programming |
| 2 | bm25_order=['Apple M3 cache programming', 'GPU memory concepts'] |
| 3 | hybrid_order=['Apple M3 cache programming', 'GPU memory concepts'] |
| 4 | hybrid_components=[{'full_text': 0.35, 'bm25': 0.2, 'semantic': 0.434831}, {'full_text': 0.160417, 'bm25': 0.041513, 'semantic': 0.45}] |

## Chatroom exchange workflow

### Test description

Simulates a course chatroom exchange between two students and the @chatbot assistant. The test verifies message delivery, chatbot addressing, visibility-limited sharing of ASAG scores and research results, payload integrity, and low-latency workflow execution.

### Metrics

| Metric | Value |
| --- | --- |
| messages_sent | 4 |
| student_a_received | 2 |
| student_b_received | 1 |
| chatbot_received | 1 |
| practice_score_shared | True |
| research_result_shared | True |
| delivery_accuracy | 1.0 |
| exact_delivery_match_expected | True |
| ai_chatbot_command_recognized | True |
| ai_chatbot_answered | True |
| ai_shared_payload_integrity | True |
| ai_visibility_gate_passed | True |
| ai_collaboration_quality_gate_passed | True |
| unauthorized_delivery_count | 0 |
| latency_ms | 0.007 |
| messages_per_second | 596214.0 |
| latency_target_ms | 50 |
| meets_latency_target | True |
| performance_verdict | performant |
| all_exchanges_successful | True |

### Evidence details

| No. | Detail |
| --- | --- |
| 1 | 1. student-a -> student-b: Please review my ASAG practice score. shared_type=practice_score |
| 2 | 2. student-b -> student-a: I see the score and suggest adding cache locality details. shared_type=None |
| 3 | 3. student-a -> @chatbot: @chatbot show research for M3 unified memory shared_type=research_result |
| 4 | 4. @chatbot -> student-a: Research received: Apple M3 course note is relevant. shared_type=research_result |
