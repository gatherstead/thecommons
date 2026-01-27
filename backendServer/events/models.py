import uuid
from django.db import models
from django.contrib.auth.models import User


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    # Link to the built-in User
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

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
        return f"{self.user.username}'s Profile"


class Event(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    title = models.CharField(max_length=200)
    
    town = models.CharField(max_length=100)
    
    date = models.DateTimeField() 
    
    #TODO: Github issue #2
    venue = models.CharField(max_length=200)
    
    description = models.TextField()
    
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    photo = models.ImageField(upload_to='event_photos/', null=True, blank=True)
    
    tags = models.ManyToManyField(Tag, related_name="events", blank=True)

    def __str__(self):
        return self.title
    

# Event: {
#    uuid: uuid,
#    city: String (Or could be enum)
#    date: date? (is this a data type?)
#    title: String,
#    venue?: {}
#    venueName:
#    description: String,
#    price: [double]
#    photo?: blob,
#    tags: [String],
# }

# User: {
#    uuid: uuid,
#    userType: enum, (Local, Business, or Venue)
#    name: String,
#    email: String,
#    password: String, (It will be encrypted)
#    primaryCity: String (could be an enum),
#    tags: [String],
#    emailPreference: enum, (Weekly, Monthly, Never)
# }




########
#USAGE
########
# 1. Get the Django User
# django_user = User.objects.get(username='alice')

# # 2. Access the standard auth stuff
# print(django_user.email) 
# print(django_user.check_password('some_password'))

# # 3. Access your custom fields using the reverse relationship
# print(django_user.profile.primary_city)
# print(django_user.profile.user_type)