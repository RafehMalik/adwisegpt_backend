from rest_framework.views import exception_handler
from rest_framework.exceptions import Throttled, NotFound, PermissionDenied, AuthenticationFailed, NotAuthenticated
from rest_framework import status
from user.utils import error_response


def custom_exception_handler(exc, context):
    # Let DRF handle it first to get the response object
    response = exception_handler(exc, context)

    if isinstance(exc, Throttled):
        return error_response(
            message=f"Rate limit exceeded. Try again in {int(exc.wait)} seconds.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    if isinstance(exc, NotAuthenticated):
        return error_response(
            message="Authentication required. Please log in.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # if isinstance(exc, AuthenticationFailed):
    #     return error_response(
    #         message="Invalid or expired token. Please log in again.",
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #     )

    if isinstance(exc, PermissionDenied):
        return error_response(
            message="You do not have permission to perform this action.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if isinstance(exc, NotFound):
        return error_response(
            message="The requested resource was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # Any other DRF exception (ValidationError, etc.) that DRF handled
    if response is not None:
        # Extract errors from DRF's response
        data = response.data
        if isinstance(data, dict) and "detail" in data:
            message = str(data["detail"])
            errors = None
        elif isinstance(data, dict):
            message = "Validation failed."
            errors = data
        elif isinstance(data, list):
            message = "Validation failed."
            errors = {"non_field_errors": data}
        else:
            message = str(data)
            errors = None

        return error_response(
            message=message,
            errors=errors,
            status_code=response.status_code,
        )

    # Unhandled exception (500) — DRF returned None
    return error_response(
        message="An unexpected server error occurred. Please try again later.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )