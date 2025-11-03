"""
QuickBooks Sync Worker
Background process that retries failed QuickBooks syncs
"""
import time
import schedule
from datetime import datetime
from database import get_pending_orders, update_sync_status
from quickbooks_client import QuickBooksClient
from config import Config


def sync_pending_orders():
    """
    Check for pending/failed orders and retry syncing to QuickBooks
    Runs periodically to handle orders that failed during initial sync
    """
    print(f"\n[SyncWorker] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Starting sync check...")

    try:
        # Get orders that need syncing
        pending_orders = get_pending_orders()

        if not pending_orders:
            print(f"[SyncWorker] No pending orders to sync")
            return

        print(f"[SyncWorker] Found {len(pending_orders)} orders to sync")

        # Initialize QuickBooks client
        try:
            qb_client = QuickBooksClient()
            print(f"[SyncWorker] QuickBooks client initialized")
        except Exception as e:
            print(f"[SyncWorker] ❌ Failed to initialize QuickBooks client: {e}")
            print(f"[SyncWorker] Will retry in next cycle")
            return

        # Process each order
        synced_count = 0
        failed_count = 0

        for order in pending_orders:
            print(f"\n[SyncWorker] Processing order #{order.id} - {order.customer_name}")

            try:
                # Prepare address dict
                address = {
                    'street': order.address_street,
                    'city': order.address_city,
                    'state': order.address_state,
                    'zip': order.address_zip
                }

                # Step 1: Create or get customer
                print(f"[SyncWorker] Creating/getting customer...")
                qb_customer_id = qb_client.get_or_create_customer(
                    name=order.customer_name,
                    phone=order.customer_phone,
                    address=address
                )
                print(f"[SyncWorker] ✓ Customer ID: {qb_customer_id}")

                # Step 2: Create invoice
                print(f"[SyncWorker] Creating invoice...")
                invoice = qb_client.create_invoice(
                    customer_id=qb_customer_id,
                    product_name=Config.DETERGENT_PRODUCT_NAME,
                    quantity=1,
                    payment_method=order.payment_method
                )
                print(f"[SyncWorker] ✓ Invoice #{invoice.DocNumber} created (ID: {invoice.Id})")

                # Step 3: Update database
                update_sync_status(
                    order_id=order.id,
                    status='synced',
                    qb_data={
                        'customer_id': qb_customer_id,
                        'invoice_id': invoice.Id,
                        'invoice_number': invoice.DocNumber
                    }
                )

                print(f"[SyncWorker] ✅ Order #{order.id} synced successfully")
                synced_count += 1

            except Exception as e:
                # Log error and mark as failed
                error_msg = str(e)
                print(f"[SyncWorker] ❌ Order #{order.id} sync failed: {error_msg}")

                update_sync_status(
                    order_id=order.id,
                    status='failed',
                    error=error_msg
                )

                failed_count += 1

            # Small delay between orders to avoid rate limiting
            time.sleep(1)

        # Summary
        print(f"\n[SyncWorker] Sync cycle complete:")
        print(f"[SyncWorker] - Synced: {synced_count}")
        print(f"[SyncWorker] - Failed: {failed_count}")
        print(f"[SyncWorker] - Total processed: {synced_count + failed_count}\n")

    except Exception as e:
        print(f"[SyncWorker] ❌ Unexpected error in sync cycle: {e}")


def start_sync_worker():
    """
    Start the background sync worker
    Runs sync_pending_orders() every 5 minutes
    """
    print(f"[SyncWorker] Starting background sync worker...")
    print(f"[SyncWorker] Will check for pending orders every 5 minutes")

    # Schedule the job
    schedule.every(5).minutes.do(sync_pending_orders)

    # Run immediately on startup
    print(f"[SyncWorker] Running initial sync check...")
    sync_pending_orders()

    # Keep running
    print(f"[SyncWorker] Worker started. Press Ctrl+C to stop.\n")

    while True:
        schedule.run_pending()
        time.sleep(30)  # Check every 30 seconds if it's time to run


if __name__ == "__main__":
    # Run as standalone process
    try:
        start_sync_worker()
    except KeyboardInterrupt:
        print(f"\n[SyncWorker] Stopping worker...")
        print(f"[SyncWorker] Goodbye!")
