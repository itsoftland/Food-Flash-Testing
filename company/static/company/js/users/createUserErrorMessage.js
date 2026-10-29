/** Classic Dine Flash create-user API duplicate marker (backend text; do not change here). */
export const DINE_FLASH_CREATE_USER_DUPLICATE_API_MESSAGE = 'Username already exists.';

/** Company-admin modal copy for duplicate staff usernames within the same company. */
export const DINE_FLASH_CREATE_USER_DUPLICATE_DISPLAY_MESSAGE =
  'A user with this username already exists in this company.';

function payloadListsDuplicateMarker(values, marker) {
  return (
    Array.isArray(values) &&
    values.some((item) => item === marker || String(item) === marker)
  );
}

/**
 * True when the create-user API returned the known duplicate-username error shape
 * ({ non_field_errors: [...] } or top-level JSON array from IntegrityError fallback).
 */
export function isDineFlashDuplicateUsernameApiError(payload) {
  const marker = DINE_FLASH_CREATE_USER_DUPLICATE_API_MESSAGE;
  if (Array.isArray(payload)) {
    return payloadListsDuplicateMarker(payload, marker);
  }
  if (payload && typeof payload === 'object') {
    return payloadListsDuplicateMarker(payload.non_field_errors, marker);
  }
  return false;
}

/** Returns display message for duplicate username, or empty string for other errors. */
export function resolveDineFlashCreateUserErrorMessage(payload) {
  if (isDineFlashDuplicateUsernameApiError(payload)) {
    return DINE_FLASH_CREATE_USER_DUPLICATE_DISPLAY_MESSAGE;
  }
  return '';
}
