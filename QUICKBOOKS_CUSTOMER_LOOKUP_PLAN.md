# QuickBooks Customer Lookup Enhancement - Implementation Plan

**Created:** 2025-01-04
**Status:** Planning - Ready for Implementation
**Production Impact:** Medium - Modifies detergent order workflow

---

## Overview

Transform the detergent order workflow to automatically look up customers using **caller ID from Twilio**, then present all customer information for confirmation in a single message. Update QuickBooks records if customer provides corrections.

---

## User Requirements

Based on user responses:

1. **Question Order:** Use caller ID → QuickBooks lookup → Confirm all data (automatic, no need to ask for phone)
2. **Confirmation:** Present all available data in one message (name, address, email)
3. **QuickBooks Updates:** YES - Update QB records with any corrections provided during call
4. **Addresses:** Use billing address only (assume ship to same address)

---

## Current vs. New Workflow

### Current Flow (8 questions for new customers)
```
1. Detergent intent detected
2. Ask for name
3. Ask for phone
4. QuickBooks lookup by phone
5. If found: Confirm address only
6. If not found: Ask street → city → state → ZIP
7. Ask payment method
8. Ask quantity
9. Submit order
```

**Problem:** Even for existing customers, we ask for name and phone before looking them up, then only confirm address.

### New Flow (2 questions for existing customers!)
```
1. Detergent intent detected
2. Automatic QuickBooks lookup using caller ID from Twilio

   ┌─ IF CUSTOMER FOUND:
   │  3. Present all data: "I have [Name] on file at [Address], email [Email]. Is this correct?"
   │  4a. User says "Yes" → Skip to payment method (Question 5)
   │  4b. User says "No" → Ask what to update → Collect corrections → Flag for QB update
   │
   └─ IF CUSTOMER NOT FOUND:
      3. Ask for name
      4. Confirm/ask for phone number
      5. Collect address (street → city → state → ZIP)

5. Ask payment method
6. Ask quantity
7. Submit order
8. Update QuickBooks with any corrections (if applicable)
```

---

## Implementation Details

### Files to Modify

#### 1. `conversation_manager.py`

**Add new fields for customer data tracking:**

```python
# Detergent order tracking (EXISTING FIELDS - keep these)
self.collecting_detergent_info = False
self.detergent_customer_name = None
self.detergent_customer_phone = None
self.detergent_address_street = None
self.detergent_address_city = None
self.detergent_address_state = None
self.detergent_address_zip = None
self.detergent_payment_method = None
self.detergent_quantity = None
self.detergent_awaiting_address_confirmation = False
self.detergent_stored_address = None

# NEW FIELDS TO ADD:
self.detergent_quickbooks_customer = None      # Full Customer object from QB
self.detergent_customer_email = None           # Email from QuickBooks
self.detergent_awaiting_full_confirmation = False  # Waiting for "yes/no" on all data
self.detergent_needs_qb_update = False         # Flag if customer provided corrections
self.detergent_qb_updates = {}                 # Dict of fields to update in QB
```

**Update `clear_detergent_info()` method:**
Add the new fields to the reset list.

---

#### 2. `quickbooks_client.py`

**Add helper method to extract customer data:**

```python
def get_customer_summary(self, customer):
    """
    Extract and format customer data for phone order confirmation

    Args:
        customer: QuickBooks Customer object

    Returns:
        dict with formatted customer information
    """
    summary = {
        'qb_customer_id': customer.Id,
        'name': customer.DisplayName if customer.DisplayName else None,
        'phone': None,
        'email': None,
        'address_street': None,
        'address_city': None,
        'address_state': None,
        'address_zip': None
    }

    # Extract phone
    if customer.PrimaryPhone and customer.PrimaryPhone.FreeFormNumber:
        summary['phone'] = customer.PrimaryPhone.FreeFormNumber

    # Extract email
    if customer.PrimaryEmailAddr and customer.PrimaryEmailAddr.Address:
        summary['email'] = customer.PrimaryEmailAddr.Address

    # Extract billing address
    if customer.BillAddr:
        addr = customer.BillAddr
        summary['address_street'] = addr.Line1 if addr.Line1 else None
        summary['address_city'] = addr.City if addr.City else None
        summary['address_state'] = addr.CountrySubDivisionCode if addr.CountrySubDivisionCode else None
        summary['address_zip'] = addr.PostalCode if addr.PostalCode else None

    return summary
```

**Add method to update customer records:**

