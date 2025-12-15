# managers/utils/booking_counts.py
def get_booking_status_counts(bookings_qs,serialized_data):
    counts = {
        "created": 0,
        "waiting": 0,
        "allocated": 0,
        "occupied": 0,
        "booking_cancelled": 0,
        "operation_closed": 0,
        "unread": 0,
    }

    for p in bookings_qs:
        status_name = getattr(p, 'status', '').lower()
        if status_name in counts:
            counts[status_name] += 1

    counts["unread"] = sum(1 for item in serialized_data if item.get("new_notifications", 0) > 0)
    return counts
    
