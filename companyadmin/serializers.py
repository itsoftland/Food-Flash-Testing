# companyadmin/api/serializers.py
from rest_framework import serializers
from vendors.models import Vendor

class VendorListSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='admin_outlet.customer_name', read_only=True)

    class Meta:
        model = Vendor
        fields = [
            'id',
            'name',
            'alias_name',
            'location',
            'company_name',
            'vendor_id',
        ]
