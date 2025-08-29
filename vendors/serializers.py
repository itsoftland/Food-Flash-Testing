from rest_framework import serializers

from vendors.models import Order, UserProfile, ChatMessage

class OrdersSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source='vendor.name', read_only=True)
    manager_id = serializers.PrimaryKeyRelatedField(
        source='user_profile',
        queryset=UserProfile.objects.all(),
        required=False,
    )
    manager_name = serializers.CharField(source='user_profile.name', read_only=True)
    new_notifications = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = '__all__'
        extra_fields = ['vendor_name', 'manager_id', 'manager_name', 'new_notifications']

    def get_new_notifications(self, obj):
        return ChatMessage.objects.filter(
            vendor=obj.vendor,
            token_no=obj.token_no,
            created_date=obj.created_at.date(),
            sender='user',
            is_read=False
        ).count()

    def to_representation(self, instance):
        rep = super().to_representation(instance)

        rep['name'] = instance.vendor.name
        rep.pop('user_profile', None)
        
        return rep
