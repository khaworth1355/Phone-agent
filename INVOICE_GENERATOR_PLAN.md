# Invoice Generator from Call Transcripts

**Project Name**: Invoice Generator
**Version**: 1.0
**Date**: 2025-11-06
**Status**: Planning Phase

---

## 📋 Executive Summary

An intelligent invoice generation system that analyzes call transcripts from the Phone Agent system, extracts order information using Claude AI, validates addresses with UPS, calculates accurate shipping costs, and creates invoices in QuickBooks Online.

### Key Features
- 🤖 AI-powered data extraction from call transcripts
- 📦 Automatic UPS shipping rate calculation
- ✅ Address validation and correction
- 📊 Manual review workflow with pre-filled data
- 🔗 Direct QuickBooks Online integration
- 🚨 Error handling with admin notifications

---

## 🎯 Project Goals

1. **Reduce Manual Data Entry**: Extract customer and order information automatically from call transcripts
2. **Accurate Shipping Costs**: Get real-time UPS rates based on destination and package specs
3. **Quality Control**: Admin review step ensures accuracy before invoice creation
4. **Seamless Integration**: Use existing QuickBooks connection and phone agent database
5. **Error Handling**: Flag incomplete information for manual review

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Phone Agent Database                     │
│  (call_transcripts, call_routes, departments)               │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│              Invoice Generator System                        │
│                                                              │
│  ┌──────────────┐   ┌─────────────┐   ┌────────────────┐  │
│  │ Call Flagging│ → │   Claude    │ → │ Review Queue   │  │
│  │   Service    │   │  Extraction │   │  (Web UI)      │  │
│  └──────────────┘   └─────────────┘   └────────────────┘  │
│                                              │              │
│                                              ▼              │
│  ┌──────────────┐   ┌─────────────┐   ┌────────────────┐  │
│  │ QuickBooks   │ ← │     UPS     │ ← │  Admin         │  │
│  │  Invoice API │   │  Shipping   │   │  Approval      │  │
│  └──────────────┘   └─────────────┘   └────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 💻 Technology Stack

### Core Technologies
- **Backend**: Python 3.9+ with Flask or FastAPI
- **AI**: Anthropic Claude API (claude-3-sonnet or claude-3.5-sonnet)
- **Database**: PostgreSQL (same as phone-agent)
- **Frontend**: Simple HTML/CSS/JavaScript (or React for advanced UI)

### External APIs
- **QuickBooks Online API**: Invoice creation, customer management, product catalog
- **UPS API**: Address validation, rate calculation, residential detection
- **Phone Agent Database**: Read-only access to call transcripts

### Dependencies
```python
anthropic>=0.18.0
quickbooks-python>=0.9.0
ups-api>=1.0.0  # Or requests for direct API calls
flask>=2.3.0  # Or fastapi>=0.104.0
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0
pydantic>=2.0.0
python-dotenv>=1.0.0
```

---

## 📊 Data Flow

### 1. Call Flagging (Automatic)
```
Phone Agent DB → Scan new call_transcripts
                ↓
        Check for order keywords
                ↓
        Create flagged_calls entry
                ↓
        Notify admin (optional)
```

**Order Keywords**:
- order, purchase, buy, want to order, place an order
- detergent, TurboKlean, replacement part
- ship, deliver, send

### 2. Data Extraction (Claude AI)
```
Admin selects flagged call → Retrieve full transcript
                           ↓
                   Build Claude prompt
                           ↓
               Extract structured data:
                - Customer name
                - Phone number
                - Email (if mentioned)
                - Shipping address
                - Products & quantities
                - Special pricing notes
                - Shipping preference
                           ↓
               Return JSON structure
```

### 3. Address Validation (UPS API)
```
Extracted address → UPS Address Validation API
                  ↓
          Get standardized address
                  ↓
          Detect residential/commercial
                  ↓
          Return validated address + suggestions
```

### 4. Shipping Calculation (UPS API)
```
Validated address + Package specs → UPS Rating API
                                   ↓
                          Calculate for each service level:
                          - Ground
                          - 2nd Day Air
                          - Next Day Air
                                   ↓
                          Return rates + transit times
```

### 5. Admin Review
```
Display extracted data in web form
         ↓
Admin reviews/corrects
         ↓
Admin selects shipping method
         ↓
Admin approves
```

### 6. Invoice Creation (QuickBooks)
```
Approved data → Look up/create customer in QB
              ↓
          Look up products from QB catalog
              ↓
          Apply pricing (standard or custom)
              ↓
          Add shipping line item
              ↓
          Create invoice in QuickBooks
              ↓
          Return invoice URL
```

---

## 🗄️ Database Schema

### Option 1: Minimal (QuickBooks as source of truth)
No additional tables needed. Use phone-agent's existing tables:
- `call_transcripts` (read-only)
- `call_routes` (read-only)

Track flagged calls in-memory or simple JSON file.

### Option 2: Lightweight Tracking Table (Recommended)

