"""Offline, non-confidential E5 relevance calibration for Stage 10.5."""

import sys
from pathlib import Path
from statistics import median

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.embedding_service import embed_passages, embed_query


EVALUATION_PAIRS = (
    ("positive", "What programming languages are listed in the resume?", "Languages: Python, Java. Frameworks: TensorFlow and PyTorch."),
    ("positive", "What technologies were used in the Responsible AI Risk Monitoring Platform?", "Responsible AI Risk Monitoring Platform used Python, Kafka, Kubernetes, and PostgreSQL."),
    ("positive", "What technologies were used in the Yoga Posture Detection project?", "Yoga Posture Detection project used Python, OpenCV, TensorFlow, and MediaPipe."),
    ("positive", "Project Falcon monitoring architecture", "Project Falcon provides event monitoring architecture and alerting."),
    ("negative", "quantum banana farming satellite recipe", "Software engineer experienced with Python, Java, PostgreSQL, and REST APIs."),
    ("negative", "easy cooking dinner recipe", "Responsible AI risk monitoring with Kafka and Kubernetes."),
    ("negative", "distant galaxy telescope astronomy", "Backend development using FastAPI, PostgreSQL, Git, and Docker."),
    ("negative", "medieval poetry garden irrigation", "Yoga posture detection using computer vision and TensorFlow."),
)


def main() -> None:
    passage_vectors = embed_passages([passage for _kind, _query, passage in EVALUATION_PAIRS])
    scores: list[tuple[str, float]] = []
    for (kind, query, _passage), passage_vector in zip(EVALUATION_PAIRS, passage_vectors, strict=True):
        query_vector = embed_query(query)
        scores.append((kind, sum(a * b for a, b in zip(query_vector, passage_vector, strict=True))))

    positives = [score for kind, score in scores if kind == "positive"]
    negatives = [score for kind, score in scores if kind == "negative"]
    print(f"min_positive={min(positives):.6f}")
    print(f"median_positive={median(positives):.6f}")
    print(f"max_negative={max(negatives):.6f}")
    print(f"median_negative={median(negatives):.6f}")


if __name__ == "__main__":
    main()
