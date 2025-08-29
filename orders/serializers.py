from rest_framework import serializers
from vendors.models import Vendor, Feedback
import logging

logger = logging.getLogger(__name__)

class VendorLogoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ['id', 'name', 'logo','vendor_id','place_id']  # 'logo' should be an ImageField

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        try:
            if request and hasattr(instance.logo, 'url'):
                url = request.build_absolute_uri(instance.logo.url)
                data['logo_url'] = url.replace("http://", "https://")
            else:
                data['logo_url'] = ''
        except Exception as e:
            logger.warning(f"Error building logo URL: {e}")
            data['logo_url'] = ''
        
        data.pop('logo')  # Optional: remove raw logo field
        return data


class VendorAdsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ['vendor_id', 'ads', 'name']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')

        # Process JSON string of ads and convert to full URLs
        ad_paths = instance.get_ads_list()
        full_ad_urls = []

        if request:
            for path in ad_paths:
                if not path.startswith("http"):
                    url = request.build_absolute_uri(f"/media/{path}")
                    # Force HTTPS
                    full_ad_urls.append(url.replace("http://", "https://"))
                else:
                    full_ad_urls.append(path)

        data['ads'] = full_ad_urls
        return data


class VendorMenuSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ['vendor_id', 'menus', 'name']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')

        # Convert menu paths to full URLs
        menu_paths = instance.menus  # assuming this is a JSONField or TextField storing JSON
        if isinstance(menu_paths, str):
            import json
            menu_paths = json.loads(menu_paths)

        full_menu_urls = []
        if request:
            for path in menu_paths:
                if not path.startswith("http"):
                    url = request.build_absolute_uri(f"/media/{path}")
                    # Force HTTPS
                    full_menu_urls.append(url.replace("http://", "https://"))
                else:
                    full_menu_urls.append(path)

        data['menus'] = full_menu_urls
        return data


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = [
            'id',
            'vendor',
            'feedback_type',
            'category',
            'name',
            'comment',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

from rest_framework import serializers
from django.contrib.auth.models import User
from vendors.models import AdminOutlet

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'password']

    def create(self, validated_data):
        is_staff = self.context.get('is_staff', False)  # default False
        user = User(
            username=validated_data['username'],
            is_staff=is_staff,
            is_active=True
        )
        user.set_password(validated_data['password'])
        user.save()
        return user

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already exists.")
        return value


class AdminOutletSerializer(serializers.ModelSerializer):
    user = UserSerializer()

    class Meta:
        model = AdminOutlet
        fields = '__all__'

    def create(self, validated_data):
        user_data = validated_data.pop('user')
        user_serializer = UserSerializer(data=user_data, context={'is_staff': True})
        user_serializer.is_valid(raise_exception=True)
        user = user_serializer.save()
        admin_outlet = AdminOutlet.objects.create(user=user, **validated_data)
        return admin_outlet