```sql
CREATE TABLE invoice_queue (
    id SERIAL PRIMARY KEY,
    call_sid VARCHAR(100) UNIQUE NOT NULL,
    flagged_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(50) NOT NULL,  -- 'flagged', 'extracting', 'review', 'approved', 'invoiced', 'error'
    extracted_data JSONB,  -- Claude's extracted data
    validation_errors JSONB,  -- Issues found during extraction/validation
    qb_invoice_id VARCHAR(50),  -- QuickBooks invoice ID after creation
    qb_invoice_number VARCHAR(50),  -- Invoice number
    created_by VARCHAR(100),  -- Admin username
    processed_at TIMESTAMP,
    error_message TEXT,

    CONSTRAINT fk_call_sid FOREIGN KEY (call_sid)
        REFERENCES call_routes(call_sid)
);

CREATE INDEX idx_invoice_queue_status ON invoice_queue(status);
CREATE INDEX idx_invoice_queue_flagged_at ON invoice_queue(flagged_at);
```

**Status Flow**:
- `flagged` → Call identified with order keywords
- `extracting` → Claude is processing the transcript
- `review` → Awaiting admin review
- `approved` → Admin approved, ready for QB creation
- `invoiced` → Successfully created in QuickBooks
- `error` → Something went wrong, needs manual attention

---

## 🤖 Claude AI Extraction

### Extraction Prompt Template

```python
EXTRACTION_PROMPT = """
You are an expert at extracting order information from customer service call transcripts.

Analyze the following call transcript and extract ALL relevant order information into a structured JSON format.

TRANSCRIPT:
{transcript}

Extract the following information:

1. CUSTOMER INFORMATION:
   - Full name (as they stated it)
   - Phone number (format: +1XXXXXXXXXX)
   - Email address (if mentioned)

2. SHIPPING ADDRESS:
   - Street address (number + street name + unit/apt if applicable)
   - City
   - State (2-letter code if possible, full name is ok)
   - ZIP code (5 digits)
   - Address type: "residential" or "commercial" (infer from context)

3. PRODUCTS ORDERED:
   - Product name (e.g., "TurboKlean Detergent", "Replacement Part XYZ")
   - Quantity
   - Unit (e.g., "gallons", "units", "cases")
   - Any custom pricing mentioned (if different from standard)
   - SKU or product code if mentioned

4. SHIPPING PREFERENCES:
   - Speed preference: "standard", "expedited", "overnight", or "not specified"
   - Special instructions (e.g., "leave at back door", "call before delivery")

5. PAYMENT METHOD:
   - Method: "credit_card", "check", "invoice", "purchase_order"
   - PO number (if mentioned)

6. ADDITIONAL NOTES:
   - Any special requirements or circumstances
   - Follow-up needs
   - Price negotiations or discounts mentioned

IMPORTANT:
- Use "UNKNOWN" or null for any field not clearly stated in the transcript
- Be exact with addresses - do not guess or fill in information
- If multiple products are ordered, include all of them
- Mark your confidence level: "high", "medium", or "low" for each major section
- Flag any ambiguities or missing critical information

Return ONLY valid JSON in this exact format:
{
  "customer": {
    "name": "string or null",
    "phone": "string or null",
    "email": "string or null",
    "confidence": "high|medium|low"
  },
  "shipping_address": {
    "street": "string or null",
    "city": "string or null",
    "state": "string or null",
    "zip": "string or null",
    "address_type": "residential|commercial|unknown",
    "confidence": "high|medium|low"
  },
  "products": [
    {
      "name": "string",
      "quantity": number,
      "unit": "string",
      "custom_price": number or null,
      "sku": "string or null",
      "notes": "string or null"
    }
  ],
  "shipping": {
    "speed": "standard|expedited|overnight|not_specified",
    "special_instructions": "string or null"
  },
  "payment": {
    "method": "credit_card|check|invoice|purchase_order",
    "po_number": "string or null"
  },
  "notes": "string or null",
  "missing_info": ["list", "of", "missing", "fields"],
  "needs_review": boolean
}
"""

def extract_order_data(call_sid: str, transcript: str) -> dict:
    """Extract order information from transcript using Claude"""
    import anthropic

    client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

    prompt = EXTRACTION_PROMPT.format(transcript=transcript)

    message = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )

    # Parse JSON response
    import json
    response_text = message.content[0].text

    # Extract JSON from markdown code blocks if present
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    extracted_data = json.loads(response_text.strip())

    return extracted_data
```

---

## 📦 UPS Integration

### Address Validation

