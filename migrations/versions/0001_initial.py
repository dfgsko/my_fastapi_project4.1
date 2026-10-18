"""initial tables: courses, students, enrollments

Revision ID: 0001
Revises:
Create Date: 2026-09-25

"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("instructor", sa.String(200), nullable=False),
        sa.Column("duration_hours", sa.Integer(), nullable=False),
    )
    op.create_index("ix_courses_title", "courses", ["title"])
    op.create_index("ix_courses_instructor", "courses", ["instructor"])

    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(200), nullable=False, unique=True),
    )
    op.create_index("ix_students_email", "students", ["email"], unique=True)

    op.create_table(
        "enrollments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "student_id",
            sa.Integer(),
            sa.ForeignKey("students.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "course_id",
            sa.Integer(),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enrollment_date", sa.DateTime(), nullable=False),
        sa.Column("grade", sa.Float(), nullable=True),
        # Статус хранится строкой (а не sa.Enum) для простоты работы с
        # SQLite; на уровне приложения используется app.enums.EnrollmentStatus.
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="in_progress"
        ),
        sa.Column("certificate_path", sa.String(500), nullable=True),
        sa.UniqueConstraint("student_id", "course_id", name="uq_student_course"),
    )
    op.create_index("ix_enrollments_student_id", "enrollments", ["student_id"])
    op.create_index("ix_enrollments_course_id", "enrollments", ["course_id"])


def downgrade() -> None:
    op.drop_table("enrollments")
    op.drop_table("students")
    op.drop_table("courses")
