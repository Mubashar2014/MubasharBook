# Subscription Management System - Design Document

## 1. Overview

This design document outlines the architecture and implementation approach for transforming Mubashar's Book from a trial-based system to a full subscription management platform. The system will support optional trials, immediate subscriptions, payment integration, email verification, password reset, and comprehensive admin controls.

### 1.1 Design Goals

1. **Seamless Onboarding**: Users can choose between trial or immediate subscription
2. **Security First**: Email verification and password reset with secure token handling
3. **Payment Flexibility**: Support multiple Pakistani payment methods with automatic renewals
4. **Admin Control**: Complete user and subscription management capabilities
5. **Data Integrity**: Maintain existing multi-tenant architecture while adding subscription features
6. **Scalability**: Design for future growth and international expansion

### 1.2 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Optional Trial** | Market research shows some users prefer immediate subscription without trial period |
| **Email Verification Required** | Reduces fraud, ensures contact deliverability, industry standard |
| **Grace Period (3 days)** | Balances business needs with customer retention; allows payment issues resolution |
| **Read-Only During Grace** | Users retain data access, creates urgency without data loss fear |
| **JazzCash/EasyPaisa Primary** | Target Pakistani market first; 70%+ users prefer mobile wallets |
| **Status-Based Access Control** | Centralized subscription state machine prevents inconsistent access states |

---

## 2. Architecture Overview

### 2.1 System Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Flask Application                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │   Auth   │  │Subscription│ │  Admin   │  │  Email   │   │
│  │  Routes  │  │   Routes   │ │  Routes  │  │ Service  │   │
│  └─────┬────┘  └─────┬──────┘  └─────┬────┘  └────┬─────┘   │
│        │             │               │            │          │
│  ┌─────▼─────────────▼───────────────▼────────────▼─────┐   │
│  │              Business Logic Layer                     │   │
│  │  - SubscriptionManager  - PaymentHandler             │   │
│  │  - EmailService         - AccessControl              │   │
│  └───────────────────────┬───────────────────────────────┘   │
│                          │                                   │
│  ┌───────────────────────▼───────────────────────────────┐   │
│  │                   Data Layer (SQLAlchemy)             │   │
│  │  User | Subscription | Payment | EmailLog | AdminLog │   │
│  └───────────────────────┬───────────────────────────────┘   │
└────────────────────────────┼─────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   ┌────▼─────┐      ┌───────▼────────┐   ┌──────▼──────┐
   │ Database │      │ Payment Gateway │   │ Email SMTP  │
   │ (MySQL)  │      │ (JazzCash/     │   │ (SendGrid)  │
   └──────────┘      │  EasyPaisa)    │   └─────────────┘
                     └─────────────────┘
```

### 2.2 Technology Stack

- **Backend**: Flask 2.x + SQLAlchemy
- **Database**: MySQL (existing)
- **Email**: Flask-Mail + SendGrid/Mailgun
- **Payment**: JazzCash/EasyPaisa REST API (primary), Stripe (future)
- **Queue**: Python-RQ or Celery for async tasks (email, payment processing)
- **Security**: Flask-WTF CSRF, bcrypt password hashing, secure token generation

---

## 3. Data Model Design

### 3.1 Enhanced User Model

**Modifications to existing `User` model:**

```python
class User(UserMixin, db.Model):
    # Existing fields
    id = db.Column(db.Integer, primary_key=True)
    owner_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)  # NOW REQUIRED
    password_hash = db.Column(db.String(256), nullable=False)
    language = db.Column(db.String(5), default='ur')
    
    # New/Modified fields
