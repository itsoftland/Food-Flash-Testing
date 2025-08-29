# utils/functions/validation.py

from functools import wraps
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)

def validate_required_fields(data, required_fields):
    missing_fields = [field for field in required_fields if not data.get(field)]
    if missing_fields:
        logger.warning(f"Missing required fields: {missing_fields}")
        return False, Response(
            {"message": f" Please Fill out the following fields: {', '.join(missing_fields)}"},
            status=status.HTTP_400_BAD_REQUEST
        )
    return True, None

def validate_fields(required_fields):
    """
    Decorator to validate required fields in request.data.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            is_valid, error_response = validate_required_fields(request.data, required_fields)
            if not is_valid:
                return error_response
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def check_unique_field(model, field_name, value, exclude_id=None):
    """
    Checks whether a field value is unique in the given model,
    optionally excluding a specific object by ID.
    """
    filter_kwargs = {f"{field_name}__iexact": value}
    queryset = model.objects.filter(**filter_kwargs)
    if exclude_id:
        queryset = queryset.exclude(id=exclude_id)
    return queryset.exists()
