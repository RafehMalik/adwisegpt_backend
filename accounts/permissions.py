from rest_framework.permissions import BasePermission

class IsAdvertiser(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and hasattr(user, "profile") and user.profile.role == "advertiser")

class IsNormalUser(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and hasattr(user, "profile") and user.profile.role == "user")

class IsRoleAssigned(BasePermission):
    """
    Blocks access if the user has not selected a role.
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if not hasattr(user, "profile"):
            return False
        return user.profile.role != "unassigned"
