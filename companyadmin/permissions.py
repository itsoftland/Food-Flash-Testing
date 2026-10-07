from rest_framework.permissions import BasePermission


class IsSuperUser(BasePermission):
    """Super Admin only.

    Not DRF's IsAdminUser: that checks ``is_staff``, and Company Admins are ``is_staff=True``.
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_superuser)
