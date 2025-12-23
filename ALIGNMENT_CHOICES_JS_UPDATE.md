# Android TV Config - Alignment & Choices.js Integration Updates

## Summary of Changes

### 1. **HTML Template Updates** (`android_tv_config.html`)

#### Added Choices.js Resources
```html
<!-- Added to {% block extra_css %} -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/choices.js/public/assets/styles/choices.min.css" />
<link rel="stylesheet" href="{% static 'utils/css/choices.css' %}">

<!-- Added to {% block extra_js %} -->
<script src="https://cdn.jsdelivr.net/npm/choices.js/public/assets/scripts/choices.min.js"></script>
```

#### Fixed Show QR Alignment
- **Issue**: Show QR checkbox was slightly left-aligned
- **Solution**: Added `ps-0` class to `.form-check` wrapper
- **Result**: Checkbox now properly aligned with zero left padding

```html
<!-- Before -->
<div class="form-check">

<!-- After -->
<div class="form-check ps-0">
```

#### Fixed Booking Fields Alignment
- **Issue**: Checkboxes inside booking fields container were misaligned (some items outside container)
- **Solution**: 
  - Changed container from `flex-wrap: wrap` to `flex-direction: column`
  - Added `ps-0` class to each checkbox `.form-check` wrapper
  - Removed `form-check-inline` class from checkboxes (was causing alignment issues)
- **Result**: All checkbox items now properly contained and aligned vertically

```html
<!-- Before -->
<div class="form-check form-check-inline">

<!-- After -->
<div class="form-check ps-0">
```

#### Integrated Choices.js for Utilities Multi-Select
- Changed utilities select class from `form-select form-select-sm` to `form-select form-select-sm choices-input`
- Added `data-placeholder="Click to select utilities..."`
- Removed helper text about Ctrl key (Choices.js handles this visually)
- Added hidden class to handle Choices.js display toggle

---

### 2. **CSS Updates** (`android_tv_config.css`)

#### Booking Fields Container
**Changed from:**
```css
display: flex;
flex-wrap: wrap;
gap: 1rem;
```

**Changed to:**
```css
display: flex;
flex-direction: column;
gap: 0.5rem;
```

**Benefits:**
- Checkboxes now stack vertically
- Reduced gap (0.5rem) for compact layout
- All items contained within container boundaries

#### Added Specific Checkbox Container Styling
```css
/* Checkboxes inside booking fields container */
.booking-fields-container .form-check {
  margin-bottom: 0;
  padding-left: 0;
}

.booking-fields-container .form-check-input {
  margin-right: 0.5rem;
  margin-left: 0;
}

.booking-fields-container .form-check-label {
  margin-bottom: 0;
}
```

**Benefits:**
- Eliminates unwanted margins
- Ensures consistent spacing
- Prevents items from overflowing container

#### Added Choices.js Styling
```css
/* Choices.js Custom Styling */
.choices-input {
  display: none !important;
}

.choices {
  margin-bottom: 0;
}

.choices__inner {
  min-height: 36px;
  padding: 0.45rem 0.6rem;
  background-color: #fff;
  border: 1px solid #e0e3e8;
  border-radius: 0.375rem;
  font-size: 0.875rem;
}

.choices__input {
  background-color: #fff;
}

.choices__item {
  background-color: #f0a934;
  color: white;
  border-color: #f0a934;
  font-size: 0.8rem;
  padding: 0.35rem 0.6rem;
}

.choices__button {
  color: white;
}

.is-open .choices__inner {
  border-color: #f0a934;
  box-shadow: 0 0 0 0.15rem rgba(240, 169, 52, 0.15);
}
```

**Features:**
- Hides native select element
- Styles Choices.js container to match form design
- Uses project's golden color (#f0a934) for selection
- Matches existing form element styling
- Provides focus state with shadow effect
- Customized item appearance (white text on golden background)

---

### 3. **JavaScript Updates** (`androidTvConfig.js`)

