# QuickBooks Online Invoice Integration Plan
**Using PostgreSQL + OAuth2 + Extended Detergent Order Flow**

---

## Phase 1: QuickBooks OAuth Setup (One-Time - ~15 minutes)

### Step 1: Create QuickBooks Developer Account
1. Go to https://developer.intuit.com
2. Click "Sign In" (top right) or "Get started"
3. Use your Intuit/QuickBooks credentials or create new account
4. Accept developer terms

### Step 2: Create Your App
1. Click "My Apps" in dashboard
2. Click "Create an app"
3. Select "QuickBooks Online and Payments"
4. App Name: `TEMCO Phone Agent` (or your choice)
5. Click "Create app"

### Step 3: Get Your Credentials
1. In your app dashboard, go to "Keys & OAuth"
2. **Development Keys** section:
   - Copy **Client ID** → save for `.env` as `QUICKBOOKS_CLIENT_ID`
   - Copy **Client Secret** → save for `.env` as `QUICKBOOKS_CLIENT_SECRET`
3. **Redirect URIs** section:
   - Click "Add URI"
   - Enter: `https://chevroletsneezington.com/qb-callback`
   - Click "Save"

### Step 4: Configure OAuth Scopes
1. In "Keys & OAuth" tab
2. Scopes section - ensure these are enabled:
   - `com.intuit.quickbooks.accounting` (read/write invoices & customers)
3. Save changes

### Step 5: Test with Sandbox First
1. Use "Development" keys initially
2. Connect to QuickBooks Sandbox company (test data)
3. Once working, switch to "Production" keys for real company

**You'll complete the OAuth flow after we build the app (we'll create the `/qb-connect` route)**

---

## Phase 2: PostgreSQL Database Setup

### Option A: DigitalOcean Managed PostgreSQL (Recommended)
1. Log into DigitalOcean
2. Click "Databases" → "Create Database"
3. Choose: **PostgreSQL** version 15 or 16
4. Plan: **Basic** ($15/month for 1GB RAM, 10GB storage)
5. Region: **Same as your droplet** (San Francisco)
6. Database name: `phone_agent_db`
7. Click "Create Database Cluster"
8. Wait 3-5 minutes for provisioning
9. Go to "Connection Details" → Copy connection string
10. Add to `.env` as `DATABASE_URL`

**Connection string format:**
```
postgresql://username:password@host:port/database?sslmode=require
```

### Option B: Self-Hosted PostgreSQL (If You Prefer)
```bash
# On your DigitalOcean droplet:
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo -u postgres createdb phone_agent_db
sudo -u postgres createuser phone_agent_user -P
# Set password when prompted
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE phone_agent_db TO phone_agent_user;"
```

**Connection string for self-hosted:**
```
postgresql://phone_agent_user:your_password@localhost:5432/phone_agent_db
```

---

## Phase 3: Code Implementation

### 1. Install Dependencies
**File**: `requirements.txt`

Add these lines:
```
intuit-oauth==1.2.4
python-quickbooks==0.9.5
psycopg2-binary==2.9.9
sqlalchemy==2.0.23
```

Then run:
```bash
pip install -r requirements.txt
```

### 2. Add Configuration
**File**: `.env` (add these variables)
```bash
# QuickBooks OAuth
QUICKBOOKS_CLIENT_ID=your_client_id_here
QUICKBOOKS_CLIENT_SECRET=your_client_secret_here
QUICKBOOKS_REDIRECT_URI=https://chevroletsneezington.com/qb-callback
QUICKBOOKS_ENVIRONMENT=sandbox  # Change to 'production' when ready
QUICKBOOKS_REALM_ID=  # Will be populated after OAuth
QUICKBOOKS_REFRESH_TOKEN=  # Will be populated after OAuth

# PostgreSQL Database
DATABASE_URL=postgresql://user:password@host:port/phone_agent_db

# Detergent Product (you'll fill this in later)
DETERGENT_PRODUCT_NAME=Detergent Product Name
```