```python
import requests
from typing import Dict, List

class UPSClient:
    """UPS API client for address validation and shipping rates"""

    def __init__(self, client_id: str, client_secret: str, account_number: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.account_number = account_number
        self.base_url = "https://onlinetools.ups.com/api"
        self.access_token = None

    def authenticate(self):
        """Get OAuth access token"""
        url = "https://onlinetools.ups.com/security/v1/oauth/token"

        response = requests.post(
            url,
            auth=(self.client_id, self.client_secret),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={'grant_type': 'client_credentials'}
        )

        self.access_token = response.json()['access_token']
        return self.access_token

    def validate_address(self, address: dict) -> dict:
        """
        Validate and standardize address

        Args:
            address: {
                'street': '123 Main St',
                'city': 'Oklahoma City',
                'state': 'OK',
                'zip': '73102'
            }

        Returns:
            {
                'valid': True/False,
                'standardized_address': {...},
                'is_residential': True/False,
                'suggestions': [...] if not valid
            }
        """
        if not self.access_token:
            self.authenticate()

        url = f"{self.base_url}/addressvalidation/v1/1"

        payload = {
            "AddressValidationRequest": {
                "Request": {
                    "RequestOption": "3"  # Address Validation + Classification
                },
                "Address": {
                    "AddressLine": [address['street']],
                    "City": address['city'],
                    "StateProvinceCode": address['state'],
                    "PostalCode": address['zip'],
                    "CountryCode": "US"
                }
            }
        }

        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }

        response = requests.post(url, json=payload, headers=headers)
        data = response.json()

        # Parse response
        if 'AddressValidationResponse' in data:
            result = data['AddressValidationResponse']
            validated = result.get('ValidAddressIndicator') == ''

            standardized = result.get('Address', {})
            is_residential = result.get('AddressClassification', {}).get('Code') == '2'

            return {
                'valid': validated,
                'standardized_address': {
                    'street': standardized.get('AddressLine', [''])[0],
                    'city': standardized.get('City'),
                    'state': standardized.get('StateProvinceCode'),
                    'zip': standardized.get('PostalCode')
                },
                'is_residential': is_residential,
                'classification': 'Residential' if is_residential else 'Commercial'
            }

        return {'valid': False, 'error': 'Validation failed'}

    def get_shipping_rates(self,
                          from_address: dict,
                          to_address: dict,
                          packages: List[dict]) -> List[dict]:
        """
        Get shipping rates for multiple service levels

        Args:
            from_address: Origin address dict
            to_address: Destination address dict
            packages: [
                {
                    'weight': 5.0,  # pounds
                    'length': 12,   # inches
                    'width': 10,
                    'height': 8
                }
            ]

        Returns:
            [
                {
                    'service': 'Ground',
                    'service_code': '03',
                    'total_cost': 12.50,
                    'delivery_date': '2024-11-15',
                    'transit_days': 3
                },
                ...
            ]
        """
        if not self.access_token:
            self.authenticate()

        rates = []

        # UPS Service Codes
        services = {
            '03': 'Ground',
            '02': '2nd Day Air',
            '01': 'Next Day Air'
        }

        for service_code, service_name in services.items():
            url = f"{self.base_url}/rating/v1/rate"

            payload = {
                "RateRequest": {
                    "Request": {
                        "SubVersion": "1703"
                    },
                    "Shipment": {
                        "Shipper": {
                            "Address": {
                                "AddressLine": [from_address['street']],
                                "City": from_address['city'],
                                "StateProvinceCode": from_address['state'],
                                "PostalCode": from_address['zip'],
                                "CountryCode": "US"
                            },
                            "ShipperNumber": self.account_number
                        },
                        "ShipTo": {
                            "Address": {
                                "AddressLine": [to_address['street']],
                                "City": to_address['city'],
                                "StateProvinceCode": to_address['state'],
                                "PostalCode": to_address['zip'],
                                "CountryCode": "US"
                            }
                        },
                        "Service": {
                            "Code": service_code
                        },
                        "Package": [
                            {
                                "PackagingType": {
                                    "Code": "02"  # Customer Supplied Package
                                },
                                "Dimensions": {
                                    "UnitOfMeasurement": {
                                        "Code": "IN"
                                    },
                                    "Length": str(pkg['length']),
                                    "Width": str(pkg['width']),
                                    "Height": str(pkg['height'])
                                },
                                "PackageWeight": {
                                    "UnitOfMeasurement": {
                                        "Code": "LBS"
                                    },
                                    "Weight": str(pkg['weight'])
                                }
                            }
                            for pkg in packages
                        ]
                    }
                }
            }

            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }

            try:
                response = requests.post(url, json=payload, headers=headers)
                data = response.json()

                if 'RateResponse' in data:
                    rate_info = data['RateResponse']['RatedShipment']

                    rates.append({
                        'service': service_name,
                        'service_code': service_code,
                        'total_cost': float(rate_info['TotalCharges']['MonetaryValue']),
                        'currency': rate_info['TotalCharges']['CurrencyCode'],
                        'delivery_date': rate_info.get('DeliveryDate'),
                        'guaranteed': 'GuaranteedDelivery' in rate_info
                    })
            except Exception as e:
                print(f"Error getting rate for {service_name}: {e}")

        return sorted(rates, key=lambda x: x['total_cost'])
```

### Package Configuration

```python
# config/packages.py

PACKAGE_SPECS = {
    'detergent_5gal': {
        'name': 'TurboKlean 5 Gallon',
        'weight': 45.0,  # pounds
        'dimensions': {
            'length': 14,
            'width': 12,
            'height': 16
        },
        'qb_item_id': 'ITEM_ID_FROM_QB'
    },
    'detergent_1gal': {
        'name': 'TurboKlean 1 Gallon',
        'weight': 10.0,
        'dimensions': {
            'length': 8,
            'width': 6,
            'height': 10
        },
        'qb_item_id': 'ITEM_ID_FROM_QB'
    },
    'replacement_part_standard': {
        'name': 'Standard Replacement Part',
        'weight': 2.0,
        'dimensions': {
            'length': 6,
            'width': 6,
            'height': 4
        },
        'qb_item_id': 'ITEM_ID_FROM_QB'
    }
}

def get_package_specs(product_name: str, quantity: int) -> List[dict]:
    """
    Get package specifications for products
    Returns list of packages (may need multiple boxes for large orders)
    """
    # Normalize product name
    product_key = 'detergent_5gal'  # Default

    if '1 gallon' in product_name.lower() or '1gal' in product_name.lower():
        product_key = 'detergent_1gal'
    elif 'part' in product_name.lower():
        product_key = 'replacement_part_standard'

    spec = PACKAGE_SPECS[product_key]

    # Simple logic: 1 package per item for now
    # Could be enhanced to consolidate multiple items into fewer boxes
    packages = []
    for _ in range(quantity):
        packages.append({
            'weight': spec['weight'],
            'length': spec['dimensions']['length'],
            'width': spec['dimensions']['width'],
            'height': spec['dimensions']['height']
        })

    return packages
```

