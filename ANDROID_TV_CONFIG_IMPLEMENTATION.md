# Android TV Configuration Page - Complete Implementation

## Overview
A comprehensive Android TV Configuration page has been created with an 8-field form that allows users to configure QR code display, item display settings, booking field selections, and active utilities. The form is fully responsive and integrates with existing Django REST Framework APIs.

---

## ✅ Completed Components

### 1. **Frontend - Template** (`company/templates/company/android_tv_config.html`)
- **3-Section Form Layout**:
  1. **QR Code & Display** (3 columns):
     - Show QR Code (checkbox)
     - QR Alignment (left/right dropdown)
     - Screen Orientation (landscape/portrait dropdown)
  2. **Items Display Settings** (3 columns):
     - Items to Show (1-5 dropdown)
     - Utility Name Mode (display_name/display_code dropdown)
     - Fields to Display (name, guest_count, token checkboxes)
  3. **Active Utilities** (full-width):
     - Multi-select for active utilities from database

- **Responsive Design**:
  - Desktop: 3-column grid (col-lg-4)
  - Tablet: 2-column grid (col-md-6)
  - Mobile: Full-width stacked layout
  - Form sections with golden accent borders and clear headers

- **Form Actions**:
  - Save Configuration (golden button)
  - Reset (secondary button)
  - Both buttons fully styled and responsive

