"""аккаунты: роли client/moderator/admin, 2FA, email, профиль, возраст, сессии (лаб. № 8)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-06

"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("email", sa.String(254), nullable=True))
        b.add_column(sa.Column("password_changed_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("display_name", sa.String(60), nullable=True))
        b.add_column(sa.Column("avatar_url", sa.String(200), nullable=True))
        b.add_column(sa.Column("username_changed_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("totp_secret", sa.String(255), nullable=True))
        b.add_column(
            sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        b.add_column(sa.Column("totp_enabled_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("totp_last_timestep", sa.Integer(), nullable=True))
        b.add_column(sa.Column("totp_recovery_codes", sa.Text(), nullable=True))
        b.add_column(
            sa.Column("is_email_verified", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        b.add_column(sa.Column("email_verified_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("email_verification_token", sa.String(64), nullable=True))
        b.add_column(sa.Column("email_verification_sent_at", sa.DateTime(), nullable=True))
        b.add_column(
            sa.Column("is_age_verified", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        b.add_column(sa.Column("age_verified_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("minimum_age", sa.Integer(), nullable=True))
        b.add_column(
            sa.Column(
                "age_verification_required", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        b.alter_column("role", server_default="client")
        b.create_unique_constraint("uq_users_email", ["email"])
    op.create_index("ix_users_email_verification_token", "users", ["email_verification_token"])

    # Роль user из лаб. № 5 становится client. Существующие аккаунты уже
    # работали без подтверждения почты — считаем их подтверждёнными, иначе
    # после миграции никто не смог бы войти.
    op.execute("UPDATE users SET role = 'client' WHERE role = 'user'")
    op.execute("UPDATE users SET is_email_verified = true")
    # Email переносим из связанного студента (раньше он хранился только там).
    op.execute(
        "UPDATE users SET email = (SELECT s.email FROM students s WHERE s.id = users.student_id) "
        "WHERE student_id IS NOT NULL"
    )

    with op.batch_alter_table("refresh_tokens") as b:
        b.add_column(sa.Column("family_id", sa.String(64), nullable=True))
        b.add_column(sa.Column("user_agent", sa.String(200), nullable=True))
        b.add_column(sa.Column("ip_address", sa.String(64), nullable=True))
        b.add_column(sa.Column("session_started_at", sa.DateTime(), nullable=True))
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])

    op.create_table(
        "user_avatars",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False, server_default="image/webp"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    with op.batch_alter_table("courses") as b:
        b.add_column(sa.Column("min_age", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("courses") as b:
        b.drop_column("min_age")
    op.drop_table("user_avatars")
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    with op.batch_alter_table("refresh_tokens") as b:
        for col in ("session_started_at", "ip_address", "user_agent", "family_id"):
            b.drop_column(col)
    op.execute("UPDATE users SET role = 'user' WHERE role = 'client'")
    op.drop_index("ix_users_email_verification_token", table_name="users")
    with op.batch_alter_table("users") as b:
        b.drop_constraint("uq_users_email", type_="unique")
        b.alter_column("role", server_default="user")
        for col in (
            "age_verification_required", "minimum_age", "age_verified_at", "is_age_verified",
            "email_verification_sent_at", "email_verification_token", "email_verified_at",
            "is_email_verified", "totp_recovery_codes", "totp_last_timestep", "totp_enabled_at",
            "totp_enabled", "totp_secret", "username_changed_at", "avatar_url", "display_name",
            "password_changed_at", "email",
        ):
            b.drop_column(col)