---

## 💼 QuickBooks Integration

### Invoice Creation

```python
from quickbooks import QuickBooks
from quickbooks.objects import Invoice, Customer, Item, Address
from datetime import datetime

class QuickBooksInvoiceManager:
    """Manage QuickBooks invoice creation"""

    def __init__(self, qb_client: QuickBooks):
        self.qb = qb_client

    def find_or_create_customer(self, customer_data: dict) -> Customer:
        """
        Find existing customer or create new one

        Args:
            customer_data: {
                'name': 'John Doe',
                'phone': '+18005551234',
                'email': 'john@example.com',
                'address': {...}
            }
        """
        # Search by phone number first
        phone = customer_data['phone'].replace('+1', '').replace('-', '').replace(' ', '')

        customers = Customer.query(
            f"SELECT * FROM Customer WHERE PrimaryPhone = '{phone}'",
            qb=self.qb
        )

        if customers:
            return customers[0]

        # Not found, create new customer
        customer = Customer()
        customer.DisplayName = customer_data['name']
        customer.PrimaryPhone = {'FreeFormNumber': customer_data['phone']}

        if customer_data.get('email'):
            customer.PrimaryEmailAddr = {'Address': customer_data['email']}

        # Shipping address
        if customer_data.get('address'):
            addr = customer_data['address']
            customer.ShipAddr = Address()
            customer.ShipAddr.Line1 = addr['street']
            customer.ShipAddr.City = addr['city']
            customer.ShipAddr.CountrySubDivisionCode = addr['state']
            customer.ShipAddr.PostalCode = addr['zip']

        customer.save(qb=self.qb)
        return customer

    def get_product_price(self, product_name: str) -> tuple:
        """
        Get product from QuickBooks catalog
        Returns: (item_object, price)
        """
        # Query QB for item matching product name
        items = Item.query(
            f"SELECT * FROM Item WHERE Name LIKE '%{product_name}%'",
            qb=self.qb
        )

        if items:
            item = items[0]
            price = float(item.UnitPrice) if hasattr(item, 'UnitPrice') else 0.0
            return item, price

        raise ValueError(f"Product '{product_name}' not found in QuickBooks")

    def create_invoice(self,
                      customer_data: dict,
                      products: List[dict],
                      shipping_cost: float,
                      notes: str = None) -> Invoice:
        """
        Create invoice in QuickBooks

        Args:
            customer_data: Customer information dict
            products: [
                {
                    'name': 'TurboKlean',
                    'quantity': 2,
                    'custom_price': 150.00 or None
                }
            ]
            shipping_cost: Total shipping cost from UPS
            notes: Optional notes for the invoice

        Returns:
            Created Invoice object
        """
        # Find or create customer
        customer = self.find_or_create_customer(customer_data)

        # Create invoice
        invoice = Invoice()
        invoice.CustomerRef = customer.to_ref()
        invoice.TxnDate = datetime.now().strftime('%Y-%m-%d')

        # Add product line items
        line_items = []
        line_num = 1

        for product in products:
            item, standard_price = self.get_product_price(product['name'])

            # Use custom price if negotiated, otherwise use QB standard price
            unit_price = product.get('custom_price') or standard_price

            line = {
                'LineNum': line_num,
                'DetailType': 'SalesItemLineDetail',
                'Amount': unit_price * product['quantity'],
                'SalesItemLineDetail': {
                    'ItemRef': {'value': item.Id},
                    'Qty': product['quantity'],
                    'UnitPrice': unit_price
                }
            }

            if product.get('notes'):
                line['Description'] = product['notes']

            line_items.append(line)
            line_num += 1

        # Add shipping line item
        if shipping_cost > 0:
            # Get or create shipping item in QB
            shipping_item = self._get_shipping_item()

            line_items.append({
                'LineNum': line_num,
                'DetailType': 'SalesItemLineDetail',
                'Amount': shipping_cost,
                'SalesItemLineDetail': {
                    'ItemRef': {'value': shipping_item.Id},
                    'Qty': 1,
                    'UnitPrice': shipping_cost
                },
                'Description': 'UPS Shipping'
            })

        invoice.Line = line_items

        if notes:
            invoice.CustomerMemo = {'value': notes}

        # Save invoice
        invoice.save(qb=self.qb)

        return invoice

    def _get_shipping_item(self) -> Item:
        """Get or create 'Shipping' service item in QuickBooks"""
        items = Item.query("SELECT * FROM Item WHERE Name = 'Shipping'", qb=self.qb)

        if items:
            return items[0]

        # Create shipping item
        item = Item()
        item.Name = "Shipping"
        item.Type = "Service"
        item.IncomeAccountRef = {'value': '1'}  # Update with actual income account
        item.save(qb=self.qb)

        return item
```

---

## 🌐 Web Interface Design

### Main Pages