```python
def update_customer(self, customer_id, updates):
    """
    Update customer information in QuickBooks

    Args:
        customer_id: QuickBooks customer ID
        updates: dict with keys: name, email, address_street, address_city, address_state, address_zip

    Returns:
        True if successful, False otherwise
    """
    def _update():
        print(f"[QuickBooks] Updating customer ID {customer_id}")

        # Fetch current customer
        customer = Customer.get(customer_id, qb=self.qb_client)

        # Update name
        if 'name' in updates and updates['name']:
            customer.DisplayName = updates['name']
            parts = updates['name'].split()
            customer.GivenName = parts[0] if parts else updates['name']
            customer.FamilyName = parts[-1] if len(parts) > 1 else ''

        # Update email
        if 'email' in updates and updates['email']:
            from quickbooks.objects.base import EmailAddress
            if not customer.PrimaryEmailAddr:
                customer.PrimaryEmailAddr = EmailAddress()
            customer.PrimaryEmailAddr.Address = updates['email']

        # Update address
        if any(k in updates for k in ['address_street', 'address_city', 'address_state', 'address_zip']):
            from quickbooks.objects.base import Address
            if not customer.BillAddr:
                customer.BillAddr = Address()

            if 'address_street' in updates:
                customer.BillAddr.Line1 = updates['address_street']
            if 'address_city' in updates:
                customer.BillAddr.City = updates['address_city']
            if 'address_state' in updates:
                customer.BillAddr.CountrySubDivisionCode = updates['address_state']
            if 'address_zip' in updates:
                customer.BillAddr.PostalCode = updates['address_zip']
            customer.BillAddr.Country = 'USA'

        # Save changes
        customer.save(qb=self.qb_client)

        print(f"[QuickBooks] ✓ Customer {customer_id} updated successfully")
        return True

    try:
        return self._retry_on_failure(_update)
    except Exception as e:
        print(f"[QuickBooks] ❌ Failed to update customer {customer_id}: {e}")
        return False
```

---

#### 3. `app.py` - Main Workflow Changes

**Location:** Around lines 926-1132 (detergent workflow section)

**Change 1: Automatic caller ID lookup when detergent intent detected**

```python
# CURRENT CODE (line ~926):
if detergent_order_detected and not conv_mgr.collecting_detergent_info:
    print(f"[AI] [OVERRIDE] Detergent order detected! Forcing workflow start, bypassing Claude.")
    forced_response = "I can help with that. May I have your name please? [COLLECT_DETERGENT_NAME]"
    print(f"[AI] [OVERRIDE] Forced response: '{forced_response}'\n")

# NEW CODE:
if detergent_order_detected and not conv_mgr.collecting_detergent_info:
    print(f"[AI] [OVERRIDE] Detergent order detected! Checking caller ID for existing customer...")

    # Get caller's phone number from session
    caller_phone = session.get('caller_number')

    if caller_phone:
        # Try QuickBooks lookup using caller ID
        try:
            from quickbooks_client import QuickBooksClient
            qb = QuickBooksClient()
            existing_customer = qb.search_customer_by_phone(caller_phone)

            if existing_customer:
                # Customer found! Extract all data
                customer_data = qb.get_customer_summary(existing_customer)
                conv_mgr.detergent_quickbooks_customer = existing_customer
                conv_mgr.detergent_customer_name = customer_data['name']
                conv_mgr.detergent_customer_phone = customer_data['phone'] or caller_phone
                conv_mgr.detergent_customer_email = customer_data['email']

                # Store address if available
                if customer_data['address_street']:
                    conv_mgr.detergent_address_street = customer_data['address_street']
                    conv_mgr.detergent_address_city = customer_data['address_city']
                    conv_mgr.detergent_address_state = customer_data['address_state']
                    conv_mgr.detergent_address_zip = customer_data['address_zip']

                conv_mgr.collecting_detergent_info = True
                conv_mgr.detergent_awaiting_full_confirmation = True

                # Generate confirmation message with all data
                confirmation_parts = [f"I can help! I have {customer_data['name']} on file"]

                if customer_data['address_street']:
                    confirmation_parts.append(f"at {customer_data['address_street']}, {customer_data['address_city']}, {customer_data['address_state']} {customer_data['address_zip']}")

                if customer_data['email']:
                    confirmation_parts.append(f"email {customer_data['email']}")

                confirmation_msg = " ".join(confirmation_parts) + ". Is this all correct? [CONFIRM_CUSTOMER_DATA]"

                print(f"[AI] [OVERRIDE] Found existing customer: {customer_data['name']}")
                print(f"[AI] [OVERRIDE] Confirmation: {confirmation_msg}")
                forced_response = confirmation_msg
            else:
                # Customer not found - proceed with manual collection
                print(f"[AI] [OVERRIDE] No customer found for {caller_phone}, collecting manually")
                forced_response = "I can help with that. May I have your name please? [COLLECT_DETERGENT_NAME]"

        except Exception as e:
            # QuickBooks lookup failed - fall back to manual collection
            print(f"[AI] [OVERRIDE] QuickBooks lookup error: {e}, collecting manually")
            forced_response = "I can help with that. May I have your name please? [COLLECT_DETERGENT_NAME]"
    else:
        # No caller ID available - fall back to manual collection
        print(f"[AI] [OVERRIDE] No caller ID available, collecting manually")
        forced_response = "I can help with that. May I have your name please? [COLLECT_DETERGENT_NAME]"
```