**File**: `config.py`

Add these configuration variables (after existing config):
```python
# QuickBooks Configuration
QUICKBOOKS_CLIENT_ID = os.getenv('QUICKBOOKS_CLIENT_ID')
QUICKBOOKS_CLIENT_SECRET = os.getenv('QUICKBOOKS_CLIENT_SECRET')
QUICKBOOKS_REDIRECT_URI = os.getenv('QUICKBOOKS_REDIRECT_URI')
QUICKBOOKS_ENVIRONMENT = os.getenv('QUICKBOOKS_ENVIRONMENT', 'sandbox')
QUICKBOOKS_REALM_ID = os.getenv('QUICKBOOKS_REALM_ID')
QUICKBOOKS_REFRESH_TOKEN = os.getenv('QUICKBOOKS_REFRESH_TOKEN')

# Database
DATABASE_URL = os.getenv('DATABASE_URL')

# Product Configuration
DETERGENT_PRODUCT_NAME = os.getenv('DETERGENT_PRODUCT_NAME', 'Detergent')
```

### 3. Create Database Models
**New File**: `database.py`

This file will contain:
- SQLAlchemy setup and engine creation
- `DetergentOrder` model with these fields:
  - `id` (Integer, primary key, auto-increment)
  - `call_sid` (String, Twilio call identifier)
  - `customer_name` (String)
  - `customer_phone` (String)
  - `address_street` (String)
  - `address_city` (String)
  - `address_state` (String, 2-letter code)
  - `address_zip` (String)
  - `payment_method` (String)
  - `qb_customer_id` (String, nullable - QuickBooks customer ID)
  - `qb_invoice_id` (String, nullable - QuickBooks invoice ID)
  - `qb_invoice_number` (String, nullable - Human-readable invoice #)
  - `sync_status` (String: 'pending', 'synced', 'failed')
  - `sync_error` (Text, nullable - Error message if sync failed)
  - `created_at` (DateTime, default now)
  - `synced_at` (DateTime, nullable)

Methods to implement:
- `init_db()` - Create all tables
- `create_order(order_data)` - Insert new order
- `update_sync_status(order_id, status, qb_data, error)` - Update after QBO sync
- `get_pending_orders()` - Get orders that need syncing
- `get_recent_orders(limit=50)` - For admin dashboard

### 4. Create QuickBooks Client
**New File**: `quickbooks_client.py`

This file will contain:
- `QuickBooksClient` class with these methods:
  - `__init__()` - Initialize OAuth client and refresh token
  - `_get_client()` - Get authenticated QuickBooks client (handles token refresh)
  - `get_or_create_customer(name, phone, address)`:
    - Search for existing customer by phone number
    - If not found, create new customer
    - Return QuickBooks customer ID
  - `create_invoice(customer_id, product_name, quantity, payment_method)`:
    - Look up product/service by name
    - Create invoice with line item
    - Set customer, payment method, due date
    - Mark as sent
    - Return invoice ID and invoice number
  - `_retry_on_failure(func, max_retries=3)` - Retry helper with exponential backoff

Error handling:
- Catch authentication errors and attempt token refresh
- Catch rate limit errors (429) and wait/retry
- Catch validation errors and log details
- All errors logged with full context

### 5. Extend Conversation Manager
**File**: `conversation_manager.py`

Add these new fields to `__init__` method:
```python
# Extended detergent order data
self.detergent_address_street = None
self.detergent_address_city = None
self.detergent_address_state = None
self.detergent_address_zip = None
self.detergent_payment_method = None
self.detergent_collection_stage = None  # 'name', 'phone', 'address', 'payment', 'complete'
```

Add these new methods:
```python
def set_detergent_address(self, street, city, state, zip_code):
    """Store shipping address"""
    self.detergent_address_street = street
    self.detergent_address_city = city
    self.detergent_address_state = state
    self.detergent_address_zip = zip_code
    self.detergent_collection_stage = 'payment'

def set_detergent_payment(self, payment_method):
    """Store payment method"""
    self.detergent_payment_method = payment_method
    self.detergent_collection_stage = 'complete'

def get_full_detergent_order(self):
    """Get complete order data"""
    return {
        'name': self.detergent_customer_name,
        'phone': self.detergent_customer_phone,
        'address_street': self.detergent_address_street,
        'address_city': self.detergent_address_city,
        'address_state': self.detergent_address_state,
        'address_zip': self.detergent_address_zip,
        'payment_method': self.detergent_payment_method,
        'call_sid': self.call_sid
    }

def is_detergent_order_complete(self):
    """Check if all required data collected"""
    return all([
        self.detergent_customer_name,
        self.detergent_customer_phone,
        self.detergent_address_street,
        self.detergent_address_city,
        self.detergent_address_state,
        self.detergent_address_zip,
        self.detergent_payment_method
    ])
```

### 6. Update Claude System Prompt
**File**: `config.py` - Modify `CLAUDE_SYSTEM_PROMPT`

Add this to the detergent ordering section:
```
When a caller wants to order detergent, collect information in this exact order:

1. NAME: "May I have your name please?" [COLLECT_DETERGENT_NAME]

2. PHONE: "What's the best phone number to reach you at?" [COLLECT_DETERGENT_PHONE]

3. SHIPPING ADDRESS: "What's your shipping address? I'll need the street address, city, state, and ZIP code." [COLLECT_DETERGENT_ADDRESS]
   - Listen carefully for: street number, street name, city, state, ZIP
   - If they give partial info, ask for missing parts
   - Example: "123 Main Street, Oklahoma City, Oklahoma 73102"

4. PAYMENT: "How would you like to pay? We accept credit card, check, or we can invoice you." [COLLECT_DETERGENT_PAYMENT]
   - Listen for: credit card, check, invoice, purchase order, etc.

5. CONFIRM: "Perfect! Let me confirm: [name] at [address], paying by [method]. I'll get this order processed and connect you with our team right away." [DETERGENT_ORDER_COMPLETE]

IMPORTANT ADDRESS PARSING:
- Parse addresses naturally from how people speak
- Handle formats like "123 Main St, OKC, OK 73102" or "123 Main Street in Oklahoma City Oklahoma, zip 73102"
- Extract: street, city, state (2-letter if possible), zip code
- If anything is unclear or missing, ask before proceeding
```

### 7. Update Order Processing Logic
**File**: `app.py` - Modify `handle_ai_response()` function

Add these new marker handlers (after existing detergent markers):

```python
# Check for detergent address collection
collect_address = '[COLLECT_DETERGENT_ADDRESS]' in ai_text
collect_payment = '[COLLECT_DETERGENT_PAYMENT]' in ai_text

# Handle address collection
if collect_address:
    print(f"[AI] 🧴 Collecting shipping address")
    # Address will be parsed from next user response

elif collect_payment:
    print(f"[AI] 🧴 Collecting payment method")
    # Previous response should have been address - parse it
    address_text = user_text.strip()
    parsed_address = parse_address(address_text)  # Helper function to write
    conv_mgr.set_detergent_address(**parsed_address)
    print(f"[AI] 🧴 Address: {parsed_address['street']}, {parsed_address['city']}, {parsed_address['state']} {parsed_address['zip']}")

elif detergent_complete:
    print(f"[AI] 🧴 Detergent order complete")

    # Previous response was payment method
    payment_method = user_text.strip()
    conv_mgr.set_detergent_payment(payment_method)

    # Get complete order data
    order_data = conv_mgr.get_full_detergent_order()
    print(f"[AI] 🧴 Complete Order:")
    print(f"     Name: {order_data['name']}")
    print(f"     Phone: {order_data['phone']}")
    print(f"     Address: {order_data['address_street']}, {order_data['address_city']}, {order_data['address_state']} {order_data['address_zip']}")
    print(f"     Payment: {order_data['payment_method']}")

    # Save to database
    from database import create_order
    order_id = create_order(order_data)
    print(f"[AI] 🧴 Saved to database: Order ID {order_id}")

    # Sync to QuickBooks
    try:
        from quickbooks_client import QuickBooksClient
        qb = QuickBooksClient()

        # Create/update customer
        qb_customer_id = qb.get_or_create_customer(
            name=order_data['name'],
            phone=order_data['phone'],
            address={
                'street': order_data['address_street'],
                'city': order_data['address_city'],
                'state': order_data['address_state'],
                'zip': order_data['address_zip']
            }
        )

        # Create invoice
        invoice = qb.create_invoice(
            customer_id=qb_customer_id,
            product_name=Config.DETERGENT_PRODUCT_NAME,
            quantity=1,
            payment_method=order_data['payment_method']
        )

        # Update database
        from database import update_sync_status
        update_sync_status(
            order_id=order_id,
            status='synced',
            qb_data={
                'customer_id': qb_customer_id,
                'invoice_id': invoice.Id,
                'invoice_number': invoice.DocNumber
            },
            error=None
        )

        print(f"[AI] 🧴 ✅ Synced to QuickBooks - Invoice #{invoice.DocNumber}")

    except Exception as e:
        print(f"[AI] 🧴 ❌ QuickBooks sync failed: {e}")
        from database import update_sync_status
        update_sync_status(order_id=order_id, status='failed', qb_data=None, error=str(e))
```

Add helper function for address parsing:
```python
def parse_address(address_text):
    """
    Parse address from natural language
    Returns dict with street, city, state, zip
    """
    import re

    # Try to extract zip code (5 digits)
    zip_match = re.search(r'\b(\d{5})\b', address_text)
    zip_code = zip_match.group(1) if zip_match else ''

    # Try to extract state (2 letter code)
    state_match = re.search(r'\b([A-Z]{2})\b', address_text.upper())
    state = state_match.group(1) if state_match else ''

    # Remove zip and state from text to isolate street and city
    remaining = address_text
    if zip_code:
        remaining = remaining.replace(zip_code, '')
    if state:
        remaining = re.sub(r'\b' + state + r'\b', '', remaining, flags=re.IGNORECASE)

    # Split by comma - usually: street, city
    parts = [p.strip() for p in remaining.split(',')]

    street = parts[0] if len(parts) > 0 else ''
    city = parts[1] if len(parts) > 1 else ''

    return {
        'street': street,
        'city': city,
        'state': state,
        'zip': zip_code
    }
```

### 8. Add OAuth Routes
**File**: `app.py`

Add these new routes:

```python
@app.route("/qb-connect")
def qb_connect():
    """Initiate QuickBooks OAuth flow"""
    from intuitlib.client import AuthClient
    from config import Config

    auth_client = AuthClient(
        client_id=Config.QUICKBOOKS_CLIENT_ID,
        client_secret=Config.QUICKBOOKS_CLIENT_SECRET,
        redirect_uri=Config.QUICKBOOKS_REDIRECT_URI,
        environment=Config.QUICKBOOKS_ENVIRONMENT
    )

    auth_url = auth_client.get_authorization_url([
        'com.intuit.quickbooks.accounting'
    ])

    # Store state for CSRF protection (optional but recommended)
    return f'<a href="{auth_url}">Connect to QuickBooks</a>'

@app.route("/qb-callback")
def qb_callback():
    """Handle QuickBooks OAuth callback"""
    from intuitlib.client import AuthClient
    from config import Config
    import os

    auth_code = request.args.get('code')
    realm_id = request.args.get('realmId')

    if not auth_code:
        return "Error: No authorization code received", 400

    auth_client = AuthClient(
        client_id=Config.QUICKBOOKS_CLIENT_ID,
        client_secret=Config.QUICKBOOKS_CLIENT_SECRET,
        redirect_uri=Config.QUICKBOOKS_REDIRECT_URI,
        environment=Config.QUICKBOOKS_ENVIRONMENT
    )

    # Exchange code for tokens
    auth_client.get_bearer_token(auth_code, realm_id=realm_id)

    refresh_token = auth_client.refresh_token

    # Save to .env file (simple approach)
    # For production, consider saving to database
    env_path = os.path.join(os.path.dirname(__file__), '.env')

    # Read existing .env
    with open(env_path, 'r') as f:
        lines = f.readlines()

    # Update QUICKBOOKS_REALM_ID and QUICKBOOKS_REFRESH_TOKEN
    with open(env_path, 'w') as f:
        for line in lines:
            if line.startswith('QUICKBOOKS_REALM_ID='):
                f.write(f'QUICKBOOKS_REALM_ID={realm_id}\n')
            elif line.startswith('QUICKBOOKS_REFRESH_TOKEN='):
                f.write(f'QUICKBOOKS_REFRESH_TOKEN={refresh_token}\n')
            else:
                f.write(line)

    return """
    <h1>QuickBooks Connected Successfully!</h1>
    <p>Your phone agent is now connected to QuickBooks Online.</p>
    <p>Realm ID: {}</p>
    <p>You can close this window.</p>
    """.format(realm_id)

@app.route("/qb-status")
def qb_status():
    """Check QuickBooks connection status"""
    from config import Config

    if not Config.QUICKBOOKS_REFRESH_TOKEN:
        return """
        <h1>QuickBooks Not Connected</h1>
        <p><a href="/qb-connect">Click here to connect</a></p>
        """

    # Try to get company info to verify connection
    try:
        from quickbooks_client import QuickBooksClient
        qb = QuickBooksClient()
        # Test connection by getting company info
        return f"""
        <h1>QuickBooks Connected ✅</h1>
        <p>Realm ID: {Config.QUICKBOOKS_REALM_ID}</p>
        <p>Environment: {Config.QUICKBOOKS_ENVIRONMENT}</p>
        """
    except Exception as e:
        return f"""
        <h1>QuickBooks Connection Error ❌</h1>
        <p>Error: {str(e)}</p>
        <p><a href="/qb-connect">Reconnect</a></p>
        """

@app.route("/orders")
def orders_dashboard():
    """View recent orders and sync status"""
    from database import get_recent_orders

    orders = get_recent_orders(limit=50)

    html = """
    <html>
    <head>
        <title>Detergent Orders</title>
        <style>
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #4CAF50; color: white; }
            .synced { background-color: #d4edda; }
            .pending { background-color: #fff3cd; }
            .failed { background-color: #f8d7da; }
        </style>
    </head>
    <body>
        <h1>Detergent Orders</h1>
        <table>
            <tr>
                <th>ID</th>
                <th>Date</th>
                <th>Name</th>
                <th>Phone</th>
                <th>Address</th>
                <th>Payment</th>
                <th>Status</th>
                <th>QBO Invoice</th>
            </tr>
    """

    for order in orders:
        status_class = order.sync_status
        qb_invoice = order.qb_invoice_number if order.qb_invoice_number else '-'

        html += f"""
            <tr class="{status_class}">
                <td>{order.id}</td>
                <td>{order.created_at.strftime('%Y-%m-%d %H:%M')}</td>
                <td>{order.customer_name}</td>
                <td>{order.customer_phone}</td>
                <td>{order.address_city}, {order.address_state}</td>
                <td>{order.payment_method}</td>
                <td>{order.sync_status}</td>
                <td>{qb_invoice}</td>
            </tr>
        """

    html += """
        </table>
    </body>
    </html>
    """

    return html
```

### 9. Add Background Sync Job (Optional)
**New File**: `sync_worker.py`

This file runs as a background process to retry failed syncs:

```python
"""
Background worker to retry failed QuickBooks syncs
Run with: python sync_worker.py
"""
import time
from database import get_pending_orders, update_sync_status
from quickbooks_client import QuickBooksClient
from config import Config

def sync_pending_orders():
    """Find and sync all pending/failed orders"""
    orders = get_pending_orders()

    if not orders:
        print("[Sync Worker] No pending orders")
        return

    print(f"[Sync Worker] Found {len(orders)} pending orders")

    qb = QuickBooksClient()

    for order in orders:
        try:
            print(f"[Sync Worker] Processing order {order.id}...")

            # Create/update customer
            qb_customer_id = qb.get_or_create_customer(
                name=order.customer_name,
                phone=order.customer_phone,
                address={
                    'street': order.address_street,
                    'city': order.address_city,
                    'state': order.address_state,
                    'zip': order.address_zip
                }
            )

            # Create invoice
            invoice = qb.create_invoice(
                customer_id=qb_customer_id,
                product_name=Config.DETERGENT_PRODUCT_NAME,
                quantity=1,
                payment_method=order.payment_method
            )

            # Update database
            update_sync_status(
                order_id=order.id,
                status='synced',
                qb_data={
                    'customer_id': qb_customer_id,
                    'invoice_id': invoice.Id,
                    'invoice_number': invoice.DocNumber
                },
                error=None
            )

            print(f"[Sync Worker] ✅ Order {order.id} synced - Invoice #{invoice.DocNumber}")

        except Exception as e:
            print(f"[Sync Worker] ❌ Order {order.id} failed: {e}")
            update_sync_status(
                order_id=order.id,
                status='failed',
                qb_data=None,
                error=str(e)
            )

if __name__ == "__main__":
    print("[Sync Worker] Starting...")

    while True:
        try:
            sync_pending_orders()
        except Exception as e:
            print(f"[Sync Worker] Error: {e}")

        # Wait 5 minutes before next check
        time.sleep(300)
```

To run in background:
```bash
# On server:
nohup python sync_worker.py > sync_worker.log 2>&1 &
```

---

## Phase 4: Testing Plan

### Test 1: Database Setup
```bash
cd /opt/phone-agent
source venv/bin/activate
python -c "from database import init_db; init_db()"
```

Verify tables created:
```bash
# If using DigitalOcean managed PostgreSQL:
psql $DATABASE_URL -c "\dt"

# Should show: detergent_orders table
```

### Test 2: QuickBooks OAuth
1. Restart Flask app: `sudo systemctl restart phone-agent`
2. Visit: `https://chevroletsneezington.com/qb-connect`
3. Click "Connect to QuickBooks"
4. Log in to QuickBooks (use Sandbox company)
5. Authorize app
6. Should redirect to success page with Realm ID
7. Verify `.env` has `QUICKBOOKS_REALM_ID` and `QUICKBOOKS_REFRESH_TOKEN`
8. Visit: `https://chevroletsneezington.com/qb-status`
9. Should show "Connected ✅"

### Test 3: Manual QuickBooks API Test
Create test file `test_qb.py`:
```python
from quickbooks_client import QuickBooksClient
from config import Config

qb = QuickBooksClient()

# Test customer creation
print("Creating test customer...")
customer_id = qb.get_or_create_customer(
    name="Test Customer",
    phone="555-123-4567",
    address={
        'street': '123 Test St',
        'city': 'Oklahoma City',
        'state': 'OK',
        'zip': '73102'
    }
)
print(f"Customer ID: {customer_id}")

# Test invoice creation
print("Creating test invoice...")
invoice = qb.create_invoice(
    customer_id=customer_id,
    product_name=Config.DETERGENT_PRODUCT_NAME,
    quantity=1,
    payment_method="Check"
)
print(f"Invoice created: #{invoice.DocNumber}")
print(f"Invoice ID: {invoice.Id}")
```

Run:
```bash
python test_qb.py
```

Verify in QuickBooks Sandbox:
- Go to Sales → Customers
- Find "Test Customer"
- Check Invoices

### Test 4: End-to-End Phone Call Test

**Prepare:**
1. Make sure app is running with all changes
2. Update Claude prompt with product name
3. Have test address ready

**Test Call:**
1. Call your Twilio number
2. Wait for greeting
3. Say: "I want to order detergent"
4. AI asks for name → Say: "John Smith"
5. AI asks for phone → Say: "555-867-5309"
6. AI asks for address → Say: "123 Main Street, Oklahoma City, Oklahoma 73102"
7. AI asks for payment → Say: "Credit card"
8. AI confirms and transfers

**Verify:**
1. Check console logs for:
   - "🧴 Detergent order complete"
   - "Saved to database: Order ID X"
   - "✅ Synced to QuickBooks - Invoice #XXX"
2. Visit `https://chevroletsneezington.com/orders`
   - Should show new order with status "synced"
3. Check QuickBooks Sandbox:
   - Customer "John Smith" exists
   - Invoice created with detergent line item
4. Check PostgreSQL:
   ```bash
   psql $DATABASE_URL -c "SELECT * FROM detergent_orders ORDER BY id DESC LIMIT 1;"
   ```

### Test 5: Failure Scenario
1. Stop internet or QuickBooks API temporarily
2. Place another test order
3. Verify order saves to database with status='failed'
4. Restore internet
5. Run sync worker:
   ```bash
   python sync_worker.py
   ```
6. Verify order syncs successfully

### Test 6: Address Parsing
Test various address formats:
- "123 Main St, OKC, OK 73102"
- "456 Elm Street in Oklahoma City Oklahoma 73102"
- "789 Oak Ave, Oklahoma City, OK, 73102"

Verify each parses correctly into street/city/state/zip fields.

---

## Phase 5: Production Deployment

### 1. Switch to Production QuickBooks

**In Intuit Developer Portal:**
1. Go to your app
2. Click "Keys & OAuth"
3. Switch to "Production Keys" tab
4. Copy Production Client ID and Client Secret

**Update `.env`:**
```bash
QUICKBOOKS_CLIENT_ID=production_client_id_here
QUICKBOOKS_CLIENT_SECRET=production_client_secret_here
QUICKBOOKS_ENVIRONMENT=production
QUICKBOOKS_REALM_ID=  # Clear this, will repopulate
QUICKBOOKS_REFRESH_TOKEN=  # Clear this, will repopulate
```

**Reconnect to Production QuickBooks:**
1. Visit `/qb-connect`
2. Log in with REAL QuickBooks account
3. Authorize app
4. Verify connection with `/qb-status`

### 2. Add Real Product Names

**In QuickBooks Online:**
1. Go to Sales → Products and Services
2. Find your detergent product
3. Copy EXACT name (case-sensitive)

**Update `.env`:**
```bash
DETERGENT_PRODUCT_NAME=Detergent - 50oz Bottle
# Or whatever the exact name is in QuickBooks
```

### 3. Database Backups

**If using DigitalOcean Managed PostgreSQL:**
1. In DigitalOcean dashboard
2. Go to your database
3. Settings → Backups
4. Enable daily automated backups
5. Set retention to 7 days (or more)

**If using self-hosted PostgreSQL:**
Create backup script `/opt/phone-agent/backup_db.sh`:
```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/opt/phone-agent/backups"
mkdir -p $BACKUP_DIR

pg_dump phone_agent_db > $BACKUP_DIR/backup_$DATE.sql
gzip $BACKUP_DIR/backup_$DATE.sql

# Keep only last 7 days
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +7 -delete
```

Add to cron:
```bash
crontab -e
# Add line:
0 2 * * * /opt/phone-agent/backup_db.sh
```

### 4. Monitoring & Alerts

**Add to monitoring script or cron:**
```bash
#!/bin/bash
# Check for failed orders
FAILED_COUNT=$(psql $DATABASE_URL -t -c "SELECT COUNT(*) FROM detergent_orders WHERE sync_status='failed';")

if [ "$FAILED_COUNT" -gt 0 ]; then
    echo "WARNING: $FAILED_COUNT orders failed to sync to QuickBooks"
    # Send email or SMS alert here
fi
```

**Manual checks:**
- Visit `/orders` daily to check sync status
- Check QuickBooks invoices weekly
- Monitor `sync_worker.log` for errors

### 5. Production Checklist

Before going live:
- [ ] QuickBooks Production OAuth completed
- [ ] Real product names configured in `.env`
- [ ] Database backups enabled
- [ ] Sync worker running in background
- [ ] Test call completed successfully
- [ ] Invoice verified in production QuickBooks
- [ ] Monitoring/alerts set up
- [ ] Document product names for team

---

## File Changes Summary

### New Files Created:
1. `database.py` - PostgreSQL models & connection
2. `quickbooks_client.py` - QuickBooks API wrapper
3. `sync_worker.py` - Background retry job
4. `test_qb.py` - Manual testing script

### Modified Files:
1. `requirements.txt` - Added dependencies
2. `.env` - Added QBO & database config
3. `config.py` - Load new environment variables
4. `conversation_manager.py` - Add address/payment fields & methods
5. `app.py` - Add OAuth routes, extend order processing, add address parsing

### New Database Tables:
1. `detergent_orders` - Stores all order data and sync status

---

## Troubleshooting Common Issues

### Issue: "Invalid Client" error during OAuth
**Solution:**
- Verify Client ID and Secret are correct
- Check Redirect URI exactly matches what's in Intuit Developer Portal
- Make sure using correct environment (sandbox vs production)

### Issue: "Product not found" when creating invoice
**Solution:**
- Log into QuickBooks Online
- Go to Sales → Products and Services
- Copy EXACT product name (including spaces, capitalization)
- Update `DETERGENT_PRODUCT_NAME` in `.env`

### Issue: Address parsing fails
**Solution:**
- Check logs to see what user said
- Update `parse_address()` function to handle that format
- Consider using Google Maps API for address validation (future enhancement)

### Issue: Token expired errors
**Solution:**
- QuickBooks tokens expire after 100 days
- Reconnect via `/qb-connect`
- Or implement automatic token refresh (advanced)

### Issue: Database connection fails
**Solution:**
- Verify `DATABASE_URL` format is correct
- Check PostgreSQL is running: `psql $DATABASE_URL -c "SELECT 1;"`
- Check firewall allows connection from your app server
- For DigitalOcean managed DB, verify trusted sources configured

### Issue: Orders stuck in "pending" status
**Solution:**
- Check if sync worker is running: `ps aux | grep sync_worker`
- Check sync worker logs: `tail -f sync_worker.log`
- Manually run: `python sync_worker.py`
- Check QuickBooks API status: https://status.developer.intuit.com/

---

## Estimated Timeline

| Phase | Task | Time |
|-------|------|------|
| 1 | QuickBooks OAuth Setup | 15 min |
| 2 | PostgreSQL Setup (managed) | 10 min |
| 2 | PostgreSQL Setup (self-hosted) | 30 min |
| 3 | Code Implementation | 2-3 hours |
| 4 | Testing | 1 hour |
| 5 | Production Deploy | 30 min |
| **Total** | | **4-5 hours** |

---

## Next Steps

1. ✅ Create QuickBooks Developer account
2. ✅ Set up PostgreSQL database on DigitalOcean
3. ⏳ Implement code changes (database.py, quickbooks_client.py, etc.)
4. ⏳ Complete OAuth flow
5. ⏳ Add product name to config
6. ⏳ Test end-to-end
7. ⏳ Deploy to production

---

## Support & Resources

- **QuickBooks API Documentation**: https://developer.intuit.com/app/developer/qbo/docs/api/accounting/all-entities/invoice
- **Python QuickBooks SDK**: https://github.com/sidecars/python-quickbooks
- **Intuit OAuth Guide**: https://developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/oauth-2.0
- **PostgreSQL Documentation**: https://www.postgresql.org/docs/
- **SQLAlchemy Documentation**: https://docs.sqlalchemy.org/

---

**Document Version**: 1.0
**Last Updated**: 2025-11-03
**Author**: Claude Code Assistant
