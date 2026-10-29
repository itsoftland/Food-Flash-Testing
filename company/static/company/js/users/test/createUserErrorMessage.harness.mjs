/**
 * Run: node createUserErrorMessage.harness.mjs
 */
import {
  DINE_FLASH_CREATE_USER_DUPLICATE_DISPLAY_MESSAGE,
  isDineFlashDuplicateUsernameApiError,
  resolveDineFlashCreateUserErrorMessage,
} from '../createUserErrorMessage.js';

function assert(condition, message) {
  if (!condition) {
    console.error('FAIL:', message);
    process.exit(1);
  }
}

const display = DINE_FLASH_CREATE_USER_DUPLICATE_DISPLAY_MESSAGE;

assert(
  isDineFlashDuplicateUsernameApiError({ non_field_errors: ['Username already exists.'] }),
  'non_field_errors duplicate'
);
assert(
  resolveDineFlashCreateUserErrorMessage({ non_field_errors: ['Username already exists.'] }) ===
    display,
  'non_field_errors maps to display message'
);

assert(
  isDineFlashDuplicateUsernameApiError(['Username already exists.']),
  'top-level array duplicate'
);
assert(
  resolveDineFlashCreateUserErrorMessage(['Username already exists.']) === display,
  'array maps to display message'
);

assert(
  !isDineFlashDuplicateUsernameApiError({ vendor_id: ['Selected outlet does not belong to your account.'] }),
  'vendor validation is not duplicate'
);
assert(
  resolveDineFlashCreateUserErrorMessage({ vendor_id: ['Selected outlet does not belong to your account.'] }) ===
    '',
  'vendor validation yields empty (generic fallback in UI)'
);

assert(
  !isDineFlashDuplicateUsernameApiError({ username: ['A user with this username already exists in this company.'] }),
  'hospital-style username key is not dine flash duplicate marker'
);

console.log('all assertions passed');