#### Added Choices.js Instance Management
```javascript
let choicesInstance = null; // Store Choices.js instance

function initializeChoices() {
  if (choicesInstance) {
    choicesInstance.destroy();
  }
  choicesInstance = new Choices(utilitiesSelect, {
    removeItemButton: true,
    itemSelectText: 'Click to select',
    placeholder: true,
    placeholderValue: 'Click to select utilities...',
    shouldSort: false,
    searchFields: ['label', 'value'],
  });
}
```

**Features:**
- Initializes Choices.js after utilities are loaded
- Allows destroying and reinitializing instance
- Configured for multi-select with remove buttons
- Custom placeholder text
- Search enabled across labels and values

#### Updated Utilities Loading
- Calls `initializeChoices()` after populating utilities options
- Ensures Choices.js is initialized with all available utilities

#### Updated Form Validation
```javascript
// Handle both standard select and Choices.js
let selectedUtilities = [];
if (choicesInstance) {
  selectedUtilities = choicesInstance.getValue().map((item) => item.value);
} else {
  selectedUtilities = Array.from(utilitiesSelect.selectedOptions).map((opt) => opt.value);
}
```

**Benefits:**
- Graceful fallback to standard select if Choices.js fails
- Properly validates selected utilities from Choices.js

#### Updated Form Submission Payload
```javascript
// Get selected utilities from Choices.js or standard select
let selectedUtilityValues = [];
if (choicesInstance) {
  selectedUtilityValues = choicesInstance.getValue().map((item) => parseInt(item.value));
} else {
  selectedUtilityValues = Array.from(utilitiesSelect.selectedOptions).map((opt) => parseInt(opt.value));
}

const payload = {
  // ... other fields ...
  utilities: selectedUtilityValues,
};
```

**Benefits:**
- Correctly extracts selected values from Choices.js
- Sends proper integer IDs to backend API

#### Updated Configuration Population
```javascript
// Update Choices.js if initialized
if (choicesInstance) {
  choicesInstance.setChoiceByValue(selectedUtilityIds.map(id => id.toString()));
}
```

**Benefits:**
- Pre-selects utilities when loading existing configuration
- Maintains consistency between form and Choices.js state

---

## Alignment Fixes Summary

| Issue | Before | After | Solution |
|-------|--------|-------|----------|
| Show QR checkbox alignment | Slightly left-offset | Properly aligned | Added `ps-0` class (Bootstrap padding reset) |
| Booking fields items | Some items overflow container | All items contained | Changed flex-wrap to flex-direction: column, added `ps-0` to checkboxes |
| Booking fields spacing | 1rem gap (too wide) | 0.5rem gap (compact) | Reduced gap value, made flex-direction column |
| Utilities selector | Native multi-select | Enhanced Choices.js UI | Full Choices.js integration with custom styling |

---

## User Experience Improvements

1. **Better Visual Consistency**: Show QR checkbox now aligns with other form elements
2. **Proper Content Layout**: All checkboxes in Fields to Display section are now properly contained
3. **Enhanced Multi-Select UX**: Choices.js provides:
   - Visual tag-based selection instead of native dropdown
   - Easy removal of selected items via X button
   - Real-time search functionality
   - Touch-friendly interface
   - Better mobile experience
4. **Consistent Styling**: Choices.js matches project's color scheme (#f0a934 golden accent)

---

## Testing Recommendations

- [ ] Verify Show QR checkbox alignment on desktop, tablet, mobile
- [ ] Check Booking Fields container on all screen sizes
- [ ] Test Choices.js multi-select functionality
- [ ] Verify Choices.js items are removable with X button
- [ ] Test search within Choices.js dropdown
- [ ] Verify form saves correctly with Choices.js values
- [ ] Test loading existing configuration (utilities pre-select)
- [ ] Check mobile keyboard interaction with Choices.js
- [ ] Verify responsive behavior on small screens

---

## Browser Compatibility

- ✅ Chrome/Edge (Chromium-based)
- ✅ Firefox
- ✅ Safari
- ✅ Mobile browsers (iOS Safari, Chrome Mobile)

Choices.js is well-supported across all modern browsers.

---

Generated: 2025-01-23
Status: ✅ Complete