**Change 2: Add handler for full data confirmation**

Insert this BEFORE the name collection handler (before line ~940):

```python
elif conv_mgr.detergent_awaiting_full_confirmation:
    # User is confirming or denying all their information from QuickBooks
    print(f"[AI] [OVERRIDE] State: Full customer data confirmation received")
    user_response = user_text.lower().strip()

    # Check for affirmative responses
    affirmative_keywords = ['yes', 'yeah', 'yep', 'correct', 'right', 'that\'s right', 'perfect', 'good', 'fine', 'ok', 'okay']
    negative_keywords = ['no', 'nope', 'wrong', 'incorrect', 'not', 'different', 'change', 'update']

    is_affirmative = any(keyword in user_response for keyword in affirmative_keywords)
    is_negative = any(keyword in user_response for keyword in negative_keywords)

    if is_affirmative and not is_negative:
        # User confirmed all data - skip to payment method!
        print(f"[AI] [OVERRIDE] Customer data confirmed, skipping to payment")
        conv_mgr.detergent_awaiting_full_confirmation = False
        forced_response = "Perfect. How would you like to pay? We accept credit card, check, or we can invoice you. [COLLECT_DETERGENT_PAYMENT]"

    elif is_negative:
        # User needs to update something
        print(f"[AI] [OVERRIDE] Customer needs to update information")
        conv_mgr.detergent_awaiting_full_confirmation = False
        conv_mgr.detergent_needs_qb_update = True
        forced_response = "No problem. What would you like to update? Your name, address, or email? [COLLECT_CORRECTION]"

    else:
        # Unclear response - ask again
        print(f"[AI] [OVERRIDE] Unclear confirmation response, asking again")
        forced_response = "I didn't catch that. Is the information I have on file still correct? [CONFIRM_CUSTOMER_DATA]"
```

**Change 3: Add correction handler**

Insert after the full confirmation handler:

```python
elif '[COLLECT_CORRECTION]' in ai_text or conv_mgr.detergent_needs_qb_update:
    # User said data is wrong, determine what needs updating
    print(f"[AI] [OVERRIDE] State: Collecting correction information")
    user_response = user_text.lower().strip()

    # Determine what they want to update
    if 'name' in user_response:
        print(f"[AI] [OVERRIDE] User wants to update name")
        conv_mgr.detergent_customer_name = None  # Clear to trigger collection
        forced_response = "What name should I use for this order? [COLLECT_DETERGENT_NAME]"
        conv_mgr.detergent_qb_updates['name'] = True

    elif 'address' in user_response:
        print(f"[AI] [OVERRIDE] User wants to update address")
        # Clear address fields
        conv_mgr.detergent_address_street = None
        conv_mgr.detergent_address_city = None
        conv_mgr.detergent_address_state = None
        conv_mgr.detergent_address_zip = None
        forced_response = "What's the street address? [COLLECT_DETERGENT_ADDRESS]"
        conv_mgr.detergent_qb_updates['address'] = True

    elif 'email' in user_response:
        print(f"[AI] [OVERRIDE] User wants to update email")
        forced_response = "What's your email address? [COLLECT_DETERGENT_EMAIL]"
        conv_mgr.detergent_qb_updates['email'] = True

    else:
        # Default: assume address (most common correction)
        print(f"[AI] [OVERRIDE] Unclear what to update, defaulting to address")
        conv_mgr.detergent_address_street = None
        conv_mgr.detergent_address_city = None
        conv_mgr.detergent_address_state = None
        conv_mgr.detergent_address_zip = None
        forced_response = "What's your current street address? [COLLECT_DETERGENT_ADDRESS]"
        conv_mgr.detergent_qb_updates['address'] = True
```

**Change 4: Add email collection handler**

Insert after ZIP code collection (after line ~1102):