#### 1. Dashboard (`/`)
- Shows flagged calls count
- Recent invoices created
- Calls needing review
- Quick stats (total invoices, total revenue this week)

#### 2. Flagged Calls (`/flagged-calls`)
```
┌─────────────────────────────────────────────────────────────┐
│ Flagged Calls Awaiting Processing                           │
├─────────────────────────────────────────────────────────────┤
│ Call Date    │ Caller Phone  │ Department │ Keywords        │
│ 2024-11-06   │ +18165551234 │ Sales      │ order, detergent│ [Process]
│ 2024-11-06   │ +14055559876 │ Sales      │ buy, shipping   │ [Process]
│ 2024-11-05   │ +19185554321 │ Sales      │ purchase, part  │ [Process]
└─────────────────────────────────────────────────────────────┘

[x] Auto-refresh every 30s    [ View Transcript ]  [ Skip ]
```

#### 3. Review & Approve (`/review/{call_sid}`)
```
┌─────────────────────────────────────────────────────────────┐
│ Invoice Review - Call CA1234567890abcdef                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ 📞 Call Information                                          │
│   Date: 2024-11-06 14:23:15                                 │
│   Duration: 3m 42s                                          │
│   Department: Sales                                         │
│   [ View Full Transcript ]                                  │
│                                                              │
│ 👤 Customer Information           [Confidence: High ✓]      │
│   Name:    [John Smith____________]                         │
│   Phone:   [+1 (816) 555-1234____]                         │
│   Email:   [john@example.com_____]                         │
│                                                              │
│ 📍 Shipping Address               [Confidence: Medium ⚠]    │
│   Street:  [123 Main Street______]  [ Validate Address ]   │
│   City:    [Oklahoma City________]                         │
│   State:   [OK] ZIP: [73102]                               │
│   Type:    ● Residential  ○ Commercial                      │
│                                                              │
│   ✓ Address Validated by UPS                                │
│   Suggested: 123 Main St, Oklahoma City, OK 73102          │
│                                                              │
│ 📦 Products Ordered               [Confidence: High ✓]      │
│   1. TurboKlean 5 Gallon                                   │
│      Quantity: [2] units                                    │
│      Price: [$150.00] each (Standard QB price: $150.00)    │
│                                                              │
│   2. Replacement Part XYZ                                   │
│      Quantity: [1] unit                                     │
│      Price: [$45.00] each (Standard QB price: $45.00)      │
│                                                              │
│   [ + Add Product ]                                         │
│                                                              │
│ 🚚 Shipping Options                                         │
│   ○ Ground (3-5 days) ............ $12.50                  │
│   ● 2nd Day Air (2 days) ......... $28.75  ← Selected     │
│   ○ Next Day Air (1 day) ......... $65.50                  │
│                                                              │
│   Package: 2 boxes, 90 lbs total                           │
│                                                              │
│ 💵 Invoice Summary                                          │
│   Subtotal (Products): ..... $345.00                       │
│   Shipping: ................. $28.75                        │
│   Tax: ...................... $0.00                         │
│   ─────────────────────────────────                         │
│   Total: .................... $373.75                       │
│                                                              │
│ 📝 Notes / Special Instructions                             │
│   [Leave package at back door___]                          │
│   [_________________________________]                        │
│                                                              │
│ ⚠️ Review Flags:                                            │
│   • Address confidence: MEDIUM (confirm with customer)      │
│                                                              │
│ [  Create Invoice in QuickBooks  ]  [ Save Draft ]  [ Cancel ]
└─────────────────────────────────────────────────────────────┘
```

#### 4. Success Page
```
✅ Invoice Created Successfully!

Invoice #: INV-1234
QuickBooks Link: [View in QuickBooks →]

Customer: John Smith
Total: $373.75
Status: Sent to customer

[ View Next Flagged Call ]  [ Back to Dashboard ]
```

---

## 🔧 Implementation Phases

### Phase 1: Foundation (Week 1)
**Goal**: Set up project structure and database access

- [ ] Create new Python project `invoice-generator`
- [ ] Set up virtual environment and dependencies
- [ ] Configure database connection to phone-agent DB (read-only)
- [ ] Create basic Flask/FastAPI app structure
- [ ] Test QB and UPS API connections
- [ ] Create configuration system (.env)

**Deliverable**: Working app skeleton that can read from phone-agent database

---

### Phase 2: Call Flagging System (Week 1-2)
**Goal**: Automatically identify calls that may need invoicing

**Components**:
```python
# call_flagging_service.py

class CallFlaggingService:
    def __init__(self, db_session):
        self.db = db_session

    def scan_new_calls(self, since_minutes=60):
        """
        Scan call transcripts from last N minutes for order keywords
        """
        # Query call_transcripts where:
        # - timestamp > now - since_minutes
        # - is_final = True
        # - speaker = 'caller' or 'ai'
        pass

    def check_order_keywords(self, transcript_text):
        """
        Check if transcript contains order-related keywords
        """
        ORDER_KEYWORDS = [
            'order', 'purchase', 'buy', 'want to order',
            'place an order', 'detergent', 'turboklean',
            'replacement part', 'ship', 'deliver'
        ]

        text_lower = transcript_text.lower()
        matches = [kw for kw in ORDER_KEYWORDS if kw in text_lower]

        return len(matches) >= 2  # Require at least 2 keyword matches

    def flag_call(self, call_sid):
        """
        Mark call as flagged for review
        """
        # Create entry in invoice_queue or in-memory store
        pass
```

