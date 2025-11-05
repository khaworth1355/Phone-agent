"""
QuickBooks Online API Client
Handles customer and invoice creation with OAuth2 authentication
"""
import time
from intuitlib.client import AuthClient
from intuitlib.enums import Scopes
from quickbooks import QuickBooks
from quickbooks.objects.customer import Customer
from quickbooks.objects.invoice import Invoice
from quickbooks.objects.item import Item
from quickbooks.objects.detailline import SalesItemLine, SalesItemLineDetail
from config import Config


class QuickBooksClient:
    """QuickBooks Online API wrapper"""

    def __init__(self):
        """Initialize QuickBooks client with OAuth2"""
        self.auth_client = None
        self.qb_client = None
        self._initialize_client()

    def _initialize_client(self):
        """Set up authenticated QuickBooks client"""
        if not Config.QUICKBOOKS_CLIENT_ID or not Config.QUICKBOOKS_CLIENT_SECRET:
            raise ValueError("QuickBooks Client ID and Secret not configured")

        if not Config.QUICKBOOKS_REFRESH_TOKEN or not Config.QUICKBOOKS_REALM_ID:
            raise ValueError(
                "QuickBooks not connected. Please complete OAuth flow at /qb-connect"
            )

        print(f"[QuickBooks] Initializing client for Realm ID: {Config.QUICKBOOKS_REALM_ID}")

        # Create auth client
        self.auth_client = AuthClient(
            client_id=Config.QUICKBOOKS_CLIENT_ID,
            client_secret=Config.QUICKBOOKS_CLIENT_SECRET,
            redirect_uri=Config.QUICKBOOKS_REDIRECT_URI,
            environment=Config.QUICKBOOKS_ENVIRONMENT
        )

        # Set refresh token
        self.auth_client.refresh_token = Config.QUICKBOOKS_REFRESH_TOKEN

        # Refresh to get new access token
        self._refresh_token()

        # Create QuickBooks client
        self.qb_client = QuickBooks(
            auth_client=self.auth_client,
            refresh_token=Config.QUICKBOOKS_REFRESH_TOKEN,
            company_id=Config.QUICKBOOKS_REALM_ID,
            minorversion=65  # API version
        )

        print(f"[QuickBooks] Client initialized successfully")

    def _refresh_token(self):
        """Refresh OAuth2 access token"""
        try:
            self.auth_client.refresh()
            print(f"[QuickBooks] Access token refreshed")
        except Exception as e:
            print(f"[QuickBooks] Error refreshing token: {e}")
            raise ValueError(
                "Failed to refresh QuickBooks token. Please reconnect at /qb-connect"
            )

    def _retry_on_failure(self, func, max_retries=3, *args, **kwargs):
        """
        Retry a function on failure with exponential backoff

        Args:
            func: Function to call
            max_retries: Maximum number of retry attempts
            *args, **kwargs: Arguments to pass to function

        Returns:
            Result of function call
        """
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == max_retries - 1:
                    # Last attempt failed, raise error
                    raise
                else:
                    # Wait with exponential backoff
                    wait_time = 2 ** attempt
                    print(f"[QuickBooks] Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)

    def search_customer_by_phone(self, phone):
        """
        Search for existing customer by phone number

        Args:
            phone: Customer phone number

        Returns:
            Customer object if found, None otherwise
        """
        try:
            # Clean phone number (remove non-digits for comparison)
            clean_phone = ''.join(filter(str.isdigit, phone))

            print(f"[QuickBooks] Searching for customer with phone: {phone}")

            # Query customers
            customers = Customer.all(qb=self.qb_client)

            # Search for phone match
            for customer in customers:
                if customer.PrimaryPhone and customer.PrimaryPhone.FreeFormNumber:
                    customer_phone = ''.join(filter(str.isdigit, customer.PrimaryPhone.FreeFormNumber))
                    if customer_phone == clean_phone:
                        print(f"[QuickBooks] Found existing customer: {customer.DisplayName} (ID: {customer.Id})")
                        return customer

            print(f"[QuickBooks] No existing customer found with phone: {phone}")
            return None

        except Exception as e:
            print(f"[QuickBooks] Error searching customers: {e}")
            return None

    def create_customer(self, name, phone, address):
        """
        Create a new customer in QuickBooks

        Args:
            name: Customer name
            phone: Customer phone number
            address: Dict with keys: street, city, state, zip

        Returns:
            Customer ID
        """
        def _create():
            print(f"[QuickBooks] Creating new customer: {name}")

            customer = Customer()
            customer.DisplayName = name
            customer.GivenName = name.split()[0] if ' ' in name else name
            customer.FamilyName = name.split()[-1] if ' ' in name else ''

            # Set phone
            from quickbooks.objects.base import PhoneNumber, Address
            customer.PrimaryPhone = PhoneNumber()
            customer.PrimaryPhone.FreeFormNumber = phone

            # Set billing address
            customer.BillAddr = Address()
            customer.BillAddr.Line1 = address['street']
            customer.BillAddr.City = address['city']
            customer.BillAddr.CountrySubDivisionCode = address['state']
            customer.BillAddr.PostalCode = address['zip']
            customer.BillAddr.Country = 'USA'

            # Save customer
            customer.save(qb=self.qb_client)

            print(f"[QuickBooks] ✓ Customer created - ID: {customer.Id}")
            return customer.Id

        return self._retry_on_failure(_create)

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

    def get_or_create_customer(self, name, phone, address):
        """
        Get existing customer by phone or create new one

        Args:
            name: Customer name
            phone: Customer phone number
            address: Dict with keys: street, city, state, zip

        Returns:
            Customer ID
        """
        # Search for existing customer
        existing_customer = self.search_customer_by_phone(phone)

        if existing_customer:
            return existing_customer.Id
        else:
            return self.create_customer(name, phone, address)

    def get_item_by_name(self, product_name):
        """
        Get product/service item by name

        Args:
            product_name: Product name to search for

        Returns:
            Item object if found, None otherwise
        """
        try:
            print(f"[QuickBooks] Searching for product: {product_name}")

            # Query items/products
            items = Item.all(qb=self.qb_client)

            # Search for exact match
            for item in items:
                if item.Name and item.Name.lower() == product_name.lower():
                    print(f"[QuickBooks] Found product: {item.Name} (ID: {item.Id})")
                    return item

            print(f"[QuickBooks] ❌ Product not found: {product_name}")
            print(f"[QuickBooks] Available products: {[item.Name for item in items[:10]]}")
            raise ValueError(
                f"Product '{product_name}' not found in QuickBooks. "
                f"Please check DETERGENT_PRODUCT_NAME in .env matches exact product name in QuickBooks."
            )

        except Exception as e:
            print(f"[QuickBooks] Error searching items: {e}")
            raise

    def create_invoice(self, customer_id, product_name, quantity, payment_method):
        """
        Create an invoice for a customer

        Args:
            customer_id: QuickBooks customer ID
            product_name: Product/service name
            quantity: Quantity (usually 1 for detergent)
            payment_method: Payment method string

        Returns:
            Invoice object
        """
        def _create():
            print(f"[QuickBooks] Creating invoice for customer ID: {customer_id}")

            # Get product item
            item = self.get_item_by_name(product_name)

            # Create invoice
            invoice = Invoice()

            # Set customer reference
            from quickbooks.objects.base import Ref
            invoice.CustomerRef = Ref()
            invoice.CustomerRef.value = customer_id

            # Create line item
            line = SalesItemLine()
            line.LineNum = 1
            line.Description = f"{product_name} - {payment_method}"
            line.Amount = item.UnitPrice * quantity

            # Set item details
            line.SalesItemLineDetail = SalesItemLineDetail()
            line.SalesItemLineDetail.ItemRef = Ref()
            line.SalesItemLineDetail.ItemRef.value = item.Id
            line.SalesItemLineDetail.Qty = quantity
            line.SalesItemLineDetail.UnitPrice = item.UnitPrice

            # Add line to invoice
            invoice.Line = [line]

            # Note about payment method (CustomerMemo must be a Memo object)
            from quickbooks.objects.base import CustomerMemo as Memo
            memo = Memo()
            memo.value = f"Payment method: {payment_method}"
            invoice.CustomerMemo = memo

            # Save invoice
            invoice.save(qb=self.qb_client)

            print(f"[QuickBooks] ✓ Invoice created - #{invoice.DocNumber} (ID: {invoice.Id})")
            return invoice

        return self._retry_on_failure(_create)

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

    def get_company_info(self):
        """
        Get company information (useful for testing connection)

        Returns:
            Company name string
        """
        try:
            from quickbooks.objects.company_info import CompanyInfo
            company = CompanyInfo.get(1, qb=self.qb_client)
            print(f"[QuickBooks] Connected to: {company.CompanyName}")
            return company.CompanyName
        except Exception as e:
            print(f"[QuickBooks] Error getting company info: {e}")
            raise


if __name__ == "__main__":
    # Test QuickBooks connection
    print("Testing QuickBooks connection...")
    try:
        qb = QuickBooksClient()
        company_name = qb.get_company_info()
        print(f"✓ Successfully connected to: {company_name}")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