```python
elif '[COLLECT_DETERGENT_EMAIL]' in ai_text:
    # User is providing email address
    print(f"[AI] [OVERRIDE] State: Email provided")
    email = user_text.strip().split('.')[0].strip()  # Take first sentence
    conv_mgr.detergent_customer_email = email
    print(f"[AI] [OVERRIDE] Stored email: {email}")
    forced_response = "Perfect. How would you like to pay? We accept credit card, check, or we can invoice you. [COLLECT_DETERGENT_PAYMENT]"
```

**Change 5: Update QuickBooks after order completion**

After order is saved to database and QB invoice created (around line 1260):

```python
# EXISTING CODE: Invoice created successfully
print(f"[AI] 🧴 ✅ Synced to QuickBooks - Invoice #{invoice.DocNumber}")

# NEW CODE: Update customer record if corrections were provided
if conv_mgr.detergent_needs_qb_update and conv_mgr.detergent_qb_updates:
    try:
        qb_customer_id = conv_mgr.detergent_quickbooks_customer.Id if conv_mgr.detergent_quickbooks_customer else qb_customer_id

        # Build updates dict
        updates = {}

        if 'name' in conv_mgr.detergent_qb_updates and conv_mgr.detergent_customer_name:
            updates['name'] = conv_mgr.detergent_customer_name

        if 'email' in conv_mgr.detergent_qb_updates and conv_mgr.detergent_customer_email:
            updates['email'] = conv_mgr.detergent_customer_email

        if 'address' in conv_mgr.detergent_qb_updates:
            updates['address_street'] = conv_mgr.detergent_address_street
            updates['address_city'] = conv_mgr.detergent_address_city
            updates['address_state'] = conv_mgr.detergent_address_state
            updates['address_zip'] = conv_mgr.detergent_address_zip

        if updates:
            print(f"[AI] 🧴 Updating QuickBooks customer record with corrections...")
            success = qb.update_customer(qb_customer_id, updates)
            if success:
                print(f"[AI] 🧴 ✅ Customer record updated in QuickBooks")
            else:
                print(f"[AI] 🧴 ⚠️ Customer record update failed (non-critical)")
    except Exception as e:
        print(f"[AI] 🧴 ⚠️ Failed to update customer record: {e} (non-critical)")
```

**Change 6: Add marker removal**

Around line 1300, add:

```python
spoken_text = spoken_text.replace('[CONFIRM_CUSTOMER_DATA]', '').strip()
spoken_text = spoken_text.replace('[COLLECT_CORRECTION]', '').strip()
spoken_text = spoken_text.replace('[COLLECT_DETERGENT_EMAIL]', '').strip()
```

---

## Example Conversations

### Scenario 1: Existing Customer - All Correct (2 questions!)

```
User: "I need more detergent"
[System automatically looks up caller ID 555-123-4555]
[QuickBooks: Found John Smith]

AI: "I can help! I have John Smith on file at 123 Main St, Oklahoma City,
     OK 73108, email john@example.com. Is this all correct?"

User: "Yes"

AI: "Perfect. How would you like to pay?"
User: "Credit card"

AI: "Great! Let me confirm: John Smith at Oklahoma City, OK, paying by
     credit card. How many units would you like to order?"
User: "Two"

AI: "Order submitted. Is there anything else I can help you with today?"

[Order saved to database]
[Invoice created in QuickBooks]
[No QB update needed - data was correct]
```

**Questions asked: 2 (payment + quantity)**
**Skipped: name, phone, street, city, state, ZIP**

---

### Scenario 2: Existing Customer - Address Changed

```
User: "I want detergent"
[Caller ID lookup: Found]

AI: "I can help! I have Jane Doe on file at 456 Oak Ave, Tulsa, OK 74105.
     Is this correct?"

User: "No, I moved"

AI: "No problem. What would you like to update? Your name, address, or email?"
User: "Address"

AI: "What's the street address?"
User: "789 Pine Street"

AI: "What city?"
User: "Oklahoma City"

AI: "And the state?"
User: "Oklahoma"

AI: "And the ZIP code?"
User: "73108"

AI: "Perfect. How would you like to pay?"
[Continue with payment + quantity]

[After order completion]
[QuickBooks customer record updated with new address]
```

**Questions asked: 7 (what to update, street, city, state, ZIP, payment, quantity)**
**Skipped: name, phone**
**Bonus: QuickBooks updated for future orders**

---

### Scenario 3: New Customer