**CLI Tool**:
```bash
# Run manually or via cron
python flag_calls.py --since-minutes 60
```

**Deliverable**: Service that identifies calls needing invoice review

---

### Phase 3: Claude Extraction Engine (Week 2)
**Goal**: Extract structured data from transcripts

**Components**:
- Claude prompt engineering (see earlier section)
- JSON parsing and validation
- Confidence scoring
- Error detection

```python
# extraction_service.py

class ExtractionService:
    def process_call(self, call_sid):
        """
        Extract order data from call transcript
        """
        # 1. Get full transcript from database
        transcript = self.get_call_transcript(call_sid)

        # 2. Call Claude API
        extracted_data = extract_order_data(call_sid, transcript)

        # 3. Validate extracted data
        validation_errors = self.validate_extraction(extracted_data)

        # 4. Update invoice_queue
        self.update_queue(call_sid, extracted_data, validation_errors)

        return extracted_data

    def validate_extraction(self, data):
        """Check for missing or invalid fields"""
        errors = []

        if not data['customer']['name']:
            errors.append('Missing customer name')

        if not data['shipping_address']['street']:
            errors.append('Missing shipping address')

        if not data['products']:
            errors.append('No products identified')

        return errors
```

**Testing**:
```python
# Test with sample transcripts
pytest tests/test_extraction.py
```

**Deliverable**: Reliable extraction with 80%+ accuracy

---

### Phase 4: UPS Integration (Week 2-3)
**Goal**: Validate addresses and calculate shipping

**Components**:
- UPS API client (see earlier section)
- Address validation
- Rate shopping
- Package dimension logic

```python
# shipping_service.py

class ShippingService:
    def __init__(self, ups_client):
        self.ups = ups_client

    def process_shipping(self, extracted_data):
        """
        Validate address and get shipping rates
        """
        address = extracted_data['shipping_address']
        products = extracted_data['products']

        # 1. Validate address
        validated = self.ups.validate_address(address)

        # 2. Get package specs
        packages = []
        for product in products:
            pkg_specs = get_package_specs(product['name'], product['quantity'])
            packages.extend(pkg_specs)

        # 3. Get rates
        origin = self.get_warehouse_address()
        rates = self.ups.get_shipping_rates(origin, validated['standardized_address'], packages)

        return {
            'validated_address': validated,
            'shipping_rates': rates,
            'packages': packages
        }
```

**Deliverable**: Working UPS address validation and rate calculation

---

### Phase 5: QuickBooks Invoice Creation (Week 3)
**Goal**: Create invoices in QB with validated data

**Components**:
- QuickBooks client (see earlier section)
- Customer lookup/creation
- Product catalog integration
- Invoice generation
- Price validation (QB catalog vs. negotiated)

```python
# invoice_service.py

class InvoiceCreationService:
    def __init__(self, qb_client, qb_invoice_manager):
        self.qb = qb_client
        self.invoice_mgr = qb_invoice_manager

    def create_invoice_from_review(self, reviewed_data):
        """
        Create QB invoice from admin-reviewed data
        """
        # 1. Prepare customer data
        customer_data = {
            'name': reviewed_data['customer']['name'],
            'phone': reviewed_data['customer']['phone'],
            'email': reviewed_data['customer'].get('email'),
            'address': reviewed_data['shipping_address']
        }

        # 2. Prepare products
        products = reviewed_data['products']

        # 3. Add selected shipping
        shipping_cost = reviewed_data['selected_shipping']['total_cost']

        # 4. Create invoice
        invoice = self.invoice_mgr.create_invoice(
            customer_data,
            products,
            shipping_cost,
            notes=reviewed_data.get('notes')
        )

        # 5. Update invoice_queue
        self.update_queue_with_invoice(
            reviewed_data['call_sid'],
            invoice.Id,
            invoice.DocNumber
        )

        return invoice
```

**Deliverable**: Functional invoice creation in QuickBooks

---

### Phase 6: Web Interface (Week 3-4)
**Goal**: Admin UI for review and approval

**Pages**:
1. Dashboard - Overview
2. Flagged Calls List
3. Review Form (main interface)
4. Success/Error pages

**Technology**:
- Option A: Simple Flask + Jinja2 templates + Bootstrap
- Option B: FastAPI + React (more modern but more complex)
- Option C: Streamlit (quickest prototype)

**Features**:
- Display extracted data in editable form
- Address validation with suggestions
- Shipping rate selection
- Product editing (add/remove/modify)
- Real-time total calculation
- "Create Invoice" button
- Error handling and validation

**Deliverable**: Functional web UI for invoice review

---

### Phase 7: Error Handling & Notifications (Week 4)
**Goal**: Handle edge cases and notify admins

**Components**:
1. **Error Detection**:
   - Missing customer info
   - Invalid addresses
   - Product not in QB catalog
   - UPS API failures
   - QB API failures

2. **Notification System**:
   - Email alerts for failed extractions
   - Slack/Discord webhook for new flagged calls
   - Summary reports (daily/weekly)

3. **Retry Logic**:
   - Automatic retry for transient failures
   - Manual retry for permanent failures

```python
# notification_service.py

class NotificationService:
    def send_extraction_failed(self, call_sid, errors):
        """Email admin about failed extraction"""
        pass

    def send_new_flagged_calls(self, count):
        """Notify admin of new calls needing review"""
        pass

    def send_invoice_created(self, invoice_number, customer_name, total):
        """Confirmation email/notification"""
        pass
```

**Deliverable**: Robust error handling and admin notifications

---

## 📝 API Endpoints

### GET `/api/flagged-calls`
List all calls flagged for invoice processing

**Response**:
```json
{
  "calls": [
    {
      "call_sid": "CA123...",
      "flagged_at": "2024-11-06T14:30:00Z",
      "caller_phone": "+18165551234",
      "department": "Sales",
      "keywords_matched": ["order", "detergent"],
      "status": "flagged"
    }
  ],
  "total": 5,
  "pending_review": 3
}
```

---

### POST `/api/extract/{call_sid}`
Extract order data from call transcript

**Response**:
```json
{
  "success": true,
  "call_sid": "CA123...",
  "extracted_data": {
    "customer": {...},
    "shipping_address": {...},
    "products": [...],
    "confidence": {
      "customer": "high",
      "address": "medium",
      "products": "high"
    }
  },
  "validation_errors": [],
  "needs_review": false
}
```

---

### POST `/api/validate-address`
Validate address via UPS

**Request**:
```json
{
  "street": "123 Main St",
  "city": "Oklahoma City",
  "state": "OK",
  "zip": "73102"
}
```

**Response**:
```json
{
  "valid": true,
  "standardized_address": {
    "street": "123 Main St",
    "city": "Oklahoma City",
    "state": "OK",
    "zip": "73102"
  },
  "is_residential": true,
  "classification": "Residential"
}
```

---

### POST `/api/calculate-shipping`
Get UPS shipping rates

**Request**:
```json
{
  "destination": {
    "street": "123 Main St",
    "city": "Oklahoma City",
    "state": "OK",
    "zip": "73102"
  },
  "products": [
    {"name": "TurboKlean 5 Gallon", "quantity": 2}
  ]
}
```

**Response**:
```json
{
  "rates": [
    {
      "service": "Ground",
      "service_code": "03",
      "total_cost": 12.50,
      "delivery_date": "2024-11-15",
      "transit_days": 3
    },
    {
      "service": "2nd Day Air",
      "service_code": "02",
      "total_cost": 28.75,
      "delivery_date": "2024-11-13"
    }
  ],
  "packages": [
    {"weight": 45, "length": 14, "width": 12, "height": 16}
  ]
}
```

---

### POST `/api/create-invoice`
Create invoice in QuickBooks

**Request**:
```json
{
  "call_sid": "CA123...",
  "customer": {
    "name": "John Smith",
    "phone": "+18165551234",
    "email": "john@example.com",
    "address": {...}
  },
  "products": [
    {
      "name": "TurboKlean 5 Gallon",
      "quantity": 2,
      "custom_price": null
    }
  ],
  "shipping": {
    "service": "2nd Day Air",
    "cost": 28.75
  },
  "notes": "Leave at back door"
}
```

**Response**:
```json
{
  "success": true,
  "invoice_id": "123",
  "invoice_number": "INV-1234",
  "quickbooks_url": "https://qbo.intuit.com/...",
  "total": 373.75,
  "customer_id": "456"
}
```

---

## 🔐 Security Considerations

### Authentication
- Admin-only access (HTTP Basic Auth or JWT)
- API key authentication for external calls (if any)
- Secure credential storage (environment variables)

### Data Protection
- Read-only database access for phone-agent DB
- Encrypt API credentials (QB, UPS)
- No storage of credit card info (QB handles payments)
- HTTPS only in production

### Access Control
- Separate environments (dev, staging, prod)
- IP whitelisting for admin panel
- Audit log of invoice creations
- Rate limiting on API endpoints

---

## 📊 Monitoring & Analytics

### Metrics to Track
- Calls flagged per day
- Extraction success rate
- Avg review time per invoice
- Invoices created per day
- Total revenue processed
- Address validation rate
- Shipping cost trends

### Logging
```python
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('invoice_generator.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Example usage
logger.info(f"Flagged call {call_sid} with keywords: {keywords}")
logger.warning(f"Address validation failed for {call_sid}")
logger.error(f"Invoice creation failed: {error}")
```

---

## 🧪 Testing Strategy

### Unit Tests
```python
# tests/test_extraction.py
def test_extract_customer_info():
    transcript = "My name is John Smith and my phone is 816-555-1234"
    result = extract_order_data("TEST123", transcript)
    assert result['customer']['name'] == 'John Smith'
    assert '+18165551234' in result['customer']['phone']

# tests/test_ups.py
def test_address_validation():
    address = {
        'street': '123 Main St',
        'city': 'Oklahoma City',
        'state': 'OK',
        'zip': '73102'
    }
    result = ups_client.validate_address(address)
    assert result['valid'] == True
```

### Integration Tests
```python
# tests/test_integration.py
def test_full_workflow():
    # 1. Flag call
    # 2. Extract data
    # 3. Validate address
    # 4. Get shipping rates
    # 5. Create invoice
    pass
```

