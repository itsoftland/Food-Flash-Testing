# DineFlash - Software Requirements Specification (SRS)

## Document Information
- **Project Name:** DineFlash
- **Version:** 1.0
- **Date:** December 24, 2024
- **Prepared For:** Business Stakeholders

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [System Overview](#2-system-overview)
3. [User Roles](#3-user-roles)
4. [Feature Modules](#4-feature-modules)
   - 4.1 Dashboard
   - 4.2 Outlet Management
   - 4.3 Device Management
   - 4.4 Android TV Management
   - 4.5 TV Configuration
   - 4.6 Utilities Management
   - 4.7 User Management
   - 4.8 Advertisement & Banners
   - 4.9 Booking Management
5. [Customer-Facing Features](#5-customer-facing-features)
6. [Non-Functional Requirements](#6-non-functional-requirements)

---

## 1. Introduction

### 1.1 Purpose
DineFlash is a comprehensive restaurant table booking management system designed to streamline customer flow, display booking statuses on Android TVs, and provide real-time notifications to customers.

### 1.2 Scope
The system covers:
- Multi-outlet restaurant management
- Token-based management
- Android TV display integration
- Customer notifications via push notifications(web)
- Advertisement management
- Analytics and reporting
- Manager Apk

### 1.3 Target Audience
- Restaurant chains and food courts
- Healthcare facilities with waiting areas
- Service centers with token systems

---

## 2. System Overview

DineFlash consists of three main interfaces:

| Interface | Purpose | Users |
|-----------|---------|-------|
| Admin Portal | Multi-company management | Super Admin |
| Company Portal | Outlet and device management | Company Admin |
| Customer Interface | Token status tracking | End Customers |

---

## 3. User Roles

| Role | Access Level | Capabilities |
|------|--------------|--------------|
| Super Admin | Full System | Manage all companies, licenses |
| Company Admin | Company-wide | Manage outlets, devices, users |
| Outlet Manager | Single Outlet | View orders, manage tokens |
| Customer | Public | View token status, receive notifications |

---

## 4. Feature Modules

### 4.1 Dashboard
**Screen:** Company Dashboard

**Features:**
- Real-time order/token statistics
- Daily booking summary
- Quick access to all modules
- Key performance metrics

---

### 4.2 Outlet Management
**Screens:** Outlets List, Create Outlet, Update Outlet

**Features:**
- Create and manage restaurant outlets
- Configure outlet-specific settings:
  - Token display limit
  - Business day start hour
  - Timezone settings
  - Auto-delete hours for orders
  - MQTT/Firebase communication mode
- Assign MQTT server configuration
- Enable/disable features per outlet

---

### 4.3 Device Management

#### 4.3.1 Keypad Devices
**Screen:** Keypad Devices

**Features:**
- List all registered keypad devices
- Map devices to outlets
- Unmap devices from outlets
- View device status

#### 4.3.2 Manager Devices (Android APK)
**Screen:** Manager Devices

**Features:**
- List manager mobile devices
- Assign to specific outlets
- User assignment to devices

---

### 4.4 Android TV Management
**Screen:** Android TVs

**Features:**
- List all registered Android TV devices
- Map TVs to outlets
- Assign TV configurations to devices
- View current configuration status
- Filter by mapped/unmapped status

**Table Columns:**
| Column | Description |
|--------|-------------|
| MAC Address | Unique device identifier |
| Outlet Name | Assigned outlet |
| Configuration | Assigned config name |
| Created Time | Registration date |
| Actions | Link/Unlink outlet |

---

### 4.5 TV Configuration
**Screens:** Add Configuration, Configuration List

**Features:**
- Create named TV display configurations
- Configure display settings:
  - **Config Name:** Unique identifier
  - **Show QR Code:** Enable/disable QR display
  - **QR Alignment:** Left or Right
  - **Screen Orientation:** Portrait or Landscape
  - **Items to Show:** 1-5 bookings displayed
  - **Utility Name Mode:** Display Name or Display Code
  - **Booking Fields:** Name, Guest Count, Token
  - **Utilities:** Multi-select active utilities

**Actions:**
- View configuration details
- Edit configuration
- Delete configuration
- Assign to Android TVs

---

### 4.6 Utilities Management
**Screens:** Utilities List, Create Utility

**Features:**
- Create utility categories (e.g., Kitchen, Bar, VIP)
- Configure utility settings:
  - **Utility Name:** Internal identifier
  - **Display Name:** Customer-facing name
  - **Display Code:** Short code (e.g., KIT, BAR)
  - **Token Mode:** Continuous or Utility-Specific
  - **Prefix:** Token prefix (e.g., VIP-001)
- Activate/deactivate utilities
- Edit utility details

---

### 4.7 User Management
**Screens:** User List, Create User

**Features:**
- Create web and manager users
- Assign users to outlets
- Role-based access control:
  - Manager (Android APK)
  - Web User
- User activation/deactivation

---

### 4.8 Advertisement & Banners

#### 4.8.1 Banner Management
**Screen:** Banners

**Features:**
- Upload advertisement images
- Delete banners
- Image conversion for TV display

#### 4.8.2 Profile Management
**Screens:** New Profile, Profile List, Map Profiles, Mapped List

**Features:**
- Create advertisement profiles with:
  - Date range (start/end)
  - Active days (weekdays selection)
  - Priority level (1-5)
  - Time slots
- Assign profiles to outlets
- View profile assignments

---

### 4.9 Order Management
**Screens:** Total Orders, Order Details

**Features:**
- View all orders with filters
- Order timeline tracking
- Status history:
  - Preparing
  - Ready (customizable statuses)
  - Completed
- Order count summary by status
- Search and filter capabilities

---

## 5. Customer-Facing Features

### 5.1 Token Tracking
- Real-time token status display
- Push notifications on status change
- QR code scanning for status check

### 5.2 Table Booking
- Utility-based booking
- Guest count specification
- Phone number for notifications

### 5.3 Feedback System
- Submit complaints/suggestions/compliments
- Category selection (Dish/Service)
- Contact request option

---

## 6. Non-Functional Requirements

### 6.1 Performance
- Real-time updates via MQTT/Firebase
- Support for multiple concurrent TVs
- Fast page load times

### 6.2 Security
- JWT-based authentication
- CSRF protection
- Role-based access control

### 6.3 Scalability
- Multi-tenant architecture
- Multiple outlets per company
- Unlimited device support

### 6.4 Compatibility
- Modern web browsers (Chrome, Firefox, Safari, Edge)
- Android TV devices
- Android mobile devices (APK)
- iOS/Android web (PWA)

---

## Appendix A: Screen Index

| Module | Screen Name | URL Path |
|--------|-------------|----------|
| Dashboard | Company Dashboard | /company/dashboard/ |
| Outlets | Outlet List | /company/outlets/ |
| Outlets | Create Outlet | /company/create_outlet/ |
| Devices | Keypad Devices | /company/keypad_devices/ |
| Devices | Manager Devices | /company/manager_devices/ |
| Android TVs | TV List | /company/android_tvs/ |
| TV Config | Add Configuration | /company/android_tv_config/ |
| TV Config | Configuration List | /company/tv_config_list_page/ |
| Utilities | Utilities List | /company/utilities/ |
| Utilities | Create Utility | /company/create_utility/ |
| Users | User List | /company/user_list/ |
| Users | Create User | /company/create_users/ |
| Banners | Banner Management | /company/banners/ |
| Profiles | New Profile | /company/new_profile/ |
| Profiles | Profile List | /company/profile_list/ |
| Profiles | Map Profiles | /company/map_profiles/ |
| Orders | Total Orders | /company/total_orders/ |
| Orders | Order Details | /company/order_details/ |

---

**End of Document**
