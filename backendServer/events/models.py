import uuid
from django.db import models


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class Town(models.Model):
    slug = models.CharField(max_length=100, unique=True)  # e.g. 'carrboro'
    name = models.CharField(max_length=100)               # e.g. 'Carrboro'

    def __str__(self):
        return self.name


class BetterAuthUser(models.Model):
    """Read-only mirror of `neon_auth.user`. Better Auth (Next.js) owns writes.

    The `db_table` value uses deliberate double-quote injection so Django
    emits `FROM "neon_auth"."user"` — a valid cross-schema reference.
    """

    id = models.UUIDField(primary_key=True)
    name = models.TextField()
    email = models.EmailField(unique=True)
    email_verified = models.BooleanField(db_column='emailVerified', default=False)
    image = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(db_column='createdAt')
    updated_at = models.DateTimeField(db_column='updatedAt')
    user_type = models.CharField(max_length=20, default='LOCAL')

    # DRF permission classes read these attributes.
    is_authenticated = True
    is_anonymous = False

    class Meta:
        managed = False
        db_table = 'neon_auth"."user'

    def __str__(self):
        return self.email


class BetterAuthSession(models.Model):
    id = models.TextField(primary_key=True)
    expires_at = models.DateTimeField(db_column='expiresAt')
    token = models.TextField(unique=True)
    created_at = models.DateTimeField(db_column='createdAt')
    updated_at = models.DateTimeField(db_column='updatedAt')
    ip_address = models.TextField(db_column='ipAddress', null=True, blank=True)
    user_agent = models.TextField(db_column='userAgent', null=True, blank=True)
    user_id = models.TextField(db_column='userId')

    class Meta:
        managed = False
        db_table = 'neon_auth"."session'


class BetterAuthAccount(models.Model):
    id = models.TextField(primary_key=True)
    account_id = models.TextField(db_column='accountId')
    provider_id = models.TextField(db_column='providerId')
    user_id = models.TextField(db_column='userId')
    access_token = models.TextField(db_column='accessToken', null=True, blank=True)
    refresh_token = models.TextField(db_column='refreshToken', null=True, blank=True)
    id_token = models.TextField(db_column='idToken', null=True, blank=True)
    access_token_expires_at = models.DateTimeField(db_column='accessTokenExpiresAt', null=True, blank=True)
    refresh_token_expires_at = models.DateTimeField(db_column='refreshTokenExpiresAt', null=True, blank=True)
    scope = models.TextField(null=True, blank=True)
    password = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(db_column='createdAt')
    updated_at = models.DateTimeField(db_column='updatedAt')

    class Meta:
        managed = False
        db_table = 'neon_auth"."account'


class BetterAuthVerification(models.Model):
    id = models.TextField(primary_key=True)
    identifier = models.TextField()
    value = models.TextField()
    expires_at = models.DateTimeField(db_column='expiresAt')
    created_at = models.DateTimeField(db_column='createdAt', null=True, blank=True)
    updated_at = models.DateTimeField(db_column='updatedAt', null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'neon_auth"."verification'


class BetterAuthJwks(models.Model):
    id = models.TextField(primary_key=True)
    public_key = models.TextField(db_column='publicKey')
    private_key = models.TextField(db_column='privateKey')
    created_at = models.DateTimeField(db_column='createdAt')

    class Meta:
        managed = False
        db_table = 'neon_auth"."jwks'


class UserProfile(models.Model):
    user = models.OneToOneField(
        BetterAuthUser,
        on_delete=models.CASCADE,
        related_name='profile',
        db_column='user_id',
        db_constraint=False,
    )

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class UserType(models.TextChoices):
        LOCAL = 'LOCAL', 'Local'
        BUSINESS = 'BUSINESS', 'Business'
        VENUE = 'VENUE', 'Venue'

    user_type = models.CharField(
        max_length=20,
        choices=UserType.choices,
        default=UserType.LOCAL
    )

    primary_city = models.CharField(max_length=100, blank=True)

    class EmailFrequency(models.TextChoices):
        WEEKLY = 'WEEKLY', 'Weekly'
        MONTHLY = 'MONTHLY', 'Monthly'
        NEVER = 'NEVER', 'Never'

    email_preference = models.CharField(
        max_length=20,
        choices=EmailFrequency.choices,
        default=EmailFrequency.WEEKLY
    )

    tags = models.ManyToManyField(Tag, related_name="users", blank=True)

    def __str__(self):
        return f"{self.user.email}'s Profile"


class NewsletterSubscriber(models.Model):
    class Frequency(models.TextChoices):
        WEEKLY = 'WEEKLY', 'Weekly'
        MONTHLY = 'MONTHLY', 'Monthly'

    email = models.EmailField(unique=True)
    frequency = models.CharField(max_length=10, choices=Frequency.choices, default=Frequency.WEEKLY)
    is_active = models.BooleanField(default=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.email} ({self.frequency})"


class Event(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    title = models.CharField(max_length=200)

    town = models.ForeignKey('Town', null=True, blank=True, on_delete=models.SET_NULL, related_name='events')

    date = models.DateTimeField(db_index=True)

    venue = models.CharField(max_length=200)

    description = models.TextField()

    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    photo = models.ImageField(upload_to='event_photos/', null=True, blank=True)

    tags = models.ManyToManyField(Tag, related_name="events", blank=True)

    link = models.URLField(max_length=500, blank=True)

    is_verified = models.BooleanField(default=False)
    source_name = models.CharField(max_length=200, blank=True, default='')

    # Tracks who submitted this event; null for pipeline-ingested events.
    created_by = models.ForeignKey(
        'BetterAuthUser',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='created_events',
        db_constraint=False,
    )

    def __str__(self):
        return self.title
