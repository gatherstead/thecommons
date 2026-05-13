from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0005_alter_event_date"),
    ]

    operations = [
        # Create the schema for Better Auth tables (managed by Next.js).
        migrations.RunSQL(
            sql="CREATE SCHEMA IF NOT EXISTS neon_auth;",
            reverse_sql=migrations.RunSQL.noop,
        ),

        # Throwaway dev data — previous (untracked) Django auth flow had
        # no production users.
        migrations.RunSQL(
            sql="TRUNCATE TABLE events_userprofile CASCADE;",
            reverse_sql=migrations.RunSQL.noop,
        ),

        # Register Better Auth tables in Django's migration state so the
        # UserProfile FK can resolve. `managed = False` means no DDL emitted.
        migrations.CreateModel(
            name="BetterAuthUser",
            fields=[
                ("id", models.TextField(primary_key=True, serialize=False)),
                ("name", models.TextField()),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("email_verified", models.BooleanField(db_column="emailVerified", default=False)),
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
                ("ip_address", models.TextField(blank=True, db_column="ipAddress", null=True)),
                ("user_agent", models.TextField(blank=True, db_column="userAgent", null=True)),
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
                ("user_id", models.TextField(db_column="userId")),
                ("access_token", models.TextField(blank=True, db_column="accessToken", null=True)),
                ("refresh_token", models.TextField(blank=True, db_column="refreshToken", null=True)),
                ("id_token", models.TextField(blank=True, db_column="idToken", null=True)),
                ("access_token_expires_at", models.DateTimeField(blank=True, db_column="accessTokenExpiresAt", null=True)),
                ("refresh_token_expires_at", models.DateTimeField(blank=True, db_column="refreshTokenExpiresAt", null=True)),
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
                ("created_at", models.DateTimeField(blank=True, db_column="createdAt", null=True)),
                ("updated_at", models.DateTimeField(blank=True, db_column="updatedAt", null=True)),
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

        # Swap UserProfile.user from auth.User (BIGINT) to BetterAuthUser (TEXT).
        # db_constraint=False because the target lives in neon_auth and Django
        # doesn't manage it — the relationship is logical, not enforced at DB level.
        migrations.RemoveField(
            model_name="userprofile",
            name="user",
        ),
        migrations.AddField(
            model_name="userprofile",
            name="user",
            field=models.OneToOneField(
                db_column="user_id",
                db_constraint=False,
                on_delete=models.deletion.CASCADE,
                related_name="profile",
                to="events.betterauthuser",
            ),
        ),
    ]
