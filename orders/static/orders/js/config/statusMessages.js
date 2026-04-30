// orders/static/orders/js/config/statusMessages.js

/**
 * Centralized message templates for notification modal.
 * 
 * Each key in STATUS_MESSAGE_MAP corresponds to a backend status.
 * The function receives `pushData` (order/flight info) and returns an HTML string.
 *
 * Example:
 *   STATUS_MESSAGE_MAP['ready'](pushData)
 *     → "Your Order 12 for Café Rio is now ready at Counter 3."
 *
 * NOTE: Keep these templates generic and concise to ensure they are safe for all
 * project variants (Food Flash, Airline Flash, Dine Flash, etc.). 
 * Flavour-specific overrides should be handled in notificationService.js.
 */
export const STATUS_MESSAGE_MAP = {
  preparing: (data) => `
    Your Order <strong>${data.token_no}</strong> for <strong>${data.item_name || data.name || 'your item'}</strong>
    is now <strong>preparing</strong>. Please wait while we finish it.`,
  item_preparing: (data) => STATUS_MESSAGE_MAP.preparing(data),
  buffet_item_preparing: (data) => STATUS_MESSAGE_MAP.preparing(data),

  ready: (data) => `
    Your order <strong>${data.token_no}</strong> is <strong>ready</strong>.`,
  item_ready: (data) => STATUS_MESSAGE_MAP.ready(data),
  buffet_item_ready: (data) => STATUS_MESSAGE_MAP.ready(data),

  cancelled: (data) => `
    Unfortunately, your order <strong>${data.token_no}</strong> for <strong>${data.item_name || data.name || 'your item'}</strong> 
    has been cancelled. Please contact staff for assistance.`,
  item_cancelled: (data) => STATUS_MESSAGE_MAP.cancelled(data),
  buffet_item_cancelled: (data) => STATUS_MESSAGE_MAP.cancelled(data),


  delivered: (data) => `
    Your Order <strong>${data.token_no}</strong> for <strong>${data.item_name || data.name || 'your item'}</strong>
    has been delivered. Thank you for choosing us!`,
  item_delivered: (data) => STATUS_MESSAGE_MAP.delivered(data),
  order_delivered: (data) => STATUS_MESSAGE_MAP.delivered(data),

  buffetstatus: (data) => `
    Your order has been received, token no : <strong>${data.token_no}</strong>`,



  checked_in: (data) => `
    You have successfully checked-In for <strong>Flight ${data.flight_no}</strong>.`,

  boarding_shortly: (data) => `
    <strong>Flight ${data.flight_no}</strong> will be ready for boarding shortly. 
    Kindly wait for next announcement.`,

  boarding_announced: (data) => `
    <strong>Flight ${data.flight_no}</strong> is ready for boarding.
    Kindly proceed through boarding gate.`,

  rescheduled: (data) => `
    <strong>Flight ${data.flight_no}</strong> is Resheduled.
    Kindly contact the airline staff.`,

  gate_change: (data) => `
    Gate No changed.Revised Gate No will be Announced Shortly`,

  flightcancel: (data) => `
    Kindly contact the airline staff.`,

  waiting: (data) => `
    Your Booking No <strong>${data.booking_no}</strong> for <strong>${data.alias_name || data.name || 'the outlet'}</strong>
    is now <strong>waiting</strong> for allocation.`,

  allocated: (data) => `
    Your Booking No <strong>${data.booking_no}</strong> for <strong>${data.alias_name || data.name || 'the outlet'}</strong>
    has been Allocated at <strong>${data.utility_name}</strong>.`,

  utility_transfer: (data) => `
    Your Booking No <strong>${data.booking_no}</strong> for <strong>${data.alias_name || data.name || 'the outlet'}</strong>
    has been transferred to <strong>${data.utility_name}</strong>.`,

  occupied: (data) => `
    Your Booking No <strong>${data.booking_no}</strong> for <strong>${data.alias_name || data.name || 'the outlet'}</strong>
    is now <strong>Occupied</strong>. Enjoy your meal!`,

  booking_cancelled: (data) => `
    Your Booking No <strong>${data.booking_no}</strong> for <strong>${data.alias_name || data.name || 'the outlet'}</strong>
    has been <strong>Cancelled</strong>.`,

  operation_closed: (data) => `
    Thank you for choosing us today.`,

};
