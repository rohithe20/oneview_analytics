import sys

from app.core.db import SessionLocal
from app.seed.loader import SeedError, load_papers, load_questions, load_subjects, load_topics


def main() -> int:
    with SessionLocal() as db:
        try:
            subjects = load_subjects(db)
            topics = load_topics(db, subjects)
            papers = load_papers(db, subjects)
            load_questions(db, papers, topics)
        except SeedError as exc:
            db.rollback()
            print("Seed failed:\n", file=sys.stderr)
            print(exc, file=sys.stderr)
            return 1
        except Exception:
            db.rollback()
            raise

        db.commit()
        print(f"Seeded {len(subjects)} subject(s), {len(topics)} topic(s), {len(papers)} paper(s).")
        return 0


if __name__ == "__main__":
    sys.exit(main())
