from django import forms
from .models import Vendor

class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class VendorFileUploadForm(forms.Form):
    vendor = forms.ModelChoiceField(queryset=Vendor.objects.all())
    
    ads_files = forms.FileField(
        widget=MultiFileInput(attrs={'multiple': True}),
        required=False
    )
    
    menus_files = forms.FileField(
        widget=MultiFileInput(attrs={'multiple': True}),
        required=False
    )