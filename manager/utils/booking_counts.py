# managers/utils/booking_counts.py
def get_booking_status_counts(bookings_qs):
    return {
        "total": bookings_qs.count(),
        "pending": bookings_qs.filter(status="Pending").count(),
        "completed": bookings_qs.filter(status="Completed").count(),
        "preparing": bookings_qs.filter(status="Preparing").count(),
        "ready": bookings_qs.filter(status="Ready").count(),
    }