### 2. **Frontend - Styling** (`company/static/company/css/android_tv_config.css`)
- **Section Styling**:
  - Background color: light gray (#f8f9fa)
  - Left border accent: golden (#f0a934)
  - Section titles with underlines
  - Proper spacing for visual hierarchy

- **Form Elements**:
  - Consistent input/select styling with focus states
  - Multi-select support for utilities (min-height: 120px)
  - Checkbox styling with accent colors
  - Form helper text for multi-select instructions

- **Responsive Breakpoints**:
  - Mobile (≤480px): Single column, adjusted spacing
  - Tablet (≤768px): 2-column grid, optimized gaps
  - Desktop (>768px): 3-column grid, full spacing

- **Interactive States**:
  - Button hover effects with shadow and transform
  - Input focus states with golden outline
  - Disabled state styling for conditional fields

### 3. **Frontend - JavaScript** (`company/static/company/js/androidTvConfig.js`)
- **Utilities Loading**:
  - Fetches active utilities from `/company/api/get_utilities/`
  - Populates multi-select dropdown with utility names/codes
  - Handles both array and paginated response formats

- **Configuration Loading**:
  - Fetches existing TV config from `/company/api/tv_config_list/`
  - Gets first (most recent) config from the list
  - Falls back to sensible defaults if no config exists
  - Automatically repopulates form on reload/reset

- **Form Validation** (Client-side):
  - QR Alignment required if Show QR checked
  - Items to Show required (1-5 range)
  - Screen Orientation required
  - Utility Name Mode required
  - At least one utility must be selected
  - All validation errors shown in single alert

- **Form Submission**:
  - Posts to `/company/api/tv_config_create/`
  - Includes CSRF token from `window.AppUtils.getCSRFToken()`
  - Sends all 8 fields as JSON payload
  - Handles both success and error responses
  - Reloads configuration after successful save

- **Dynamic Field Control**:
  - QR Alignment dropdown disabled unless Show QR is checked
  - Reset button reloads saved configuration
  - Form state persists across page navigation

### 4. **Backend - API Integration** (`company/urls.py`)
- **Existing Endpoints**:
  - `POST /company/api/tv_config_create/` - Create/Update TV config
  - `GET /company/api/tv_config_list/` - List all configs for admin outlet
  - `GET /company/api/get_utilities/` - Fetch utilities for vendor

- **View Functions** (`company/views.py`):
  - `tv_config_create()` - Creates new TV config with duplicate checking
  - `tv_config_list()` - Returns all configs for authenticated user's outlet
  - Both use IsAuthenticated permission and check admin_outlet access

### 5. **Backend - Serializers** (`company/serializers.py`)
- **TVDeviceConfigSerializer**:
  - Fields: id, admin_outlet, show_qr, qr_alignment, items_to_show, booking_fields, utility_name_mode, screen_orientation, utilities, created_at, updated_at
  - Validates items_to_show: 1-5 (updated from 1-3)
  - Validates booking_fields: must be list with allowed values
  - Validates qr_alignment: required if show_qr is true
  - Validates utilities: belong to same admin_outlet

### 6. **Backend - Models** (`vendors/models.py`)
- **TVDeviceConfig Model**:
  - `show_qr` (BooleanField) - Whether to display QR code
  - `qr_alignment` (CharField) - "left" or "right"
  - `items_to_show` (PositiveSmallIntegerField) - 1-5 items to show
  - `booking_fields` (JSONField) - List of field names to display
  - `utility_name_mode` (CharField) - "display_name" or "display_code"
  - `screen_orientation` (CharField) - "portrait" or "landscape"
  - `utilities` (ManyToManyField) - Selected utilities
  - `admin_outlet` (ForeignKey) - Belongs to admin outlet
  - Auto-tracked: created_at, updated_at

### 7. **Navigation Integration** (`company/templates/company/layouts/base.html`)
- Added "Configuration" link under Android TV's menu section
- Proper active state detection for current page
- Menu hierarchy: Android TV's → Configuration

### 8. **API Endpoints Export** (`static/utils/js/apiEndpoints.js`)
- Added two new constants:
  - `CREATE_TV_CONFIG`: `${BASE}company/api/tv_config_create/`
  - `GET_TV_CONFIG`: `${BASE}company/api/tv_config_list/`

---

## 📋 Form Field Specifications

| Field | Type | Required | Options/Range | Notes |
|-------|------|----------|---|-------|
| Show QR Code | Checkbox | No | Yes/No | Conditional - enables alignment field |
| QR Alignment | Select | Yes (if QR enabled) | left, right | Disabled unless Show QR checked |
| Screen Orientation | Select | Yes | landscape, portrait | Defines display layout |
| Items to Show | Select | Yes | 1-5 | Number of bookings to display |
| Utility Name Mode | Select | Yes | display_name, display_code | How utility names appear |
| Fields to Display | Checkboxes | No | name, guest_count, token | Multi-select for booking card fields |
| Active Utilities | Multi-select | Yes | [loaded from DB] | Must select at least 1 utility |

---

## 🔌 API Request/Response Format

### Create/Update Configuration
**Endpoint:** `POST /company/api/tv_config_create/`

**Request Body:**
```json
{
  "show_qr": true,
  "qr_alignment": "right",
  "items_to_show": 3,
  "booking_fields": ["name", "guest_count"],
  "utility_name_mode": "display_name",
  "screen_orientation": "landscape",
  "utilities": [1, 2, 3]
}
```

**Response (Success):**
```json
{
  "message": "TV configuration created successfully.",
  "config": {
    "id": 1,
    "admin_outlet": 5,
    "show_qr": true,
    "qr_alignment": "right",
    "items_to_show": 3,
    "booking_fields": ["name", "guest_count"],
    "utility_name_mode": "display_name",
    "screen_orientation": "landscape",
    "utilities": [1, 2, 3],
    "created_at": "2025-01-01T10:30:00Z",
    "updated_at": "2025-01-01T10:30:00Z"
  }
}
```

### Fetch Utilities
**Endpoint:** `GET /company/api/get_utilities/`

**Response Format:**
```json
{
  "success": true,
  "utilities": [
    {
      "id": 1,
      "utility_name": "Queue",
      "display_name": "Queue Management",
      "display_code": "Q001",
      "is_active": true,
      "vendor": 5,
      "vendor_name": "Restaurant ABC"
    },
    ...
  ],
  "count": 5
}
```

### Fetch Configurations
**Endpoint:** `GET /company/api/tv_config_list/`

**Response Format:**
```json
{
  "configs": [
    {
      "id": 1,
      "admin_outlet": 5,
      "show_qr": true,
      "qr_alignment": "right",
      "items_to_show": 3,
      "booking_fields": ["name", "guest_count"],
      "utility_name_mode": "display_name",
      "screen_orientation": "landscape",
      "utilities": [1, 2, 3],
      "created_at": "2025-01-01T10:30:00Z"
    }
  ],
  "count": 1
}
```

---

## 🧪 Testing Checklist

- [ ] Form renders correctly on desktop/tablet/mobile
- [ ] Utilities dropdown populates with active utilities
- [ ] QR Alignment field disabled when Show QR unchecked
- [ ] Form validation triggers on submit
- [ ] Successful save shows success modal
- [ ] Failed save shows error modal
- [ ] Reset button reloads saved configuration
- [ ] All 8 fields submit correctly to API
- [ ] Configuration persists across page reloads
- [ ] Sidebar link navigates and shows active state
- [ ] Multi-select utilities works on desktop and mobile
- [ ] Responsive layout at all breakpoints (480px, 768px, 1024px)

---

## 📁 Files Modified/Created

### Created Files:
1. `company/templates/company/android_tv_config.html` - Main form template
2. `company/static/company/css/android_tv_config.css` - Complete styling
3. `company/static/company/js/androidTvConfig.js` - Form logic and API integration

### Modified Files:
1. `company/urls.py` - Already has routes (no changes needed)
2. `company/views.py` - Already has API views (no changes needed)
3. `company/serializers.py` - Updated items_to_show validation (1-5)
4. `company/templates/company/layouts/base.html` - Added sidebar link
5. `static/utils/js/apiEndpoints.js` - Added TV config endpoints
6. `vendors/models.py` - Model already exists (no changes needed)

---

## 🚀 Next Steps / Recommendations

1. **Test Form End-to-End**:
   - Navigate to Android TV → Configuration
   - Fill in all fields
   - Submit and verify API success

2. **Error Handling**:
   - Test with empty utilities list
   - Test with invalid utility IDs
   - Test with network errors

3. **Enhancement Ideas**:
   - Add support for "phone" and "datetime" booking fields if needed
   - Add edit/delete functionality for existing configurations
   - Add configuration preview/preview mode
   - Add audit logging for configuration changes
   - Add bulk configuration assignment to devices

4. **Performance Optimization**:
   - Add caching for utilities list
   - Implement pagination if utilities list grows large
   - Add debouncing for form changes

5. **Security**:
   - Verify CSRF token is properly validated
   - Test permission checks (admin_outlet isolation)
   - Verify no data leakage between outlets

---

## 🎨 Design Notes

- **Color Scheme**: Golden accent (#f0a934) for interactive elements
- **Spacing**: Consistent use of rem units for responsive scaling
- **Typography**: 0.875rem base font size for readability
- **Form Layout**: 3-column desktop → 2-column tablet → 1-column mobile
- **Form Sections**: Light gray backgrounds with golden left borders for visual separation

---

## 💡 Technical Details

- **Framework**: Django 3.x + Django REST Framework
- **Frontend**: ES6 modules, Vanilla JavaScript
- **Styling**: Bootstrap 5 grid + custom CSS
- **Authentication**: JWT via `fetchWithAutoRefresh()`
- **Authorization**: `@permission_classes([IsAuthenticated])` + admin_outlet validation
- **Database**: PostgreSQL (via Django ORM)

---

## 📚 Related Components

- **ModalService**: Used for success/error notifications
- **fetchWithAutoRefresh**: Handles authentication and auto-refresh tokens
- **AppUtils.getCSRFToken()**: Provides CSRF token for POST requests
- **AdminOutlet Model**: Ensures data isolation between users

---

Generated: 2025-01-01  
Status: ✅ Complete and Ready for Testing