### Manual Testing Checklist
- [ ] Flag call with order keywords
- [ ] Extract data with high confidence
- [ ] Extract data with missing info (error handling)
- [ ] Validate correct address
- [ ] Validate incorrect address (get suggestions)
- [ ] Calculate shipping for residential
- [ ] Calculate shipping for commercial
- [ ] Create invoice with standard pricing
- [ ] Create invoice with custom pricing
- [ ] Handle QB customer already exists
- [ ] Handle new QB customer creation
- [ ] Handle UPS API failure
- [ ] Handle QB API failure

---

## 🚀 Deployment

### Environment Variables

```bash
# .env file

# Database (read-only access to phone-agent DB)
DATABASE_URL=postgresql://user:pass@host:port/dbname

# Claude AI
ANTHROPIC_API_KEY=sk-ant-...

# QuickBooks (reuse from phone-agent)
QUICKBOOKS_CLIENT_ID=...
QUICKBOOKS_CLIENT_SECRET=...
QUICKBOOKS_REALM_ID=...
QUICKBOOKS_REFRESH_TOKEN=...

# UPS API
UPS_CLIENT_ID=...
UPS_CLIENT_SECRET=...
UPS_ACCOUNT_NUMBER=...

# Warehouse Address (for shipping origin)
WAREHOUSE_STREET=...
WAREHOUSE_CITY=...
WAREHOUSE_STATE=...
WAREHOUSE_ZIP=...

# Notifications
NOTIFICATION_EMAIL=admin@temco.com
SLACK_WEBHOOK_URL=https://hooks.slack.com/...

# Admin Auth
ADMIN_USERNAME=admin
ADMIN_PASSWORD=...

# App Settings
FLASK_ENV=production
PORT=8000
```

### Production Setup (DigitalOcean Droplet)

```bash
# 1. Clone repo
git clone https://github.com/your-org/invoice-generator.git
cd invoice-generator

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
nano .env  # Add your credentials

# 5. Run database migrations (if using invoice_queue table)
python migrations/create_tables.py

# 6. Test connections
python test_connections.py

# 7. Run with gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 app:app

# 8. Set up systemd service
sudo nano /etc/systemd/system/invoice-generator.service
```

**systemd service file**:
```ini
[Unit]
Description=Invoice Generator Service
After=network.target

[Service]
Type=simple
User=invoiceagent
WorkingDirectory=/opt/invoice-generator
Environment="PATH=/opt/invoice-generator/venv/bin"
ExecStart=/opt/invoice-generator/venv/bin/gunicorn -w 4 -b 127.0.0.1:8000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start service
sudo systemctl enable invoice-generator
sudo systemctl start invoice-generator
sudo systemctl status invoice-generator
```

### Nginx Configuration

```nginx
# /etc/nginx/sites-available/invoice-generator

server {
    listen 443 ssl;
    server_name invoices.chevroletsneezington.com;

    ssl_certificate /etc/letsencrypt/live/chevroletsneezington.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/chevroletsneezington.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 📚 Additional Resources

### Documentation to Reference
- [UPS Developer Portal](https://developer.ups.com/)
- [QuickBooks API Docs](https://developer.intuit.com/app/developer/qbo/docs/get-started)
- [Anthropic Claude API](https://docs.anthropic.com/claude/reference/getting-started-with-the-api)
- Phone Agent Database Schema (see current project)

### Similar Projects / Examples
- Zapier QuickBooks Integrations
- UPS Shipping Calculators
- AI Data Extraction tools

### Future Enhancements
- **Automatic processing**: Skip review for high-confidence extractions
- **Batch processing**: Process multiple calls at once
- **Smart learning**: Train on corrected extractions to improve accuracy
- **Email invoices**: Send directly to customers via QB
- **Tracking numbers**: Update invoices with UPS tracking when shipped
- **Custom workflows**: Different flows for different product types
- **Mobile app**: iOS/Android app for on-the-go approvals
- **Voice confirmation**: Call customer to confirm order before invoicing
- **Inventory tracking**: Check stock before creating invoice
- **Multi-language**: Support for Spanish-speaking customers

---

## ✅ Success Criteria

The project will be considered successful when:

1. ✅ **85%+ extraction accuracy** - Claude correctly extracts customer info from transcripts
2. ✅ **100% address validation** - All addresses validated through UPS before invoicing
3. ✅ **<5 minutes review time** - Admin can review and approve invoice in under 5 minutes
4. ✅ **Zero manual QB entry** - All invoices created programmatically
5. ✅ **Accurate shipping costs** - UPS rates match actual shipping charges
6. ✅ **Error recovery** - System handles API failures gracefully
7. ✅ **Audit trail** - Full history of flagged calls → invoices

---

## 🎯 Next Steps

1. **Review this plan** with stakeholders
2. **Set up development environment**
3. **Create GitHub repository** for invoice-generator project
4. **Configure API access** (UPS, QB, Claude)
5. **Start with Phase 1** (foundation and database access)
6. **Iterate based on testing** and feedback

---

## 📞 Questions & Clarifications

- **How many invoices per day** are expected? (affects rate limits)
- **Custom pricing frequency** - how often are prices negotiated?
- **Product catalog size** - how many products total?
- **Integration timeline** - when do you need this operational?
- **Budget for UPS API** - UPS charges per API call
- **Existing QuickBooks workflows** - any conflicts to avoid?

---

**Document Version**: 1.0
**Last Updated**: 2025-11-06
**Author**: Claude (Anthropic)
**Status**: Ready for Development