```
User: "I need detergent"
[Caller ID lookup: Not found]

AI: "I can help with that. May I have your name please?"
User: "Bob Johnson"

AI: "Thank you Bob. I have your number as 555-999-8888, is that correct?"
User: "Yes"

AI: "What's the street address?"
[Continue with normal address collection]
[Payment + quantity]
[Order submitted]

[New customer created in QuickBooks]
```

**Questions asked: 8 (name, phone confirmation, street, city, state, ZIP, payment, quantity)**
**Same as before for new customers**

---

### Scenario 4: Existing Customer - Email Update

```
User: "More detergent please"
[Found in QB]

AI: "I have Mike Smith at 111 Elm St, Norman, OK 73069, email mike@oldmail.com.
     Is this correct?"

User: "My email changed"

AI: "No problem. What would you like to update?"
User: "Email"

AI: "What's your email address?"
User: "mike@newmail.com"

AI: "Perfect. How would you like to pay?"
[Payment + quantity]
[Order submitted]

[QuickBooks updated with new email]
```

---

## Technical Details

### Accessing Caller ID from Twilio

**In app.py, caller phone is stored in session:**

```python
# Check around line 280-290 where call is initiated
session['caller_number']  # E.164 format: "+15551234555"
```

**Phone number normalization:**
- Twilio provides: `+15551234555` (E.164)
- QuickBooks may have: `(555) 123-4555` or `555-123-4555`
- `search_customer_by_phone()` already handles this by stripping non-digits

### QuickBooks Customer Object Fields

Available from `customer` object after `search_customer_by_phone()`:

```python
customer.Id                                    # QuickBooks ID
customer.DisplayName                           # "John Smith"
customer.GivenName                            # "John"
customer.FamilyName                           # "Smith"
customer.PrimaryPhone.FreeFormNumber          # "555-123-4555"
customer.PrimaryEmailAddr.Address             # "john@example.com"
customer.BillAddr.Line1                       # "123 Main St"
customer.BillAddr.City                        # "Oklahoma City"
customer.BillAddr.CountrySubDivisionCode      # "OK"
customer.BillAddr.PostalCode                  # "73108"
customer.ShipAddr                             # Separate shipping (if different)
```

### Error Handling

**If QuickBooks API call fails:**
- Log error
- Fall back to manual collection (ask for name)
- Order still completes successfully

**If caller ID unavailable:**
- Fall back to manual collection
- Still ask for phone number as normal

**If customer update fails:**
- Log warning (non-critical)
- Order still completes
- Invoice still created
- Customer can be updated manually in QB

---

## Testing Checklist

- [ ] Existing customer, all data correct → Only asks payment + quantity
- [ ] Existing customer, wants to update address → Collects new address, updates QB
- [ ] Existing customer, wants to update email → Collects new email, updates QB
- [ ] Existing customer, wants to update name → Collects new name, updates QB
- [ ] New customer (not in QB) → Full collection flow works
- [ ] Caller ID unavailable → Falls back to manual collection
- [ ] QuickBooks API timeout → Falls back gracefully
- [ ] Customer says "no" but doesn't specify what's wrong → Defaults to address update
- [ ] Multiple corrections in one call → All updates saved to QB
- [ ] Order completion → QB invoice created successfully
- [ ] QB customer update → Changes reflected in QuickBooks

---

## Rollback Plan

If issues arise, revert by:

1. Restore original `app.py` detergent workflow (lines 926-1132)
2. Restore original `conversation_manager.py` (remove new fields)
3. Restore original `quickbooks_client.py` (remove new methods)

System will revert to: Ask name → Ask phone → Confirm address only

---

## Future Enhancements (Not in this phase)

1. Handle shipping vs billing address separately
2. Fuzzy name matching ("Jon" vs "John")
3. Multiple phone numbers per customer
4. Business/company name handling
5. Special instructions or notes
6. Preferred payment method stored in QB
7. Order history ("Last time you ordered 3 units, same this time?")

---

## Implementation Priority

**Phase 1 (High Priority):**
- Caller ID lookup
- Full data confirmation
- Skip to payment for existing customers

**Phase 2 (Medium Priority):**
- Correction handling
- QuickBooks updates

**Phase 3 (Low Priority):**
- Email collection
- Advanced error handling

---

## Summary

This enhancement will:

✅ Reduce questions from 8 to 2 for existing customers
✅ Provide personalized service ("I have you on file...")
✅ Keep QuickBooks data accurate with automatic updates
✅ Maintain fallback safety for new customers or failures
✅ Improve customer experience significantly

**Estimated implementation time:** 4-6 hours
**Testing time:** 2-3 hours
**Total:** 1 business day
