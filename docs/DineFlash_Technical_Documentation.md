# DineFlash - Technical Documentation

## Document Information
- **Project Name:** DineFlash
- **Version:** 1.0
- **Date:** December 24, 2024
- **Prepared For:** Developers

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Project Structure](#2-project-structure)
3. [Technology Stack](#3-technology-stack)
4. [Django Apps](#4-django-apps)
5. [Database Models](#5-database-models)
6. [API Reference](#6-api-reference)
7. [Frontend Structure](#7-frontend-structure)
8. [Authentication](#8-authentication)
9. [Real-Time Communication](#9-real-time-communication)
10. [Development Setup](#10-development-setup)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      DineFlash System                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Admin Web   │  │  Company Web │  │  Customer    │      │
│  │  Portal      │  │  Portal      │  │  PWA/Web     │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                 │                 │               │
│  ┌──────┴─────────────────┴─────────────────┴───────┐      │
│  │              Django REST API                      │      │
│  │         (JWT Authentication + CSRF)               │      │
│  └──────────────────────┬────────────────────────────┘      │
│                         │                                   │
│  ┌──────────────────────┼────────────────────────────┐      │
│  │                 PostgreSQL / SQLite               │      │
│  └───────────────────────────────────────────────────┘      │
│                                                             │
│  ┌───────────────────────────────────────────────────┐      │
│  │     MQTT / Firebase / Azure IoT (Real-time)       │      │
│  └───────────────────────────────────────────────────┘      │
│                         │                                   │
│  ┌──────────────────────┼────────────────────────────┐      │
│  │              Android TV Displays                  │      │
│  └───────────────────────────────────────────────────┘      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Project Structure

```
Food Flash Testing/
├── caller_on/              # Main Django project settings
│   ├── settings.py         # Django configuration
│   ├── urls.py             # Root URL configuration
│   └── wsgi.py             # WSGI entry point
│
├── company/                # Company admin portal
│   ├── views.py            # View functions & API endpoints
│   ├── serializers.py      # DRF serializers
│   ├── urls.py             # URL routing
│   ├── templates/          # HTML templates
│   └── static/             # CSS, JS, images
│
├── companyadmin/           # Super admin portal
│   ├── views.py
│   └── templates/
│
├── vendors/                # Core business logic
│   ├── models.py           # Database models
│   ├── views.py            # API endpoints
│   └── urls.py
│
├── orders/                 # Order processing
│   └── views.py
│
├── static/                 # Global static files
│   └── utils/              # Shared utilities
│       ├── js/
│       │   ├── apiEndpoints.js
│       │   └── services/
│       └── css/
│
├── requirements.txt        # Python dependencies
└── manage.py               # Django CLI
```

---

## 3. Technology Stack

| Layer | Technology |
|-------|------------|
| Backend | Django 4.x, Django REST Framework |
| Database | PostgreSQL / SQLite |
| Frontend | Vanilla JS (ES6 Modules), Bootstrap 5 |
| CSS | Custom CSS, Choices.js |
| Real-time | MQTT, Firebase Cloud Messaging, Azure IoT |
| Authentication | JWT (SimpleJWT), Session-based |
| Task Queue | Celery (optional) |

---

## 4. Django Apps

### 4.1 company (Company Portal)
Primary app for company-level management.

**Key Files:**
- `views.py` - 70+ view functions and API endpoints
- `serializers.py` - DRF serializers for all models
- `urls.py` - URL routing (73 patterns)

### 4.2 companyadmin (Super Admin)
Multi-tenant company management.

**Features:**
- Company registration
- License management
- Product authentication

### 4.3 vendors (Core Models)
Contains all database models.

**Key Models:**
- AdminOutlet, Vendor, VendorConfig
- Utility, TVDeviceConfig
- AndroidDevice, Device
- Order, OrderStatusHistory

### 4.4 orders
Order processing and analytics.

---

## 5. Database Models

### 5.1 Key Models

#### AdminOutlet
Top-level company entity.
```python
class AdminOutlet(models.Model):
    user = OneToOneField(User)
    customer_name = CharField(max_length=255)
    # License fields
    product_from_date, product_to_date
    web_login_count, android_tv_count, outlet_count
```

#### Vendor (Outlet)
Individual restaurant/outlet.
```python
class Vendor(models.Model):
    admin_outlet = ForeignKey(AdminOutlet)
    name = CharField(max_length=255)
    vendor_id = IntegerField(unique=True)
    location_id = CharField(max_length=20)
```

#### TVDeviceConfig
TV display configuration.
```python
class TVDeviceConfig(models.Model):
    admin_outlet = ForeignKey(AdminOutlet)
    config_name = CharField(max_length=255)
    show_qr = BooleanField(default=False)
    qr_alignment = CharField(choices=['left', 'right'])
    screen_orientation = CharField(choices=['portrait', 'landscape'])
    items_to_show = PositiveSmallIntegerField(default=1)
    booking_fields = JSONField(default=list)
    utility_name_mode = CharField(choices=['name', 'display_name', 'display_code'])
    utilities = ManyToManyField(Utility)
```

#### Utility
Service categories/counters.
```python
class Utility(models.Model):
    vendor = ForeignKey(Vendor)
    utility_name = CharField(max_length=100)
    display_name = CharField(max_length=100)
    display_code = CharField(max_length=10)
    token_mode = CharField(choices=['continuous', 'utility_specific'])
    prefix = CharField(max_length=4)
```

#### Order
Customer orders/tokens.
```python
class Order(models.Model):
    vendor = ForeignKey(Vendor)
    token_no = IntegerField()
    status = CharField(choices=STATUS_CHOICES)
    utility = ForeignKey(Utility)
    customer_name, no_of_packs, phone_number
```

---

## 6. API Reference

### 6.1 Authentication
```
POST /api/login/                    # JWT login
```

### 6.2 Company APIs
```
GET  /company/api/get_vendors/      # List outlets
POST /company/api/create_vendor/    # Create outlet
POST /company/api/update_vendor/    # Update outlet

GET  /company/api/get_android_tvs/  # List Android TVs
POST /company/api/map_android_tvs/<id>/    # Link TV to outlet
POST /company/api/unmap_android_tvs/<id>/  # Unlink TV

GET  /company/api/tv_config_list/           # List TV configs
POST /company/api/tv_config_create/         # Create config
GET  /company/api/tv_config_detail/<id>/    # Get config details
PATCH /company/api/tv_config_update/<id>/   # Update config
POST /company/api/tv_config_delete/<id>/    # Delete config
POST /company/api/tv_config_assign/         # Assign config to TV

GET  /company/api/get_utilities/            # List utilities
POST /company/api/create_utility/           # Create utility
POST /company/api/update_utility/           # Update utility
POST /company/api/update_utility_status/    # Toggle active

GET  /company/api/filtered_orders/          # List orders
GET  /company/api/order_counts_summary/     # Order statistics
```

### 6.3 Vendor APIs
```
POST /vendors/api/update-order/             # Update order status
GET  /vendors/api/list-order/               # List orders
POST /vendors/api/register_android_device/  # Register TV
```

---

## 7. Frontend Structure

### 7.1 JavaScript Architecture
```
company/static/company/js/
├── androidTvs.js              # Android TV management
├── androidTvConfig.js         # Add configuration page
├── androidtvs/
│   ├── tvConfigAssignment.js  # Config assignment modal
│   └── tv-config/
│       ├── tvConfigCore.js    # Config list logic
│       ├── tvConfigEdit.js    # Edit/View/Delete modals
│       └── tvConfigListManager.js  # Entry point

static/utils/js/
├── apiEndpoints.js            # API URL constants
└── services/
    ├── authFetchService.js    # JWT fetch wrapper
    ├── modalService.js        # Modal utilities
    └── confirmModalService.js # Confirmation dialogs
```

### 7.2 Key Patterns

**ES6 Module Imports:**
```javascript
import { fetchWithAutoRefresh } from './services/authFetchService.js';
import { API_ENDPOINTS } from './apiEndpoints.js';
import { ModalService } from './services/modalService.js';
```

**Context Pattern:**
```javascript
const ctx = {
  fetchWithAutoRefresh,
  apiEndpoints: API_ENDPOINTS,
  ModalService
};
openViewModal(configId, ctx);
```

---

## 8. Authentication

### 8.1 JWT Flow
1. Login → Receive access + refresh tokens
2. Store tokens in localStorage/cookies
3. Include access token in Authorization header
4. Auto-refresh on 401 response

### 8.2 CSRF Protection
- Django CSRF middleware enabled
- Token included in POST/PATCH/DELETE requests
- Retrieved via `AppUtils.getCSRFToken()`

---

## 9. Real-Time Communication

### 9.1 Communication Modes
| Mode | Use Case |
|------|----------|
| MQTT | Primary, low-latency updates |
| Firebase | Fallback, push notifications |
| Azure IoT | Enterprise deployments |

### 9.2 MQTT Topics
```
{vendor_id}/orders      # Order updates
{vendor_id}/tv/{mac}    # TV-specific updates
```

---

## 10. Development Setup

### 10.1 Prerequisites
- Python 3.10+
- PostgreSQL or SQLite
- Node.js (for asset compilation, optional)

### 10.2 Installation
```bash
# Clone repository
cd "Food Flash Testing"

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Database setup
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver
```

### 10.3 Environment Variables (.env)
```
DEBUG=True
SECRET_KEY=your-secret-key
DATABASE_URL=postgres://user:pass@localhost/dineflash
MQTT_HOST=mqtt.example.com
MQTT_PORT=1883
```

---

## Appendix: File Reference

| File | Purpose |
|------|---------|
| `company/serializers.py` | API serialization (TVDeviceConfigSerializer, AndroidDeviceSerializer, etc.) |
| `vendors/models.py` | All database models |
| `static/utils/js/apiEndpoints.js` | API URL constants |
| `company/views.py` | View functions and API handlers |

---

**End of Document**
