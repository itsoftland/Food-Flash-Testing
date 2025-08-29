# utils/order_utils.py
import logging
from .models import Order

logger = logging.getLogger(__name__)

def get_last_tokens(vendor, limit):
    logger.info(f"🔍 Fetching last {limit} token(s) for Vendor: {vendor} (ID: {vendor.id if hasattr(vendor, 'id') else 'N/A'})")
    
    tokens = list(
        Order.objects.filter(vendor=vendor,status='ready')
        .order_by('-updated_at')
        .values_list('token_no', flat=True)[:limit]
    )
    
    logger.info(f"📦 Tokens fetched from DB: {tokens}")

    while len(tokens) < limit:
        tokens.append(0)
    
    logger.info(f"✅ Final tokens list (padded to {limit}): {tokens}")
    return tokens

