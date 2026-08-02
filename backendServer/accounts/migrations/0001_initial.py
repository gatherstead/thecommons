# Moves the identity/auth-bridge models (5 Better Auth mirrors + UserProfile
# + BusinessProfile) into their own app. state_operations only — no DDL runs.
# The physical tables (events_userprofile, events_businessprofile, and the
# neon_auth.* mirrors) are untouched; see the paired events move migration.

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("events", "0020_seed_monthly_digest_beat"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="BetterAuthUser",
                    fields=[
                        ("id", models.UUIDField(primary_key=True, serialize=False)),
                        ("name", models.TextField()),
                        ("email", models.EmailField(max_length=254, unique=True)),
                        (
                            "email_verified",
                            models.BooleanField(db_column="emailVerified", default=False),
                        ),
                        ("image", models.TextField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(db_column="createdAt")),
                        ("updated_at", models.DateTimeField(db_column="updatedAt")),
                        ("user_type", models.CharField(default="LOCAL", max_length=20)),
                    ],
                    options={
                        "db_table": 'neon_auth"."user',
                        "managed": False,
                    },
                ),
                migrations.CreateModel(
                    name="BetterAuthSession",
                    fields=[
                        ("id", models.TextField(primary_key=True, serialize=False)),
                        ("expires_at", models.DateTimeField(db_column="expiresAt")),
                        ("token", models.TextField(unique=True)),
                        ("created_at", models.DateTimeField(db_column="createdAt")),
                        ("updated_at", models.DateTimeField(db_column="updatedAt")),
                        (
                            "ip_address",
                            models.TextField(blank=True, db_column="ipAddress", null=True),
                        ),
                        (
                            "user_agent",
                            models.TextField(blank=True, db_column="userAgent", null=True),
                        ),
                        ("user_id", models.TextField(db_column="userId")),
                    ],
                    options={
                        "db_table": 'neon_auth"."session',
                        "managed": False,
                    },
                ),
                migrations.CreateModel(
                    name="BetterAuthAccount",
                    fields=[
                        ("id", models.TextField(primary_key=True, serialize=False)),
                        ("account_id", models.TextField(db_column="accountId")),
                        ("provider_id", models.TextField(db_column="providerId")),
                        ("user_id", models.UUIDField(db_column="userId")),
                        (
                            "access_token",
                            models.TextField(blank=True, db_column="accessToken", null=True),
                        ),
                        (
                            "refresh_token",
                            models.TextField(blank=True, db_column="refreshToken", null=True),
                        ),
                        ("id_token", models.TextField(blank=True, db_column="idToken", null=True)),
                        (
                            "access_token_expires_at",
                            models.DateTimeField(
                                blank=True, db_column="accessTokenExpiresAt", null=True
                            ),
                        ),
                        (
                            "refresh_token_expires_at",
                            models.DateTimeField(
                                blank=True, db_column="refreshTokenExpiresAt", null=True
                            ),
                        ),
                        ("scope", models.TextField(blank=True, null=True)),
                        ("password", models.TextField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(db_column="createdAt")),
                        ("updated_at", models.DateTimeField(db_column="updatedAt")),
                    ],
                    options={
                        "db_table": 'neon_auth"."account',
                        "managed": False,
                    },
                ),
                migrations.CreateModel(
                    name="BetterAuthVerification",
                    fields=[
                        ("id", models.TextField(primary_key=True, serialize=False)),
                        ("identifier", models.TextField()),
                        ("value", models.TextField()),
                        ("expires_at", models.DateTimeField(db_column="expiresAt")),
                        (
                            "created_at",
                            models.DateTimeField(blank=True, db_column="createdAt", null=True),
                        ),
                        (
                            "updated_at",
                            models.DateTimeField(blank=True, db_column="updatedAt", null=True),
                        ),
                    ],
                    options={
                        "db_table": 'neon_auth"."verification',
                        "managed": False,
                    },
                ),
                migrations.CreateModel(
                    name="BetterAuthJwks",
                    fields=[
                        ("id", models.TextField(primary_key=True, serialize=False)),
                        ("public_key", models.TextField(db_column="publicKey")),
                        ("private_key", models.TextField(db_column="privateKey")),
                        ("created_at", models.DateTimeField(db_column="createdAt")),
                    ],
                    options={
                        "db_table": 'neon_auth"."jwks',
                        "managed": False,
                    },
                ),
                migrations.CreateModel(
                    name="UserProfile",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "uuid",
                            models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                        ),
                        (
                            "user_type",
                            models.CharField(
                                choices=[
                                    ("LOCAL", "Local"),
                                    ("BUSINESS", "Business"),
                                    ("VENUE", "Venue"),
                                ],
                                default="LOCAL",
                                max_length=20,
                            ),
                        ),
                        ("primary_city", models.CharField(blank=True, max_length=100)),
                        ("address", models.CharField(blank=True, max_length=255)),
                        (
                            "email_preference",
                            models.CharField(
                                choices=[
                                    ("WEEKLY", "Weekly"),
                                    ("MONTHLY", "Monthly"),
                                    ("NEVER", "Never"),
                                ],
                                default="WEEKLY",
                                max_length=20,
                            ),
                        ),
                        (
                            "tags",
                            models.ManyToManyField(
                                blank=True, related_name="users", to="events.tag"
                            ),
                        ),
                        (
                            "user",
                            models.OneToOneField(
                                db_column="user_id",
                                db_constraint=False,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="profile",
                                to="accounts.betterauthuser",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "events_userprofile",
                    },
                ),
                migrations.CreateModel(
                    name="BusinessProfile",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        (
                            "uuid",
                            models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                        ),
                        ("business_name", models.CharField(max_length=200)),
                        ("description", models.TextField(blank=True)),
                        ("contact_email", models.EmailField(blank=True, max_length=254)),
                        ("contact_phone", models.CharField(blank=True, max_length=30)),
                        ("is_published", models.BooleanField(default=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "service_area",
                            models.ManyToManyField(
                                blank=True, related_name="businesses", to="events.town"
                            ),
                        ),
                        (
                            "tags",
                            models.ManyToManyField(
                                blank=True, related_name="businesses", to="events.tag"
                            ),
                        ),
                        (
                            "user",
                            models.OneToOneField(
                                db_column="user_id",
                                db_constraint=False,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="business_profile",
                                to="accounts.betterauthuser",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "events_businessprofile",
                    },
                ),
            ],
        ),
    ]
