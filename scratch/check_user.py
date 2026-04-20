import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'caller_on.settings')
sys.path.append(os.getcwd())
django.setup()

from django.contrib.auth.models import User
from vendors.models import UserProfile

username = 'james'
password = '123'

try:
    user = User.objects.get(username=username)
    print(f"User '{username}' found. Exact username in DB: '{user.username}'")
    print(f"Is active: {user.is_active}")
    print(f"Is staff: {user.is_staff}")
    print(f"Is superuser: {user.is_superuser}")
    
    from django.contrib.auth import authenticate
    auth_user = authenticate(username=username, password=password)
    if auth_user:
        print("Authentication SUCCESSFUL with password '123'")
    else:
        print("Authentication FAILED with password '123'")
        
    profiles = UserProfile.objects.filter(user=user)
    if profiles.exists():
        for profile in profiles:
            print(f"Profile found: Role={profile.role}, Name={profile.name}, Vendor={profile.vendor}")
    else:
        print("No UserProfile found for this user.")

except User.DoesNotExist:
    print(f"User '{username}' NOT found.")
except Exception as e:
    print(f"Error: {e}")
